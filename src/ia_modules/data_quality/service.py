"""Serviço de qualidade de dados — IA Brasil.

Validações automáticas, verificação de frescor e métricas.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select

from src.collector.raw_store import PARSER_VERSION_KEY, QUARANTINE_REASON_KEY
from src.core.db import (
    Acao,
    AcaoInstituicao,
    Avaliacao,
    Eixo,
    Evento,
    Evidencia,
    Fonte,
    Indicador,
    IngestionRun,
    Instituicao,
    Meta,
    Plano,
    Programa,
    Recurso,
    StatusAcao,
    VinculoEvidencia,
    get_session,
)
from src.modules.data_quality.schemas import (
    DataFreshnessInfo,
    DataQualityMetrics,
    DatasetQualityScore,
    FreshnessCheck,
    HealthDataFreshnessResponse,
    QualityAlert,
    QualityReportResponse,
    QuarantineCheck,
    SchemaDriftCheck,
    SourceQualityChecks,
    ValidationResult,
    ValidationSeverity,
    ValidationViolation,
    VolumeCheck,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _env_int(name: str, default: int) -> int:
    """Lê um inteiro do env com fallback (ignora valores inválidos)."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _cadence_from_run(run: IngestionRun | None) -> dict[str, str | date | None]:
    """Lê a cadência declarada persistida no último run terminal (issue #1103).

    O scheduler grava ``periodicidade`` ("2x/ano" ou "manual") e
    ``ultima_referencia`` (data do documento oficial) no
    ``metadata_json`` do run. Este helper normaliza esses valores para o
    ``DataFreshnessInfo``.

    Args:
        run: Último run terminal da fonte (None quando não há runs).

    Returns:
        Dict com ``periodicidade`` e ``ultima_referencia`` (ou None).
    """
    if run is None:
        return {"periodicidade": None, "ultima_referencia": None}

    metadata = run.metadata_json or {}
    periodicidade = metadata.get("periodicidade")
    if not isinstance(periodicidade, str) or not periodicidade:
        periodicidade = None

    ultima_ref: date | None = None
    raw_ref = metadata.get("ultima_referencia")
    if isinstance(raw_ref, date):
        ultima_ref = raw_ref
    elif isinstance(raw_ref, str) and raw_ref:
        try:
            ultima_ref = datetime.fromisoformat(raw_ref).date()
        except ValueError:
            try:
                ultima_ref = date.fromisoformat(raw_ref)
            except ValueError:
                ultima_ref = None

    return {"periodicidade": periodicidade, "ultima_referencia": ultima_ref}


