"""IA Brasil — PBIA Ingestion.

Ingestão async das entidades parseadas no banco de dados.
Usa SQLAlchemy async ORM para persistência.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from src.modules.pbia_parser.utils import generate_deterministic_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import (
    Acao,
    AcaoInstituicao,
    Avaliacao,
    Eixo,
    Evento,
    Evidencia,
    Fonte,
    Indicador,
    Instituicao,
    Meta,
    Plano,
    Programa,
    Recurso,
    StatusAcao,
    TipoIndicador,
    TipoMeta,
    VinculoEvidencia,
)
from src.modules.pbia_parser.parser import parse_pbia_document
from src.modules.pbia_parser.schemas import (
    EntityCounts,
    IngestionReport,
    ParserError,
)


async def upsert_entity(
    session: AsyncSession,
    entity_class: type[Any],
    entity_id: str,
    data: dict[str, Any],
    exclude_fields: list[str] | None = None,
    **kwargs: Any,
) -> tuple[bool, Any]:
    """Upsert an entity with deduplication logic.

    Checks if entity exists, updates if it does, creates if it doesn't.

    Args:
        session: SQLAlchemy async session
        entity_class: The SQLAlchemy model class
        entity_id: The deterministic ID to check/create
        data: Dictionary of entity data
        exclude_fields: Fields to exclude from update
        **kwargs: Additional entity constructor arguments

    Returns:
        tuple: (is_new, entity) where is_new is True if created, False if updated
    """
    exclude_fields = exclude_fields or []

    # Check if entity already exists
    existing_entity = await session.get(entity_class, entity_id)

    if existing_entity:
        # Update existing entity
        # Note: We only update from data, not kwargs, because kwargs are only used for creation
        # The data should already contain the properly parsed values from the caller
        for key, value in data.items():
            if key in exclude_fields:
                continue
            if hasattr(existing_entity, key):
                setattr(existing_entity, key, value)
        return False, existing_entity

    # Create new entity
    entity_data = {"id": entity_id}
    # kwargs take precedence over data (e.g., for parsed dates)
    for key, value in kwargs.items():
        if hasattr(entity_class, key):
            entity_data[key] = value

    # Add fields from data only if not already set by kwargs
    for key, value in data.items():
        if key not in exclude_fields and hasattr(entity_class, key) and key not in entity_data:
            entity_data[key] = value

    new_entity = entity_class(**entity_data)
    session.add(new_entity)
    return True, new_entity


class PBIAIngestor:
    """Ingestor do PBIA no banco de dados.

    Responsável por persistir as entidades parseadas no banco
    usando SQLAlchemy async ORM.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self, entities: dict[str, Any], source_path: str) -> IngestionReport:
        """Ingere entidades no banco de dados.

        Args:
            entities: Dicionário com entidades parseadas
            source_path: Caminho do documento de origem

        Returns:
            IngestionReport com contagens de criados/atualizados por entidade
        """
        report = IngestionReport(
            source_document=str(source_path),
            ingested_at=date.today(),
        )

        try:
            # Ingerir na ordem correta para respeitar foreign keys
            # 1. Plano (raiz)
            report.plano = await self._ingest_plano(entities.get("plano", {}))

            # 2. Instituições (independentes)
            report.instituicao = await self._ingest_instituicoes(entities.get("instituicoes", []))

            # 3. Fontes (independentes)
            report.fonte = await self._ingest_fontes(entities.get("fontes", []))

            # 4. Eixos (dependem de Plano)
            report.eixo = await self._ingest_eixos(entities.get("eixos", []))

            # 5. Programas (dependem de Eixo)
            report.programa = await self._ingest_programas(entities.get("programas", []))

            # 6. Ações (dependem de Programa)
            report.acao = await self._ingest_acoes(entities.get("acoes", []))

            # 7. Metas (dependem de Ação)
            report.meta = await self._ingest_metas(entities.get("metas", []))

            # 8. Indicadores (dependem de Meta)
            report.indicador = await self._ingest_indicadores(entities.get("indicadores", []))

            # 9. Recursos (dependem de Ação)
            report.recurso = await self._ingest_recursos(entities.get("recursos", []))

            # 10. Evidências (dependem de Fonte)
            report.evidencia = await self._ingest_evidencias(entities.get("evidencias", []))

            # 11. Vinculos (dependem de Evidência e Ação/Formula)
            report.vinculos = await self._ingest_vinculos(entities.get("vinculos", []))

            # 12. Avaliações (dependem de Ação)
            report.avaliacao = await self._ingest_avaliacoes(entities.get("avaliacoes", []))

            # 13. Eventos (dependem de Ação)
            report.evento = await self._ingest_eventos(entities.get("eventos", []))

            # 14. Relação Ação-Instituição
            await self._ingest_acao_instituicao(entities.get("acoes_instituicoes", []))

            # 15. Eventos iniciais de seed (timeline)
            await self._seed_initial_events()

            await self.session.commit()

        except Exception as e:
            await self.session.rollback()
            report.errors.append(str(e))
            raise ParserError(f"Erro durante ingestão: {e}") from e

        return report

    async def _ingest_plano(self, plano_data: dict[str, Any]) -> EntityCounts:
        """Ingere ou atualiza Plano com deduplicação explícita."""
        counts = EntityCounts()

        if not plano_data:
            return counts

        # Gerar ID determinístico com base no nome e versão
        nome = plano_data.get("nome") or ""
        versao = plano_data.get("versao") or ""
        plano_id = generate_deterministic_id("pbia", nome, versao)

        # Prepare data with parsed values for update path
        parsed_plano_data = plano_data.copy()
        if "vigencia_inicio" in parsed_plano_data:
            parsed_plano_data["vigencia_inicio"] = self._parse_date(
                plano_data.get("vigencia_inicio")
            )
        if "vigencia_fim" in parsed_plano_data:
            parsed_plano_data["vigencia_fim"] = self._parse_date(plano_data.get("vigencia_fim"))

        # Usar lógica de upsert com deduplicação explícita
        is_new, _ = await upsert_entity(
            self.session,
            Plano,
            plano_id,
            parsed_plano_data,
            exclude_fields=["_source_ref"],
            nome=plano_data.get("nome", "PBIA"),
            versao=plano_data.get("versao", "1.0"),
            ano_referencia=plano_data.get("ano_referencia", 2025),
            fonte_url=plano_data.get("fonte_url"),
            vigencia_inicio=self._parse_date(plano_data.get("vigencia_inicio")),
            vigencia_fim=self._parse_date(plano_data.get("vigencia_fim")),
        )

        if is_new:
            counts.created += 1
        else:
            counts.updated += 1

        return counts

    async def _ingest_instituicoes(self, instituicoes_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Instituições com deduplicação explícita."""
        counts = EntityCounts()

        for data in instituicoes_data:
            if not data.get("sigla"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico com base na sigla
            instituicao_id = generate_deterministic_id("inst", data["sigla"])

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Instituicao,
                instituicao_id,
                data,
                exclude_fields=["_source_ref"],
                sigla=data.get("sigla"),
                nome=data.get("nome", ""),
                tipo=data.get("tipo"),
                url_oficial=data.get("url_oficial"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_fontes(self, fontes_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Fontes com deduplicação explícita."""
        counts = EntityCounts()

        for data in fontes_data:
            if not data.get("url"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico com base na URL
            fonte_id = generate_deterministic_id("fonte", data["url"])

            # Prepare data with parsed values for update path
            parsed_fonte_data = data.copy()
            if "data_publicacao" in parsed_fonte_data:
                parsed_fonte_data["data_publicacao"] = self._parse_date(data.get("data_publicacao"))
            if "data_coleta" in parsed_fonte_data:
                parsed_fonte_data["data_coleta"] = (
                    self._parse_date(data.get("data_coleta")) or date.today()
                )

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Fonte,
                fonte_id,
                parsed_fonte_data,
                exclude_fields=["_source_ref"],
                url=data["url"],
                titulo=data.get("titulo"),
                instituicao_emissora=data.get("instituicao_emissora"),
                tipo_documental=data.get("tipo_documental"),
                data_publicacao=self._parse_date(data.get("data_publicacao")),
                data_coleta=self._parse_date(data.get("data_coleta")) or date.today(),
                hash_conteudo=data.get("hash_conteudo"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_eixos(self, eixos_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Eixos."""
        counts = EntityCounts()

        # Obter o plano (assumimos que há apenas um)
        plano = await self._get_single_plano()
        if not plano:
            counts.skipped += len(eixos_data)
            return counts

        for data in eixos_data:
            if not data.get("nome"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            numero = data.get("numero") or 0
            nome_eixo = data.get("nome") or ""
            eixo_id = generate_deterministic_id("eixo", str(plano.id), str(numero), nome_eixo)

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Eixo,
                eixo_id,
                data,
                exclude_fields=["_source_ref"],
                plano_id=plano.id,
                numero=data.get("numero", 1),
                nome=data.get("nome"),
                descricao=data.get("descricao"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_programas(self, programas_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Programas."""
        counts = EntityCounts()

        for data in programas_data:
            if not data.get("nome") or not data.get("eixo_numero"):
                counts.skipped += 1
                continue

            # Obter o eixo pelo número
            eixo = await self._get_eixo_by_numero(data["eixo_numero"])
            if not eixo:
                counts.skipped += 1
                continue

            # Preparar nome para exibição e resolução posterior
            codigo = data.get("codigo") or ""
            nome_prog = data.get("nome") or ""
            nome_exibicao = f"{codigo} - {nome_prog}" if codigo else nome_prog

            # Gerar ID determinístico
            programa_id = generate_deterministic_id("prog", str(eixo.id), codigo, nome_prog)

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Programa,
                programa_id,
                data,
                exclude_fields=["_source_ref", "eixo_numero", "codigo"],
                eixo_id=eixo.id,
                nome=nome_exibicao,
                descricao=data.get("descricao"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_acoes(self, acoes_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Ações."""
        counts = EntityCounts()

        for data in acoes_data:
            if not data.get("nome"):
                counts.skipped += 1
                continue

            # Obter o programa (se houver código de programa)
            programa = None
            if data.get("programa_codigo"):
                programa = await self._resolve_programa(data["programa_codigo"])
            elif data.get("eixo_numero"):
                # Ação de impacto imediato (sem programa)
                eixo = await self._get_eixo_by_numero(data["eixo_numero"])
                if not eixo:
                    counts.skipped += 1
                    continue
                # Para ações sem programa, criamos um programa dummy
                programa_id = generate_deterministic_id("prog", "impact", str(eixo.id))
                programa = await self.session.get(Programa, programa_id)
                if not programa:
                    programa = Programa(
                        id=programa_id,
                        eixo_id=eixo.id,
                        nome="Impacto Imediato",
                    )
                    self.session.add(programa)
                    await self.session.flush()

            if not programa:
                # Ação sem programa conhecido - criar sob programa genérico do Eixo 1
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            base_id = programa.id if programa else "root"
            cod_oficial = data.get("codigo_oficial") or ""
            nome_acao = data.get("nome") or ""
            acao_id = generate_deterministic_id("acao", base_id, cod_oficial, nome_acao)

            # Prepare data with parsed values for update path
            parsed_acao_data = data.copy()
            if "prazo" in parsed_acao_data:
                parsed_acao_data["prazo"] = self._parse_date(data.get("prazo"))

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Acao,
                acao_id,
                parsed_acao_data,
                exclude_fields=["_source_ref", "programa_codigo", "eixo_numero"],
                programa_id=programa.id if programa else None,
                codigo_oficial=data.get("codigo_oficial"),
                nome=data.get("nome"),
                descricao=data.get("descricao"),
                status=data.get("status") or StatusAcao.nao_iniciado,
                prazo=self._parse_date(data.get("prazo")),
                trecho_original=data.get("trecho_original"),
                pagina_doc=data.get("pagina_doc"),
                extra=data.get("extra", {}),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_metas(self, metas_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Metas."""
        counts = EntityCounts()

        # Build lookup: codigo_oficial -> Acao UUID
        # O parser extrai metas com acao_id = codigo oficial (ex: '1', '2'),
        # mas o FK espera o UUID da tabela acoes.
        acao_lookup = await self._build_acao_lookup()

        for data in metas_data:
            if not data.get("descricao") or not data.get("acao_id"):
                counts.skipped += 1
                continue

            # Resolver acao_id de código oficial para UUID
            acao_id_oficial = data.get("acao_id") or ""
            acao_uuid = acao_lookup.get(acao_id_oficial)
            if not acao_uuid:
                counts.skipped += 1
                continue

            # Gerar ID determinístico usando o código oficial (para compatibilidade
            # com indicadores que usam o mesmo esquema de ID)
            desc_meta = data.get("descricao") or ""
            meta_id = generate_deterministic_id("meta", acao_id_oficial, desc_meta)

            # Substituir acao_id pelo UUID resolvido para que o upsert
            # atualize corretamente tanto registros novos quanto existentes.
            # O upsert_entity aplica kwargs apenas em criacoes, mas o
            # update de entidades existentes le os valores de data.
            data["acao_id"] = acao_uuid

            # Prepare data with parsed values for update path
            parsed_meta_data = data.copy()
            if "prazo" in parsed_meta_data:
                parsed_meta_data["prazo"] = self._parse_date(data.get("prazo"))

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Meta,
                meta_id,
                parsed_meta_data,
                exclude_fields=["_source_ref"],
                acao_id=acao_uuid,  # UUID resolvido do codigo oficial
                descricao=data.get("descricao"),
                tipo=data.get("tipo") or TipoMeta.qualitativa,
                alvo_valor=data.get("alvo_valor"),
                alvo_unidade=data.get("alvo_unidade"),
                prazo=self._parse_date(data.get("prazo")),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_indicadores(self, indicadores_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Indicadores."""
        counts = EntityCounts()

        for data in indicadores_data:
            if not data.get("nome") or not data.get("meta_id"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            meta_id_ind = data.get("meta_id") or ""
            nome_ind = data.get("nome") or ""
            indicador_id = generate_deterministic_id("ind", meta_id_ind, nome_ind)

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Indicador,
                indicador_id,
                data,
                exclude_fields=["_source_ref", "meta_id"],
                meta_id=data.get("meta_id"),
                nome=data.get("nome"),
                tipo=data.get("tipo") or TipoIndicador.resultado,
                linha_base=data.get("linha_base"),
                meta_valor=data.get("meta_valor"),
                unidade=data.get("unidade"),
                fonte_calculo=data.get("fonte_calculo"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_recursos(self, recursos_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Recursos."""
        counts = EntityCounts()

        # Build lookup: codigo_oficial -> Acao UUID
        # O parser extrai recursos com acao_id = codigo oficial (ex: '1', '2'),
        # mas o FK espera o UUID da tabela acoes.
        acao_lookup = await self._build_acao_lookup()

        for data in recursos_data:
            if not data.get("acao_id"):
                counts.skipped += 1
                continue

            # Resolver acao_id de código oficial para UUID
            acao_id_oficial = data.get("acao_id") or ""
            acao_uuid = acao_lookup.get(acao_id_oficial)
            if not acao_uuid:
                counts.skipped += 1
                continue

            # Gerar ID determinístico usando o código oficial
            fonte_rec = data.get("fonte") or ""
            natureza_rec = data.get("natureza") or ""
            recurso_id = generate_deterministic_id("rec", acao_id_oficial, fonte_rec, natureza_rec)

            # Substituir acao_id pelo UUID resolvido
            data["acao_id"] = acao_uuid

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Recurso,
                recurso_id,
                data,
                exclude_fields=["_source_ref"],
                acao_id=acao_uuid,  # UUID resolvido do codigo oficial
                valor_previsto=data.get("valor_previsto"),
                valor_executado=data.get("valor_executado"),
                fonte=data.get("fonte"),
                natureza=data.get("natureza"),
                ano_referencia=data.get("ano_referencia"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_evidencias(self, evidencias_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Evidências."""
        counts = EntityCounts()

        for data in evidencias_data:
            if not data.get("fonte_id") or not data.get("tipo"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            fonte_id_evid = data.get("fonte_id") or ""
            tipo_evid = data.get("tipo") or ""
            data_evid = data.get("data_evidencia") or ""
            evidencia_id = generate_deterministic_id("evid", fonte_id_evid, tipo_evid, data_evid)

            # Prepare data with parsed values for update path
            parsed_evidencia_data = data.copy()
            if "data_evidencia" in parsed_evidencia_data:
                parsed_evidencia_data["data_evidencia"] = self._parse_date(
                    data.get("data_evidencia")
                )

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Evidencia,
                evidencia_id,
                parsed_evidencia_data,
                exclude_fields=["_source_ref", "fonte_id"],
                fonte_id=data.get("fonte_id"),
                tipo=data.get("tipo"),
                trecho=data.get("trecho"),
                resumo=data.get("resumo"),
                data_evidencia=self._parse_date(data.get("data_evidencia")),
                confianca=data.get("confianca"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_vinculos(self, vinculos_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Vínculos entre Evidências e Ações/Metas."""
        counts = EntityCounts()

        for data in vinculos_data:
            if not data.get("evidencia_id") or not data.get("acao_id"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            evid_id = data.get("evidencia_id") or ""
            acao_id_vinc = data.get("acao_id") or ""
            meta_id_vinc = data.get("meta_id") or ""
            vinculo_id = generate_deterministic_id("vinc", evid_id, acao_id_vinc, meta_id_vinc)

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                VinculoEvidencia,
                vinculo_id,
                data,
                exclude_fields=["_source_ref", "evidencia_id", "acao_id", "meta_id"],
                evidencia_id=data.get("evidencia_id"),
                acao_id=data.get("acao_id"),
                meta_id=data.get("meta_id"),
                justificativa=data.get("justificativa"),
                criado_por=data.get("criado_por") or "pbia_parser",
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_avaliacoes(self, avaliacoes_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Avaliações."""
        counts = EntityCounts()

        for data in avaliacoes_data:
            if not data.get("acao_id") or not data.get("status_avaliado"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            acao_id_avl = data.get("acao_id") or ""
            data_avl = data.get("data_avaliacao") or ""
            versao_avl = data.get("versao") or ""
            avaliacao_id = generate_deterministic_id("avl", acao_id_avl, data_avl, versao_avl)

            # Prepare data with parsed values for update path
            parsed_avaliacao_data = data.copy()
            if "data_avaliacao" in parsed_avaliacao_data:
                parsed_avaliacao_data["data_avaliacao"] = (
                    self._parse_date(data.get("data_avaliacao")) or date.today()
                )

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Avaliacao,
                avaliacao_id,
                parsed_avaliacao_data,
                exclude_fields=["_source_ref", "acao_id"],
                acao_id=data.get("acao_id"),
                status_avaliado=data.get("status_avaliado"),
                justificativa=data.get("justificativa") or "",
                avaliado_por=data.get("avaliado_por") or "pbia_parser",
                data_avaliacao=self._parse_date(data.get("data_avaliacao")) or date.today(),
                versao=data.get("versao") or 1,
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_eventos(self, eventos_data: list[dict[str, Any]]) -> EntityCounts:
        """Ingere ou atualiza Eventos."""
        counts = EntityCounts()

        for data in eventos_data:
            if not data.get("acao_id") or not data.get("tipo") or not data.get("descricao"):
                counts.skipped += 1
                continue

            # Gerar ID determinístico
            acao_id_evt = data.get("acao_id") or ""
            tipo_evt = data.get("tipo") or ""
            data_evt = data.get("data_evento") or ""
            desc_evt = (data.get("descricao") or "")[:50]
            evento_id = generate_deterministic_id("evt", acao_id_evt, tipo_evt, data_evt, desc_evt)

            # Prepare data with parsed values for update path
            parsed_evento_data = data.copy()
            if "data_evento" in parsed_evento_data:
                parsed_evento_data["data_evento"] = (
                    self._parse_date(data.get("data_evento")) or date.today()
                )

            # Usar lógica de upsert com deduplicação explícita
            is_new, _ = await upsert_entity(
                self.session,
                Evento,
                evento_id,
                parsed_evento_data,
                exclude_fields=["_source_ref", "acao_id"],
                acao_id=data.get("acao_id"),
                tipo=data.get("tipo"),
                descricao=data.get("descricao"),
                data_evento=self._parse_date(data.get("data_evento")) or date.today(),
                fonte_url=data.get("fonte_url"),
            )

            if is_new:
                counts.created += 1
            else:
                counts.updated += 1

        return counts

    async def _ingest_acao_instituicao(self, acoes_instituicoes_data: list[dict[str, Any]]) -> None:
        """Ingere relações N:M entre Ação e Instituição.

        Aceita instituicao_id como sigla ou ID. Se for sigla, resolve para o ID
        deterministico usando generate_deterministic_id("inst", sigla).
        """
        for data in acoes_instituicoes_data:
            if not data.get("acao_id") or not data.get("instituicao_id") or not data.get("papel"):
                continue

            # Resolver instituicao_id: se for sigla (sem hifens, curto), converter para ID
            instituicao_id = data["instituicao_id"]
            # Se for uma sigla (curto, sem hifens de UUID), gerar ID deterministico
            if len(instituicao_id) <= 10 and "-" not in instituicao_id:
                # Provavelmente e uma sigla, converter para ID
                instituicao_id = generate_deterministic_id("inst", instituicao_id)

            # Verificar se já existe
            existing = await self.session.execute(
                select(AcaoInstituicao).where(
                    AcaoInstituicao.acao_id == data["acao_id"],
                    AcaoInstituicao.instituicao_id == instituicao_id,
                )
            )
            if existing.scalar_one_or_none():
                continue

            relacao = AcaoInstituicao(
                acao_id=data["acao_id"],
                instituicao_id=instituicao_id,
                papel=data["papel"],
            )
            self.session.add(relacao)

    async def _seed_initial_events(self) -> None:
        """Cria eventos iniciais e audit logs após a ingestão do seed.

        Gera eventos de timeline e registros de auditoria para refletir
        a importação inicial dos dados do PBIA. Ignora registros que já existem.
        """
        from sqlalchemy import select as sa_select

        from src.core.db import Acao, AuditLog, Evento, Plano

        today = date.today()

        plano_result = await self.session.execute(sa_select(Plano).limit(1))
        plano = plano_result.scalar_one_or_none()
        if plano:
            evento_id = generate_deterministic_id("evt", "plano", str(plano.id), "seed")
            if not await self.session.get(Evento, evento_id):
                plano_evento = Evento(
                    id=evento_id,
                    acao_id=None,
                    tipo="NOTA_EDITORIAL",
                    descricao=f"Plano '{plano.nome}' importado do documento oficial do PBIA",
                    data_evento=today,
                    referencia_id=str(plano.id),
                    referencia_tipo="plano",
                    criado_em=today,
                    fonte_url="https://pbia.cgee.org.br/documento-oficial",
                )
                self.session.add(plano_evento)

        acoes_result = await self.session.execute(sa_select(Acao))
        acoes = acoes_result.scalars().all()

        for acao in acoes:
            status_str = acao.status.value if hasattr(acao.status, "value") else str(acao.status)

            audit_id = generate_deterministic_id("audit", acao.id, "seed", str(today))
            if not await self.session.get(AuditLog, audit_id):
                audit = AuditLog(
                    id=audit_id,
                    acao_id=acao.id,
                    status_anterior=None,
                    status_novo=status_str,
                    justificativa="Status inicial definido pelo seed do PBIA 2025",
                    criado_por="pbia_seed",
                    data_criacao=today,
                    extra_data={},
                )
                self.session.add(audit)

            evento_id = generate_deterministic_id("evt", acao.id, "seed", acao.codigo_oficial or "")
            if not await self.session.get(Evento, evento_id):
                evento = Evento(
                    id=evento_id,
                    acao_id=acao.id,
                    tipo="STATUS_ALTERADO",
                    descricao=(
                        f"Ação '{acao.nome}' importada do PBIA 2025 — status inicial: {status_str}"
                    ),
                    data_evento=today,
                    referencia_id=acao.id,
                    referencia_tipo="acao",
                    criado_em=today,
                    fonte_url="https://pbia.cgee.org.br/documento-oficial",
                )
                self.session.add(evento)

    async def _build_acao_lookup(self) -> dict[str, str]:
        """Builds a lookup dict mapping codigo_oficial -> Acao UUID.

        This is needed because the parser extracts metas/recursos with
        acao_id as the official code number (e.g., '1', '2'), but the
        FK column ``acao_id`` on Meta/Recurso expects the UUID primary
        key from the ``acoes`` table.

        Returns:
            dict[str, str]: {codigo_oficial: acao_uuid, ...}
        """
        result = await self.session.execute(select(Acao.id, Acao.codigo_oficial))
        return {row.codigo_oficial: row.id for row in result}

    async def _get_single_plano(self) -> Plano | None:
        """Obtém o único plano do banco (assumimos um único plano ativo)."""
        result = await self.session.execute(select(Plano).limit(1))
        return result.scalar_one_or_none()

    async def _get_eixo_by_numero(self, numero: int) -> Eixo | None:
        """Obtém eixo pelo número."""
        result = await self.session.execute(select(Eixo).where(Eixo.numero == numero).limit(1))
        return result.scalar_one_or_none()

    async def _resolve_programa(self, codigo: str) -> Programa | None:
        """Resolve programa a partir do código informado.

        Busca pelo nome que contenha o código como substring.
        Retorna ``None`` se nenhum match.

        Args:
            codigo: Código do programa a resolver.

        Returns:
            Programa encontrado ou None.
        """
        result = await self.session.execute(
            select(Programa)
            .where(Programa.nome.ilike(f"%{codigo}%"))
            .order_by(Programa.nome)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_programa_by_codigo(self, codigo: str) -> Programa | None:
        """Alias manutenção: delega para ``_resolve_programa``.

        Mantido para compatibilidade com chamadores externos que ainda
        utilizam o nome antigo.
        """
        return await self._resolve_programa(codigo)

    @staticmethod
    def _parse_date(date_value: str | date | None) -> date | None:
        """Converte string para date."""
        if date_value is None:
            return None
        if isinstance(date_value, date):
            return date_value
        try:
            return date.fromisoformat(date_value)
        except (ValueError, TypeError):
            return None


def _load_institutions_fixture() -> dict[str, Any]:
    """Load the institutions fixture from tests/fixtures/pbia_instituicoes.json.

    Returns:
        Dict with 'instituicoes' and 'acoes_instituicoes' keys, or empty lists
        if the fixture file is not found.
    """
    fixture_path = (
        Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "pbia_instituicoes.json"
    )
    if not fixture_path.exists():
        return {"instituicoes": [], "acoes_instituicoes": []}
    with open(fixture_path, encoding="utf-8") as f:
        return cast("dict[str, Any]", json.load(f))


def _load_fontes_fixture() -> dict[str, Any]:
    """Load the fontes fixture from tests/fixtures/pbia_fontes.json.

    Returns:
        Dict with 'fontes' key, or empty list if the fixture file is not found.
    """
    fixture_path = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "pbia_fontes.json"
    if not fixture_path.exists():
        return {"fontes": []}
    with open(fixture_path, encoding="utf-8") as f:
        return cast("dict[str, Any]", json.load(f))


async def ingest_pbia(source_path: str | Path, session: AsyncSession) -> IngestionReport:
    """Função principal para ingerir o PBIA no banco de dados.

    Args:
        source_path: Caminho para o documento PBIA (PDF, JSON, YAML ou texto)
        session: Sessão async SQLAlchemy

    Returns:
        IngestionReport com contagens de criados/atualizados por entidade

    Raises:
        ParserError: Se o documento não puder ser parseado
    """
    entities = await asyncio.to_thread(parse_pbia_document, source_path)

    # Carregar fixture de instituicoes (dados estaticos nao extraiveis do PDF)
    institutions_fixture = _load_institutions_fixture()

    # Substituir/adicionar instituicoes do fixture (fonte de verdade para dados estaticos)
    if institutions_fixture.get("instituicoes"):
        fixture_inst_by_sigla = {
            inst["sigla"]: inst for inst in institutions_fixture["instituicoes"]
        }
        existing_inst = {i["sigla"]: i for i in entities.get("instituicoes", [])}

        # Substituir instituicoes existentes com os dados do fixture
        # (mantendo _source_ref se houver) e adicionar novas instituicoes do fixture
        merged_instituicoes = []
        for sigla, inst_data in existing_inst.items():
            if sigla in fixture_inst_by_sigla:
                # Usar dados do fixture, mas preservar _source_ref da entidade parseada se houver
                fixture_inst = fixture_inst_by_sigla[sigla].copy()
                if "_source_ref" in inst_data and "_source_ref" not in fixture_inst:
                    fixture_inst["_source_ref"] = inst_data["_source_ref"]
                merged_instituicoes.append(fixture_inst)
            else:
                merged_instituicoes.append(inst_data)

        # Adicionar instituicoes do fixture que nao estavam no parseado
        for sigla, inst_data in fixture_inst_by_sigla.items():
            if sigla not in existing_inst:
                merged_instituicoes.append(inst_data)

        entities["instituicoes"] = merged_instituicoes

    if institutions_fixture.get("acoes_instituicoes"):
        entities.setdefault("acoes_instituicoes", []).extend(
            institutions_fixture["acoes_instituicoes"]
        )

    # Carregar fixture de fontes (fonte principal do PBIA)
    fontes_fixture = _load_fontes_fixture()
    if fontes_fixture.get("fontes"):
        # Usar fontes do fixture como fonte de verdade
        # Se ja houver fontes parseadas, preserva-las, senao usa as do fixture
        if not entities.get("fontes"):
            entities["fontes"] = fontes_fixture["fontes"]

    # Ingerir no banco
    ingestor = PBIAIngestor(session)
    return await ingestor.ingest(entities, str(source_path))