def _budget_targets_from_env() -> dict[int, float]:
    """Carrega metas orçamentárias por exercício (R$ bi) do env.

    Env ``BUDGET_TARGETS_BI`` em formato JSON, ex.: ``{"2025": 23.0}``.
    Default: ``{2025: 23.0}``.
    """
    raw = os.getenv("BUDGET_TARGETS_BI")
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            targets: dict[int, float] = {}
            for key, value in parsed.items():
                try:
                    targets[int(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            if targets:
                return targets
    return {2025: 23.0}


class DataQualityService:
    """Serviço para validação e monitoramento de qualidade dos dados."""

    # Meta orçamentária default (R$ bi) — mantida por compatibilidade;
    # a validação usa metas POR EXERCÍCIO em BUDGET_TARGETS_BI (env).
    EXPECTED_TOTAL_RECURSOS_BI = 23.0

    # Metas orçamentárias por exercício (R$ bi), configuráveis via env.
    BUDGET_TARGETS_BI: dict[int, float] = _budget_targets_from_env()

    # Thresholds de qualidade (configuráveis via env).
    FRESHNESS_STALE_DAYS = _env_int("DQ_FRESHNESS_STALE_DAYS", 14)
    FRESHNESS_CRITICAL_FAILURES = _env_int("DQ_FRESHNESS_CRITICAL_FAILURES", 3)
    VOLUME_DROP_DEGRADED_PCT = _env_int("DQ_VOLUME_DROP_DEGRADED_PCT", 20)
    VOLUME_DROP_CRITICAL_PCT = _env_int("DQ_VOLUME_DROP_CRITICAL_PCT", 50)
    QUARANTINE_CRITICAL_RUNS = _env_int("DQ_QUARANTINE_CRITICAL_RUNS", 3)
    QUARANTINE_LOOKBACK_DAYS = _env_int("DQ_QUARANTINE_LOOKBACK_DAYS", 30)
    SCORE_HEALTHY_MIN = _env_int("DQ_SCORE_HEALTHY_MIN", 80)
    SCORE_DEGRADED_MIN = _env_int("DQ_SCORE_DEGRADED_MIN", 50)
    ALERTS_ENABLED = os.getenv("DQ_ALERTS_ENABLED", "true").lower() == "true"

    # Status terminais de um run (exclui queued/running).
    _TERMINAL_STATUSES: frozenset[str] = frozenset({"success", "partial", "error"})

    # Pesos das dimensões no score 0-100 e mapeamento status→pontos.
    _CHECK_WEIGHTS: dict[str, float] = {
        "freshness": 0.4,
        "volume": 0.3,
        "schema_drift": 0.15,
        "quarantine": 0.15,
    }
    _CHECK_SCORES: dict[str, int] = {"healthy": 100, "degraded": 60, "critical": 20}

    ALLOWED_TABLES: frozenset[str] = frozenset(
        {
            "planos",
            "eixos",
            "programas",
            "acoes",
            "metas",
            "indicadores",
            "recursos",
            "evidencias",
            "fontes",
            "vinculos_evidencia",
            "instituicoes",
            "avaliacoes",
            "eventos",
            "acoes_instituicoes",
        }
    )

    _SCHEMA_RULES: dict[
        str,
        tuple[
            type[Any],
            str,
            list[tuple[str, str, ValidationSeverity, bool]],
        ],
    ] = {
        "planos": (
            Plano,
            "Plano",
            [
                ("nome", "nome", ValidationSeverity.ERROR, True),
                ("versao", "versão", ValidationSeverity.ERROR, True),
                ("ano_referencia", "ano de referência", ValidationSeverity.ERROR, False),
            ],
        ),
        "eixos": (
            Eixo,
            "Eixo",
            [
                ("plano_id", "plano_id", ValidationSeverity.ERROR, False),
                ("numero", "número", ValidationSeverity.ERROR, False),
                ("nome", "nome", ValidationSeverity.ERROR, True),
            ],
        ),
        "programas": (
            Programa,
            "Programa",
            [
                ("eixo_id", "eixo_id", ValidationSeverity.ERROR, False),
                ("nome", "nome", ValidationSeverity.ERROR, True),
            ],
        ),
        "acoes": (
            Acao,
            "Ação",
            [
                ("programa_id", "programa_id", ValidationSeverity.ERROR, False),
                ("nome", "nome", ValidationSeverity.ERROR, True),
            ],
        ),
        "metas": (
            Meta,
            "Meta",
            [
                ("acao_id", "acao_id", ValidationSeverity.ERROR, False),
                ("descricao", "descrição", ValidationSeverity.ERROR, True),
                ("tipo", "tipo", ValidationSeverity.ERROR, False),
            ],
        ),
        "indicadores": (
            Indicador,
            "Indicador",
            [
                ("meta_id", "meta_id", ValidationSeverity.ERROR, False),
                ("nome", "nome", ValidationSeverity.ERROR, True),
                ("tipo", "tipo", ValidationSeverity.ERROR, False),
            ],
        ),
        "recursos": (
            Recurso,
            "Recurso",
            [
                ("acao_id", "acao_id", ValidationSeverity.ERROR, False),
            ],
        ),
        "evidencias": (
            Evidencia,
            "Evidência",
            [
                ("fonte_id", "fonte_id", ValidationSeverity.ERROR, False),
                ("tipo", "tipo", ValidationSeverity.ERROR, False),
            ],
        ),
        "fontes": (
            Fonte,
            "Fonte",
            [
                ("url", "URL", ValidationSeverity.ERROR, True),
                ("data_coleta", "data de coleta", ValidationSeverity.WARNING, False),
            ],
        ),
        "vinculos_evidencia": (
            VinculoEvidencia,
            "Vínculo de Evidência",
            [
                ("evidencia_id", "evidencia_id", ValidationSeverity.ERROR, False),
                ("acao_id", "acao_id", ValidationSeverity.ERROR, False),
            ],
        ),
        "instituicoes": (
            Instituicao,
            "Instituição",
            [
                ("sigla", "sigla", ValidationSeverity.ERROR, True),
                ("nome", "nome", ValidationSeverity.ERROR, True),
            ],
        ),
        "avaliacoes": (
            Avaliacao,
            "Avaliação",
            [
                ("acao_id", "acao_id", ValidationSeverity.ERROR, False),
                ("status_avaliado", "status avaliado", ValidationSeverity.ERROR, False),
                ("justificativa", "justificativa", ValidationSeverity.ERROR, True),
                ("data_avaliacao", "data de avaliação", ValidationSeverity.ERROR, False),
            ],
        ),
        "eventos": (
            Evento,
            "Evento",
            [
                ("acao_id", "acao_id", ValidationSeverity.ERROR, False),
                ("tipo", "tipo", ValidationSeverity.ERROR, False),
                ("descricao", "descrição", ValidationSeverity.ERROR, True),
                ("data_evento", "data do evento", ValidationSeverity.ERROR, False),
            ],
        ),
        "acoes_instituicoes": (
            AcaoInstituicao,
            "Ação-Instituição",
            [
                ("acao_id", "acao_id", ValidationSeverity.ERROR, False),
                ("instituicao_id", "instituicao_id", ValidationSeverity.ERROR, False),
                ("papel", "papel", ValidationSeverity.ERROR, True),
            ],
        ),
    }

    @staticmethod
    async def run_full_validation() -> ValidationResult:
        """Executa todas as validações de qualidade e retorna resultado.

        Returns:
            ValidationResult com todas as violações encontradas.
        """
        violations: list[ValidationViolation] = []

        violations.extend(await DataQualityService._validate_schema())
        violations.extend(await DataQualityService._validate_referential_integrity())
        violations.extend(await DataQualityService._validate_consistency())
        violations.extend(await DataQualityService._validate_actions_without_status())

        errors = sum(1 for v in violations if v.severity == ValidationSeverity.ERROR)
        warnings = sum(1 for v in violations if v.severity == ValidationSeverity.WARNING)
        info_count = sum(1 for v in violations if v.severity == ValidationSeverity.INFO)

        summary: dict[str, object] = {
            "total_entities_checked": (await DataQualityService._count_all_entities()),
            "validation_rules_applied": [
                "schema_required_fields",
                "referential_integrity",
                "budget_consistency",
                "actions_without_status",
            ],
        }

        return ValidationResult(
            ran_at=datetime.now(),
            total_violations=len(violations),
            errors=errors,
            warnings=warnings,
            info=info_count,
            violations=violations,
            summary=summary,
        )

    @staticmethod
    async def _validate_schema() -> list[ValidationViolation]:
        """Valida campos obrigatórios em todas as entidades de ALLOWED_TABLES.

        Itera sobre _SCHEMA_RULES para verificar campos não nulos
        em todas as tabelas permitidas, garantindo cobertura
        sistemática da integridade de dados.

        Returns:
            Lista de violações encontradas.
        """
        violations: list[ValidationViolation] = []

        async with get_session() as session:
            for table_key, (
                model,
                display_name,
                fields,
            ) in DataQualityService._SCHEMA_RULES.items():
                for col_name, label, severity, check_empty in fields:
                    col = getattr(model, col_name)
                    where_clause = (col.is_(None)) | (col == "") if check_empty else col.is_(None)
                    result = await session.execute(select(model).where(where_clause))
                    for entity in result.scalars():
                        entity_id = DataQualityService._get_entity_id(entity, table_key)
                        violations.append(
                            ValidationViolation(
                                rule="schema_required_fields",
                                severity=severity,
                                entity=table_key,
                                entity_id=entity_id,
                                message=(
                                    f"{display_name}"
                                    f" '{entity_id}'"
                                    f" não possui"
                                    f" '{label}'"
                                    f" obrigatório(a)"
                                ),
                            )
                        )

        return violations

    @staticmethod
    def _get_entity_id(
        entity: Any,
        table_key: str,
    ) -> str:
        """Retorna ID da entidade, tratando PKs compostas.

        Args:
            entity: Instância do modelo ORM.
            table_key: Nome da tabela em ALLOWED_TABLES.

        Returns:
            String identificadora da entidade.
        """
        if table_key == "acoes_instituicoes":
            return f"{entity.acao_id}:{entity.instituicao_id}"
        return str(entity.id)

    @staticmethod
    async def _validate_table_fks_batch(
        session: AsyncSession,
        violations: list[ValidationViolation],
        source_model: type[Any],
        table_key: str,
        fk_map: dict[str, tuple[str, str]],
        model_map: dict[str, type[Any]],
    ) -> None:
        """Valida todas as FKs de uma tabela em uma única query.

        Usa NOT EXISTS com subqueries correlacionadas combinadas via OR
        para encontrar todas as FKs inválidas de uma tabela fonte em
        uma única query SQL, evitando N+1 queries.

        Args:
            session: Sessão assíncrona do SQLAlchemy.
            violations: Lista de violações a acumular.
            source_model: Modelo da tabela que contém as FKs.
            table_key: Nome da tabela para as violações.
            fk_map: Mapeamento de {coluna_FK: (nome_FK, tabela_ref)}.
            model_map: Mapeamento de nome_tabela -> modelo ORM.
        """
        if not fk_map:
            return

        conditions: list[Any] = []
        fk_cols_info: list[tuple[str, Any, type[Any]]] = []

        for fk_col_name, (fk_label, ref_table_name) in fk_map.items():
            ref_model = model_map.get(ref_table_name)
            if not ref_model:
                continue

            fk_col = getattr(source_model, fk_col_name)
            ref_id = getattr(ref_model, "id")

            # Create a proper correlated subquery that checks if the FK value exists
            # Use EXISTS with proper correlation to avoid false positives
            subquery = select(ref_id).where(ref_id == fk_col).correlate(source_model).exists()
            conditions.append(~subquery)
            fk_cols_info.append((fk_label, fk_col, ref_model))

        if not conditions:
            return

        result = await session.execute(
            select(source_model.id, *[fk for _, fk, _ in fk_cols_info]).where(or_(*conditions))
        )

        for row in result:
            entity_id = row[0]
            for i, (fk_label, _, ref_model) in enumerate(fk_cols_info):
                fk_val = row[i + 1]
                if fk_val is not None:
                    # The correlated subquery already verified this FK is invalid,
                    # so we can safely create the violation
                    violations.append(
                        ValidationViolation(
                            rule="referential_integrity",
                            severity=ValidationSeverity.ERROR,
                            entity=table_key,
                            entity_id=str(entity_id),
                            message=(
                                f"{table_key} '{entity_id}' referencia "
                                f"{fk_label} '{fk_val}' inexistente"
                            ),
                        )
                    )

    @staticmethod
    async def _validate_model_fks(
        session: AsyncSession,
        violations: list[ValidationViolation],
        fk_checks: list[tuple[str, str, str, str]],
    ) -> None:
        """Valida FKs agrupando por tabela fonte em queries consolidadas.

        Agrupa as verificações por tabela fonte e executa uma única query
        com NOT EXISTS para cada tabela, evitando N+1 queries.

        Args:
            session: Sessão assíncrona do SQLAlchemy.
            violations: Lista de violações a acumular.
            fk_checks: Lista de tuplas (entity_model, fk_name, ref_table, table_key).
        """
        entity_model_map: dict[str, type[Any]] = {
            "eixos": Eixo,
            "programas": Programa,
            "acoes": Acao,
            "metas": Meta,
            "indicadores": Indicador,
            "recursos": Recurso,
            "evidencias": Evidencia,
            "avaliacoes": Avaliacao,
            "eventos": Evento,
        }

        by_source: dict[str, dict[str, tuple[str, str]]] = {}
        for (
            _entity_key,
            fk_name,
            ref_table_name,
            table_key,
        ) in fk_checks:
            if ref_table_name not in entity_model_map:
                continue

            model = entity_model_map.get(table_key)
            if not model:
                continue

            if table_key not in by_source:
                by_source[table_key] = {}
            by_source[table_key][fk_name] = (fk_name, ref_table_name)

        for table_key, fk_map in by_source.items():
            model = entity_model_map[table_key]
            await DataQualityService._validate_table_fks_batch(
                session, violations, model, table_key, fk_map, entity_model_map
            )

    @staticmethod
    async def _validate_vinculo_fks(
        session: AsyncSession,
        violations: list[ValidationViolation],
    ) -> None:
        """Valida FKs de VinculoEvidencia em query consolidada.

        Args:
            session: Sessão assíncrona do SQLAlchemy.
            violations: Lista de violações a acumular.
        """
        vinc_model_map: dict[str, type[Any]] = {
            "evidencias": Evidencia,
            "acoes": Acao,
        }
        fk_map: dict[str, tuple[str, str]] = {
            "evidencia_id": ("evidencia_id", "evidencias"),
            "acao_id": ("acao_id", "acoes"),
        }
        await DataQualityService._validate_table_fks_batch(
            session, violations, VinculoEvidencia, "vinculos_evidencia", fk_map, vinc_model_map
        )

    @staticmethod
    async def _validate_ai_fks(
        session: AsyncSession,
        violations: list[ValidationViolation],
    ) -> None:
        """Valida FKs de AcaoInstituicao em query consolidada.

        Args:
            session: Sessão assíncrona do SQLAlchemy.
            violations: Lista de violações a acumular.
        """
        ai_model_map: dict[str, type[Any]] = {
            "acoes": Acao,
            "instituicoes": Instituicao,
        }
        fk_map: dict[str, tuple[str, str]] = {
            "acao_id": ("acao_id", "acoes"),
            "instituicao_id": ("instituicao_id", "instituicoes"),
        }
        await DataQualityService._validate_table_fks_batch(
            session, violations, AcaoInstituicao, "acoes_instituicoes", fk_map, ai_model_map
        )

    @staticmethod
    async def _count_table_fks_batch(
        session: AsyncSession,
        source_model: type[Any],
        fk_map: dict[str, tuple[str, str]],
        model_map: dict[str, type[Any]],
    ) -> int:
        """Conta FKs inválidas de uma tabela usando subqueries SQL.

        Args:
            session: Sessão assíncrona do SQLAlchemy.
            source_model: Modelo da tabela que contém as FKs.
            fk_map: Mapeamento de {coluna_FK: (nome_FK, tabela_ref)}.
            model_map: Mapeamento de nome_tabela -> modelo ORM.

        Returns:
            Número de FKs inválidas encontradas.
        """
        if not fk_map:
            return 0

        conditions: list[Any] = []

        for fk_col_name, (_fk_label, ref_table_name) in fk_map.items():
            ref_model = model_map.get(ref_table_name)
            if not ref_model:
                continue

            fk_col = getattr(source_model, fk_col_name)
            ref_id = getattr(ref_model, "id")

            subquery = select(ref_id).where(ref_id == fk_col).correlate(source_model).exists()
            conditions.append(~subquery)

        if not conditions:
            return 0

        result = await session.execute(
            select(func.count()).select_from(source_model).where(or_(*conditions))
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_invalid_fks(
        session: AsyncSession,
        source_model: type[Any],
        source_fk_col: Any,
        ref_model: type[Any],
    ) -> int:
        """Conta FKs inválidas usando subquery SQL eficiente.

        Args:
            session: Sessão assíncrona do SQLAlchemy.
            source_model: Modelo da tabela que contém a FK.
            source_fk_col: Coluna FK no source_model.
            ref_model: Modelo da tabela referenciada.

        Returns:
            Número de FKs inválidas encontradas.
        """
        ref_id = getattr(ref_model, "id")
        subquery = select(ref_id).where(ref_id == source_fk_col).correlate(source_model).exists()
        result = await session.execute(
            select(func.count()).select_from(source_model).where(~subquery)
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_referential_integrity_violations() -> int:
        """Conta total de violações de integridade referencial via subqueries SQL.

        Retorna apenas o count, sem criar objetos ValidationViolation.
        Mais eficiente que _validate_referential_integrity() quando só
        o número é necessário.
        """
        async with get_session() as session:
            fk_checks: list[tuple[str, str, str, str]] = [
                ("eixos", "plano_id", "planos", "eixos"),
                ("programas", "eixo_id", "eixos", "programas"),
                ("acoes", "programa_id", "programas", "acoes"),
                ("metas", "acao_id", "acoes", "metas"),
                ("indicadores", "meta_id", "metas", "indicadores"),
                ("recursos", "acao_id", "acoes", "recursos"),
                ("evidencias", "fonte_id", "fontes", "evidencias"),
                ("avaliacoes", "acao_id", "acoes", "avaliacoes"),
                ("eventos", "acao_id", "acoes", "eventos"),
            ]

            count = 0
            entity_model_map: dict[str, type[Any]] = {
                "eixos": Eixo,
                "programas": Programa,
                "acoes": Acao,
                "metas": Meta,
                "indicadores": Indicador,
                "recursos": Recurso,
                "evidencias": Evidencia,
                "avaliacoes": Avaliacao,
                "eventos": Evento,
            }

            by_source: dict[str, dict[str, tuple[str, str]]] = {}
            for (
                _entity_key,
                fk_name,
                ref_table_name,
                table_key,
            ) in fk_checks:
                if ref_table_name not in entity_model_map:
                    continue
                if table_key not in by_source:
                    by_source[table_key] = {}
                by_source[table_key][fk_name] = (fk_name, ref_table_name)

            for table_key, fk_map in by_source.items():
                model = entity_model_map[table_key]
                count += await DataQualityService._count_table_fks_batch(
                    session, model, fk_map, entity_model_map
                )

            vinc_model_map: dict[str, type[Any]] = {
                "evidencias": Evidencia,
                "acoes": Acao,
            }
            vinc_fk_map: dict[str, tuple[str, str]] = {
                "evidencia_id": ("evidencia_id", "evidencias"),
                "acao_id": ("acao_id", "acoes"),
            }
            count += await DataQualityService._count_table_fks_batch(
                session, VinculoEvidencia, vinc_fk_map, vinc_model_map
            )

            ai_model_map: dict[str, type[Any]] = {
                "acoes": Acao,
                "instituicoes": Instituicao,
            }
            ai_fk_map: dict[str, tuple[str, str]] = {
                "acao_id": ("acao_id", "acoes"),
                "instituicao_id": ("instituicao_id", "instituicoes"),
            }
            count += await DataQualityService._count_table_fks_batch(
                session, AcaoInstituicao, ai_fk_map, ai_model_map
            )

        return count

    @staticmethod
    async def _validate_referential_integrity() -> list[ValidationViolation]:
        """Valida integridade referencial via subqueries SQL.

        Usa subqueries correlacionadas para encontrar FKs inválidas
        sem carregar todas as linhas na memória.
        """
        violations: list[ValidationViolation] = []

        async with get_session() as session:
            fk_checks: list[tuple[str, str, str, str]] = [
                ("eixos", "plano_id", "planos", "eixos"),
                ("programas", "eixo_id", "eixos", "programas"),
                ("acoes", "programa_id", "programas", "acoes"),
                ("metas", "acao_id", "acoes", "metas"),
                ("indicadores", "meta_id", "metas", "indicadores"),
                ("recursos", "acao_id", "acoes", "recursos"),
                ("evidencias", "fonte_id", "fontes", "evidencias"),
                ("avaliacoes", "acao_id", "acoes", "avaliacoes"),
                ("eventos", "acao_id", "acoes", "eventos"),
            ]

            await DataQualityService._validate_model_fks(session, violations, fk_checks)
            await DataQualityService._validate_vinculo_fks(session, violations)
            await DataQualityService._validate_ai_fks(session, violations)

        return violations

    @staticmethod
    async def _validate_consistency() -> list[ValidationViolation]:
        """Valida consistência orçamentária: execução vs meta do exercício.

        Compara a soma de ``valor_previsto`` agrupada por ``ano_referencia``
        com a meta configurada para o exercício (``BUDGET_TARGETS_BI``, em
        R$ bi, via env ``BUDGET_TARGETS_BI``). Exercícios sem meta configurada
        são ignorados — nada de valor hardcoded de R$ 23 bi.
        """
        violations: list[ValidationViolation] = []

        async with get_session() as session:
            result = await session.execute(
                select(
                    Recurso.ano_referencia,
                    func.sum(Recurso.valor_previsto),
                ).group_by(Recurso.ano_referencia)
            )

            for ano, total in result:
                if ano is None or total is None:
                    continue
                target = DataQualityService.BUDGET_TARGETS_BI.get(ano)
                if target is None:
                    continue

                total_bi = float(total) / 1e9
                diff_pct = abs(total_bi - target) / target * 100

                if diff_pct > 10:
                    violations.append(
                        ValidationViolation(
                            rule="budget_consistency",
                            severity=ValidationSeverity.WARNING,
                            entity="recursos",
                            entity_id=str(ano),
                            message=(
                                f"Total de recursos previstos para {ano} "
                                f"(R$ {total_bi:.2f} bi) desvia "
                                f"{diff_pct:.1f}% da meta do exercício "
                                f"(R$ {target} bi)"
                            ),
                            details={
                                "ano_referencia": ano,
                                "total_previsto": float(total),
                                "total_bi": total_bi,
                                "expected_bi": target,
                                "diff_pct": diff_pct,
                            },
                        )
                    )
                elif diff_pct > 5:
                    violations.append(
                        ValidationViolation(
                            rule="budget_consistency",
                            severity=ValidationSeverity.INFO,
                            entity="recursos",
                            entity_id=str(ano),
                            message=(
                                f"Total de recursos previstos para {ano} "
                                f"(R$ {total_bi:.2f} bi) desvia "
                                f"{diff_pct:.1f}% da meta do exercício"
                            ),
                            details={
                                "ano_referencia": ano,
                                "total_previsto": float(total),
                                "total_bi": total_bi,
                                "expected_bi": target,
                            },
                        )
                    )

        return violations

    @staticmethod
    async def _validate_actions_without_status() -> list[ValidationViolation]:
        """Valida que ações não ficam sem status definido."""
        violations: list[ValidationViolation] = []

        async with get_session() as session:
            result = await session.execute(
                select(Acao).where(Acao.status == StatusAcao.nao_iniciado)
            )
            acoes_sem_status = result.scalars().all()

            if acoes_sem_status:
                violations.append(
                    ValidationViolation(
                        rule="actions_without_status",
                        severity=ValidationSeverity.INFO,
                        entity="acoes",
                        entity_id=None,
                        message=(
                            f"{len(acoes_sem_status)} ação(ões) com status "
                            f"'nao_iniciado' — podem precisar de avaliação"
                        ),
                        details={
                            "count": len(acoes_sem_status),
                            "ids": [a.id for a in acoes_sem_status[:20]],
                        },
                    )
                )

        return violations

    @staticmethod
    async def _count_all_entities() -> dict[str, int]:
        """Conta todas as entidades do banco usando uma query única."""
        from sqlalchemy import union_all

        async with get_session() as session:
            models: list[tuple[type[Any], str]] = [
                (Plano, "planos"),
                (Eixo, "eixos"),
                (Programa, "programas"),
                (Acao, "acoes"),
                (Meta, "metas"),
                (Indicador, "indicadores"),
                (Recurso, "recursos"),
                (Evidencia, "evidencias"),
                (VinculoEvidencia, "vinculos"),
                (Instituicao, "instituicoes"),
                (Avaliacao, "avaliacoes"),
                (Evento, "eventos"),
                (Fonte, "fontes"),
            ]

            subqueries = [
                select(func.count().label(name)).select_from(model) for model, name in models
            ]
            combined = union_all(*subqueries)
            result = await session.execute(combined)
            rows = result.all()
            return {name: row[0] for (_, name), row in zip(models, rows)}

    @staticmethod
    async def get_freshness_info() -> list[DataFreshnessInfo]:
        """Obtém informação de frescor por fonte de dados."""
        async with get_session() as session:
            sources_result = await session.execute(
                select(
                    IngestionRun.source,
                    func.count(IngestionRun.id).label("total_runs"),
                ).group_by(IngestionRun.source)
            )
            source_rows = sources_result.all()

            source_names = [row[0] for row in source_rows]

            runs_by_source: dict[str, list[IngestionRun]] = {}
            if source_names:
                runs_result = await session.execute(
                    select(IngestionRun)
                    .where(IngestionRun.source.in_(source_names))
                    .order_by(IngestionRun.source, IngestionRun.started_at.asc())
                )
                for run in runs_result.scalars():
                    runs_by_source.setdefault(run.source, []).append(run)

            freshness_list: list[DataFreshnessInfo] = []
            today = date.today()

            for row in source_rows:
                source_name = row[0]
                total_runs = row[1]

                runs = runs_by_source.get(source_name, [])

                # "Última coleta" usa o último run com status terminal
                # (success/error); runs "running" não representam coleta concluída.
                terminal_runs = [run for run in runs if run.status in ("success", "error")]
                if terminal_runs:
                    last_run = terminal_runs[-1].started_at
                    last_run_date = last_run.date() if isinstance(last_run, datetime) else last_run
                    days_since = (today - last_run_date).days if last_run_date else None
                else:
                    last_run_date = None
                    days_since = None

                # Falhas consecutivas: apenas runs contíguos entre sucessos.
                # O contador é resetado a cada success e incrementado a cada error,
                # de forma que erros antigos separados por um sucesso não contam.
                consecutive_failures = 0
                for run in runs:
                    if run.status == "success":
                        consecutive_failures = 0
                    elif run.status == "error":
                        consecutive_failures += 1

                # Cadência declarada (issue #1103): periodicidade e
                # ultima_referencia persistidas no metadata_json do último run
                # terminal pelo scheduler (_cadence_metadata).
                cadence = _cadence_from_run(terminal_runs[-1] if terminal_runs else None)

                if consecutive_failures >= DataQualityService.FRESHNESS_CRITICAL_FAILURES:
                    status = "critical"
                elif (
                    days_since is not None and days_since > DataQualityService.FRESHNESS_STALE_DAYS
                ):
                    status = "stale"
                else:
                    status = "healthy"

                freshness_list.append(
                    DataFreshnessInfo(
                        source=source_name,
                        last_collection=last_run_date,
                        days_since_collection=days_since,
                        total_runs=total_runs,
                        consecutive_failures=consecutive_failures,
                        status=status,
                        periodicidade=cadence.get("periodicidade"),
                        ultima_referencia=cadence.get("ultima_referencia"),
                    )
                )

            if not freshness_list:
                freshness_list.append(
                    DataFreshnessInfo(
                        source="pbia",
                        last_collection=None,
                        days_since_collection=None,
                        total_runs=0,
                        consecutive_failures=0,
                        status="stale",
                    )
                )

            return freshness_list

    @staticmethod
    async def get_quality_metrics() -> DataQualityMetrics:
        """Retorna métricas agregadas de qualidade dos dados."""
        counts = await DataQualityService._count_all_entities()
        freshness = await DataQualityService.get_freshness_info()

        async with get_session() as session:
            status_result = await session.execute(
                select(Acao.status, func.count(Acao.id)).group_by(Acao.status)
            )
            acoes_por_status: dict[str, int] = {}
            for row in status_result:
                status_val = row[0]
                key = status_val.value if hasattr(status_val, "value") else str(status_val)
                acoes_por_status[key] = row[1]

            sem_status_result = await session.execute(
                select(func.count()).select_from(Acao).where(Acao.status == StatusAcao.nao_iniciado)
            )
            acoes_sem_status = sem_status_result.scalar() or 0

            valor_result = await session.execute(select(func.sum(Recurso.valor_previsto)))
            total_valor = valor_result.scalar()

        schema_violations_list = await DataQualityService._validate_schema()
        ri_violations_count = await DataQualityService._count_referential_integrity_violations()

        return DataQualityMetrics(
            total_planos=counts.get("planos", 0),
            total_eixos=counts.get("eixos", 0),
            total_programas=counts.get("programas", 0),
            total_acoes=counts.get("acoes", 0),
            total_metas=counts.get("metas", 0),
            total_indicadores=counts.get("indicadores", 0),
            total_recursos=counts.get("recursos", 0),
            total_evidencias=counts.get("evidencias", 0),
            total_vinculos=counts.get("vinculos", 0),
            acoes_por_status=acoes_por_status,
            acoes_sem_status=acoes_sem_status,
            total_valor_previsto=(float(total_valor) if total_valor is not None else None),
            freshness=freshness,
            referential_integrity_violations=ri_violations_count,
            schema_violations=len(schema_violations_list),
        )

    @staticmethod
    async def get_health_data_freshness() -> HealthDataFreshnessResponse:
        """Retorna health check de frescor dos dados."""
        freshness = await DataQualityService.get_freshness_info()

        statuses = [f.status for f in freshness]
        if "critical" in statuses:
            overall_status = "critical"
        elif "stale" in statuses:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        days_list = [
            f.days_since_collection for f in freshness if f.days_since_collection is not None
        ]
        overall_days = max(days_list) if days_list else None

        details = ""
        if overall_status == "critical":
            critical = [f.source for f in freshness if f.status == "critical"]
            details = f"Coleta com falhas consecutivas em: {', '.join(critical)}"
        elif overall_status == "stale":
            stale = [f.source for f in freshness if f.status == "stale"]
            details = f"Fontes desatualizadas: {', '.join(stale)}"
        else:
            details = "Todas as fontes estão com dados frescos"

        return HealthDataFreshnessResponse(
            status=overall_status,
            checked_at=datetime.now(),
            freshness=freshness,
            overall_days_since_latest=overall_days,
            details=details,
        )

    # ------------------------------------------------------------------
    # Checks por fonte + score por dataset (issue #1096)
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_runs_by_source() -> dict[str, list[IngestionRun]]:
        """Carrega todos os IngestionRun agrupados por fonte, ordenados por data.

        Returns:
            Mapeamento fonte → lista de runs em ordem cronológica.
        """
        runs_by_source: dict[str, list[IngestionRun]] = {}
        async with get_session() as session:
            result = await session.execute(
                select(IngestionRun).order_by(
                    IngestionRun.source,
                    IngestionRun.started_at.asc(),
                    IngestionRun.id.asc(),
                )
            )
            for run in result.scalars():
                runs_by_source.setdefault(run.source, []).append(run)
        return runs_by_source

    @staticmethod
    def _terminal_runs(runs: list[IngestionRun]) -> list[IngestionRun]:
        """Filtra runs com status terminal (success/partial/error)."""
        return [r for r in runs if r.status in DataQualityService._TERMINAL_STATUSES]

    @staticmethod
    def _normalize_severity(status: str) -> str:
        """Normaliza status de freshness (stale) para severidade (degraded)."""
        if status == "stale":
            return "degraded"
        return status

    @staticmethod
    def _compute_volume_check(runs: list[IngestionRun]) -> VolumeCheck:
        """Volume: itens do último run terminal vs último run de sucesso.

        Usa o último run de sucesso como baseline; erros/quarentenas recentes
        com zero itens aparecem como queda de volume.
        """
        terminal = DataQualityService._terminal_runs(runs)
        if not terminal:
            return VolumeCheck(
                items_fetched=0, previous_items=None, delta_pct=None, status="degraded"
            )

        current = terminal[-1]
        baseline: IngestionRun | None = None
        for run in reversed(terminal[:-1]):
            if run.status == "success":
                baseline = run
                break

        current_items = current.items_fetched or 0
        baseline_items = baseline.items_fetched if baseline else None
        delta_pct: float | None = None
        if baseline_items is not None and baseline_items > 0:
            delta_pct = round((current_items - baseline_items) / baseline_items * 100, 2)

        if baseline is None or baseline_items is None or baseline_items == 0:
            status = "healthy"
        elif delta_pct is not None and delta_pct < -DataQualityService.VOLUME_DROP_CRITICAL_PCT:
            status = "critical"
        elif delta_pct is not None and delta_pct < -DataQualityService.VOLUME_DROP_DEGRADED_PCT:
            status = "degraded"
        else:
            status = "healthy"

        return VolumeCheck(
            items_fetched=current_items,
            previous_items=baseline_items,
            delta_pct=delta_pct,
            status=status,
        )

    @staticmethod
    def _compute_schema_drift_check(runs: list[IngestionRun]) -> SchemaDriftCheck:
        """Drift de schema: parser_version mudou entre os dois últimos runs terminais."""
        terminal = DataQualityService._terminal_runs(runs)
        if not terminal:
            return SchemaDriftCheck(
                parser_version=None,
                previous_parser_version=None,
                drift_detected=False,
                status="degraded",
            )

        current = terminal[-1]
        previous = terminal[-2] if len(terminal) >= 2 else None

        current_pv = (current.metadata_json or {}).get(PARSER_VERSION_KEY)
        prev_pv = (previous.metadata_json or {}).get(PARSER_VERSION_KEY) if previous else None

        current_str = current_pv if isinstance(current_pv, str) else None
        prev_str = prev_pv if isinstance(prev_pv, str) else None
        drift = current_str is not None and prev_str is not None and current_str != prev_str

        return SchemaDriftCheck(
            parser_version=current_str,
            previous_parser_version=prev_str,
            drift_detected=drift,
            status="degraded" if drift else "healthy",
        )

    @staticmethod
    def _compute_quarantine_check(runs: list[IngestionRun]) -> QuarantineCheck:
        """Quarentena: runs partial recentes dentro do lookback configurado."""
        today = date.today()
        lookback = DataQualityService.QUARANTINE_LOOKBACK_DAYS
        recent_partial: list[IngestionRun] = []
        for run in runs:
            if run.status != "partial" or run.started_at is None:
                continue
            age_days = (today - run.started_at.date()).days
            if age_days <= lookback:
                recent_partial.append(run)

        last_reason: str | None = None
        for run in reversed(recent_partial):
            reason = (run.metadata_json or {}).get(QUARANTINE_REASON_KEY)
            if isinstance(reason, str) and reason:
                last_reason = reason
                break
            if run.error_message:
                last_reason = run.error_message
                break

        count = len(recent_partial)
        if count >= DataQualityService.QUARANTINE_CRITICAL_RUNS:
            status = "critical"
        elif count >= 1:
            status = "degraded"
        else:
            status = "healthy"

        return QuarantineCheck(
            recent_partial_runs=count,
            last_quarantine_reason=last_reason,
            status=status,
        )

    @staticmethod
    def _freshness_check(info: DataFreshnessInfo) -> FreshnessCheck:
        """Converte DataFreshnessInfo em FreshnessCheck com severidade normalizada."""
        return FreshnessCheck(
            last_collection=info.last_collection,
            days_since_collection=info.days_since_collection,
            consecutive_failures=info.consecutive_failures,
            status=DataQualityService._normalize_severity(info.status),
        )

    @staticmethod
    async def get_source_quality_checks() -> list[SourceQualityChecks]:
        """Checks de qualidade por fonte: volume, frescor, drift e quarentena.

        Returns:
            Lista de checks por fonte presente em ``ingestion_runs``.
        """
        freshness = await DataQualityService.get_freshness_info()
        runs_by_source = await DataQualityService._load_runs_by_source()

        checks: list[SourceQualityChecks] = []
        for info in freshness:
            runs = runs_by_source.get(info.source, [])
            checks.append(
                SourceQualityChecks(
                    source=info.source,
                    volume=DataQualityService._compute_volume_check(runs),
                    freshness=DataQualityService._freshness_check(info),
                    schema_drift=DataQualityService._compute_schema_drift_check(runs),
                    quarantine=DataQualityService._compute_quarantine_check(runs),
                )
            )
        return checks

    @staticmethod
    def _severity_from_score(score: int) -> str:
        """Mapeia score 0-100 em severidade (healthy/degraded/critical)."""
        if score >= DataQualityService.SCORE_HEALTHY_MIN:
            return "healthy"
        if score >= DataQualityService.SCORE_DEGRADED_MIN:
            return "degraded"
        return "critical"

    @staticmethod
    def _dataset_score(checks: SourceQualityChecks) -> DatasetQualityScore:
        """Combina os checks de um dataset em score 0-100 com severidade."""
        statuses: dict[str, str] = {
            "freshness": checks.freshness.status,
            "volume": checks.volume.status,
            "schema_drift": checks.schema_drift.status,
            "quarantine": checks.quarantine.status,
        }
        score = 0.0
        for category, weight in DataQualityService._CHECK_WEIGHTS.items():
            status = statuses[category]
            score += weight * DataQualityService._CHECK_SCORES.get(status, 0)

        score_int = round(score)
        return DatasetQualityScore(
            source=checks.source,
            score=score_int,
            severity=DataQualityService._severity_from_score(score_int),
            checks=checks,
        )

    @staticmethod
    async def get_quality_report() -> QualityReportResponse:
        """Relatório público de qualidade: score por fonte + checks detalhados.

        Returns:
            QualityReportResponse com score global e por dataset.
        """
        checks = await DataQualityService.get_source_quality_checks()
        datasets = [DataQualityService._dataset_score(c) for c in checks]

        overall_score = round(sum(d.score for d in datasets) / len(datasets)) if datasets else 0

        return QualityReportResponse(
            generated_at=datetime.now(),
            overall_score=overall_score,
            overall_severity=DataQualityService._severity_from_score(overall_score),
            datasets=datasets,
        )

    @staticmethod
    async def evaluate_alerts() -> list[QualityAlert]:
        """Retorna alertas ativos de qualidade de dados (configurável via env).

        Desabilitado quando ``DQ_ALERTS_ENABLED=false``. Gera no máximo um
        alerta por categoria por fonte, na severidade mais alta detectada.
        """
        if not DataQualityService.ALERTS_ENABLED:
            return []

        report = await DataQualityService.get_quality_report()
        alerts: list[QualityAlert] = []
        created_at = datetime.now()

        for dataset in report.datasets:
            source = dataset.source
            checks = dataset.checks
            candidates: list[tuple[str, str, str]] = []

            if checks.freshness.status == "critical":
                candidates.append(
                    (
                        "critical",
                        "freshness",
                        (
                            f"Fonte '{source}': {checks.freshness.consecutive_failures} "
                            "falhas consecutivas de coleta — dados podem estar "
                            "desatualizados"
                        ),
                    )
                )
            elif checks.freshness.status == "degraded":
                candidates.append(
                    (
                        "degraded",
                        "freshness",
                        (
                            f"Fonte '{source}': última coleta há "
                            f"{checks.freshness.days_since_collection} dias"
                        ),
                    )
                )

            if checks.volume.status == "critical":
                candidates.append(
                    (
                        "critical",
                        "volume",
                        (
                            f"Fonte '{source}': volume caiu para "
                            f"{checks.volume.items_fetched} itens"
                            f" (variação {checks.volume.delta_pct}%)"
                        ),
                    )
                )
            elif checks.volume.status == "degraded":
                candidates.append(
                    (
                        "degraded",
                        "volume",
                        (
                            f"Fonte '{source}': queda de volume para "
                            f"{checks.volume.items_fetched} itens"
                            f" (variação {checks.volume.delta_pct}%)"
                        ),
                    )
                )

            if checks.schema_drift.drift_detected:
                candidates.append(
                    (
                        "degraded",
                        "schema_drift",
                        (
                            f"Fonte '{source}': parser_version mudou de "
                            f"'{checks.schema_drift.previous_parser_version}' para "
                            f"'{checks.schema_drift.parser_version}' — possível "
                            "mudança de schema"
                        ),
                    )
                )

            if checks.quarantine.status == "critical":
                candidates.append(
                    (
                        "critical",
                        "quarantine",
                        (
                            f"Fonte '{source}': {checks.quarantine.recent_partial_runs} "
                            "runs em quarentena recentemente"
                        ),
                    )
                )
            elif checks.quarantine.status == "degraded":
                candidates.append(
                    (
                        "degraded",
                        "quarantine",
                        (
                            f"Fonte '{source}': {checks.quarantine.recent_partial_runs} "
                            "run(s) em quarentena"
                        ),
                    )
                )

            for severity, category, message in candidates:
                alerts.append(
                    QualityAlert(
                        id=f"{severity}:{category}:{source}",
                        severity=severity,
                        category=category,
                        source=source,
                        message=message,
                        created_at=created_at,
                    )
                )

        return alerts

    @staticmethod
    async def send_alerts_via_telegram() -> bool:
        """Envia alertas ativos via Telegram (integração com Notifier existente).

        No-op quando o Telegram não está configurado ou não há alertas ativos.
        Para agendamento periódico, chame a partir do scheduler/CLI.

        Returns:
            True se a notificação foi enviada.
        """
        from src.collector.notification import Notifier

        notifier = Notifier.from_env()
        if not notifier.enabled:
            return False
        alerts = await DataQualityService.evaluate_alerts()
        if not alerts:
            return False
        return await notifier.notify_alerts(alerts)
