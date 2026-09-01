"""Regras de negócio para cálculo de status — IA Brasil.

Implementa as regras da taxonomia de status conforme CONTEXT.md §10:
- Não iniciado: Nenhuma evidência pública confiável de execução encontrada
- Sinalizado: Há anúncio ou intenção, mas sem ato ou entrega concreta
- Em andamento: Evidência de execução material (edital, contratação, lançamento parcial)
- Parcialmente entregue: Parte mensurável da meta cumprida, mas não o todo
- Entregue: Evidência robusta e suficiente de cumprimento da meta
- Inconclusivo: Evidências insuficientes, vagas ou sem vinculação segura
- Contraditório: Fontes públicas apontando conclusões incompatíveis
- Descontinuado: Revogação, suspensão ou abandono explícito

Cada regra é uma função pura que recebe evidências e retorna status + justificativa.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from src.core.db import StatusAcao, TipoEvidencia


@dataclass
class RuleResult:
    """Resultado da aplicação de uma regra de scoring."""

    status: StatusAcao
    confidence: float
    justification: str
    rules_applied: list[str] = field(default_factory=list)


@dataclass
class EvidenceInfo:
    """Informação simplificada de uma evidência para uso nas regras."""

    id: str
    tipo: TipoEvidencia
    trecho: str | None
    resumo: str | None
    data_evidencia: date | None
    confianca: float | None
    fonte_tipo_documental: str | None = None


PESOS_EVIDENCIA: dict[TipoEvidencia, float] = {
    TipoEvidencia.ato_oficial: 1.0,
    TipoEvidencia.edital: 1.0,
    TipoEvidencia.relatorio: 0.9,
    TipoEvidencia.pagina_institucional: 0.8,
    TipoEvidencia.noticia: 0.6,
    TipoEvidencia.ato_normativo: 0.3,
    TipoEvidencia.outro: 0.5,
}

# Versão das regras de scoring. Registrada na avaliação (via AuditLog.extra_data)
# e incluída no fingerprint de idempotência: mudanças metodológicas aqui devem
# incrementar esta versão para invalidar avaliações anteriores.
RULE_VERSION: str = "1.0.0"

# Tipos de evidência NORMATIVOS: documentos que apenas preveem/instituem a ação
# (ex.: o próprio documento do plano PBIA), sem comprovar execução material.
# Não elevam status de execução — ações com apenas esse tipo ficam nao_iniciado.
TIPOS_NORMATIVOS: set[TipoEvidencia] = {TipoEvidencia.ato_normativo}

# Palavras-chave de descontinuação explícita: revogação, suspensão,
# cancelamento, abandono ou desativação da ação. Somente com esse tipo de
# indicação o prazo vencido leva ao status descontinuado (issue #1080).
PALAVRAS_DESCONTINUACAO: tuple[str, ...] = (
    "suspens",
    "revogad",
    "cancelad",
    "abandonad",
    "descontinuad",
    "desativad",
    "extint",
)


def _peso_efetivo(evidencia: EvidenceInfo) -> float:
    """Peso efetivo de uma evidência: peso do tipo calibrado pela confiança.

    A confiança registrada pelo coletor (0.0-1.0) modula o peso do tipo
    (peso_tipo * confianca). Quando a confiança não foi calibrada (None),
    usa-se apenas o peso do tipo (confiança implícita 1.0).
    """
    base = PESOS_EVIDENCIA.get(evidencia.tipo, 0.5)
    if evidencia.confianca is None:
        return base
    return base * evidencia.confianca


def _media_confianca(evidencias: list[EvidenceInfo]) -> float:
    """Confiança média (peso efetivo) das evidências."""
    if not evidencias:
        return 0.0
    return sum(_peso_efetivo(e) for e in evidencias) / len(evidencias)


def rule_sem_evidencias(evidencias: list[EvidenceInfo]) -> RuleResult | None:
    """Regra: sem evidências vinculadas → Não iniciado.

    Args:
        evidencias: Lista de evidências vinculadas à ação.

    Returns:
        RuleResult com status nao_iniciado, ou None se não se aplica.
    """
    if len(evidencias) == 0:
        return RuleResult(
            status=StatusAcao.nao_iniciado,
            confidence=0.95,
            justification="Nenhuma evidência pública confiável de execução encontrada.",
            rules_applied=["sem_evidencias"],
        )
    return None


def rule_sinalizado(evidencias: list[EvidenceInfo]) -> RuleResult | None:
    """Regra: apenas notícias ou páginas institucionais → Sinalizado.

    Args:
        evidencias: Lista de evidências vinculadas à ação.

    Returns:
        RuleResult com status sinalizado, ou None se não se aplica.
    """
    if not evidencias:
        return None
    tipos = {e.tipo for e in evidencias}
    tipos_leves = {TipoEvidencia.noticia, TipoEvidencia.pagina_institucional, TipoEvidencia.outro}
    if tipos.issubset(tipos_leves):
        return RuleResult(
            status=StatusAcao.sinalizado,
            confidence=0.7,
            justification=(
                "Há anúncio ou intenção, mas sem ato ou entrega concreta. "
                f"Evidências do tipo: {[e.tipo.value for e in evidencias]}"
            ),
            rules_applied=["somente_noticias"],
        )
    return None


def rule_em_andamento(evidencias: list[EvidenceInfo]) -> RuleResult | None:
    """Regra: evidência oficial (ato, edital, relatório) → Em andamento.

    Evidências normativas (TIPOS_NORMATIVOS, ex.: o documento do plano) NÃO
    contam como execução material e não elevam o status.

    Args:
        evidencias: Lista de evidências vinculadas à ação.

    Returns:
        RuleResult com status em_andamento, ou None se não se aplica.
    """
    if not evidencias:
        return None
    tipos_oficiais = {
        TipoEvidencia.ato_oficial,
        TipoEvidencia.edital,
        TipoEvidencia.relatorio,
    }
    evidencias_oficiais = [e for e in evidencias if e.tipo in tipos_oficiais]
    if evidencias_oficiais:
        tipos_str = [e.tipo.value for e in evidencias_oficiais]
        return RuleResult(
            status=StatusAcao.em_andamento,
            confidence=0.9 * _media_confianca(evidencias_oficiais),
            justification=(
                f"Evidência de execução material encontrada: {tipos_str}. "
                "Há indícios concretos de andamento."
            ),
            rules_applied=["evidencia_oficial"],
        )
    return None


def _tem_evidencia_descontinuacao(evidencias: list[EvidenceInfo]) -> bool:
    """Verifica se há evidência explícita de descontinuação da ação.

    Considera resumo/trecho de evidências com sinais de revogação, suspensão,
    cancelamento, abandono ou desativação. Sem essa evidência explícita, um
    prazo vencido sozinho NÃO caracteriza descontinuação (issue #1080).
    """
    for ev in evidencias:
        texto = " ".join(filter(None, [ev.resumo or "", ev.trecho or ""])).lower()
        if any(palavra in texto for palavra in PALAVRAS_DESCONTINUACAO):
            return True
    return False


def rule_prazo_expirado(
    evidencias: list[EvidenceInfo],
    prazo: date | None,
) -> RuleResult | None:
    """Regra: prazo vencido + evidência explícita de descontinuação → Descontinuado.

    Prazo vencido sozinho NÃO caracteriza descontinuação (issue #1080): a ação
    mantém o status base (ex.: em_andamento/sinalizado) com indicação de atraso
    aplicada por evaluate_status(). O status descontinuado exige evidência
    explícita de revogação, suspensão, cancelamento ou abandono.

    Args:
        evidencias: Lista de evidências vinculadas à ação.
        prazo: Data limite da ação.

    Returns:
        RuleResult com status descontinuado, ou None se não se aplica.
    """
    if not prazo or prazo >= date.today():
        return None
    if not _tem_evidencia_descontinuacao(evidencias):
        return None
    return RuleResult(
        status=StatusAcao.descontinuado,
        confidence=0.8,
        justification=(
            f"Prazo da ação ({prazo}) já expirou e há evidência explícita de "
            "descontinuação (revogação, suspensão, cancelamento ou abandono)."
        ),
        rules_applied=["prazo_expirado"],
    )


def _com_indicacao_atraso(result: RuleResult, prazo: date | None) -> RuleResult:
    """Anota o resultado com indicação de atraso quando o prazo já expirou.

    Prazo vencido sozinho não altera o status (issue #1080), mas deve ficar
    sinalizado na justificativa e nas regras aplicadas.
    """
    if not prazo or prazo >= date.today():
        return result
    if result.status == StatusAcao.descontinuado or "prazo_expirado" in result.rules_applied:
        return result
    return replace(
        result,
        justification=(
            f"{result.justification} Prazo da ação ({prazo.isoformat()}) já expirou "
            "— possível atraso."
        ),
        rules_applied=[*result.rules_applied, "prazo_expirado"],
    )


def rule_contraditorio(evidencias: list[EvidenceInfo]) -> RuleResult | None:
    """Regra: evidências com resumos contraditórios → Contraditório.

    Args:
        evidencias: Lista de evidências vinculadas à ação.

    Returns:
        RuleResult com status contraditorio, ou None se não se aplica.
    """
    if len(evidencias) < 2:
        return None
    contraditorios = [e for e in evidencias if e.resumo and "contradit" in e.resumo.lower()]
    if contraditorios:
        return RuleResult(
            status=StatusAcao.contraditoriro,
            confidence=0.8,
            justification=(
                "Fontes públicas apontam conclusões incompatíveis. "
                f"{len(contraditorios)} evidência(s) com indício de contradição."
            ),
            rules_applied=["evidencias_contraditorias"],
        )
    return None


def rule_inconclusivo(evidencias: list[EvidenceInfo]) -> RuleResult | None:
    """Regra: evidências insuficientes ou vagas → Inconclusivo.

    Args:
        evidencias: Lista de evidências vinculadas à ação.

    Returns:
        RuleResult com status inconclusivo, ou None se não se aplica.
    """
    if not evidencias:
        return None
    total_confianca = sum(PESOS_EVIDENCIA.get(e.tipo, 0.5) for e in evidencias)
    media_confianca = total_confianca / len(evidencias) if evidencias else 0
    if media_confianca < 0.6:
        return RuleResult(
            status=StatusAcao.inconclusivo,
            confidence=0.6,
            justification=(
                "Evidências insuficientes, vagas ou sem vinculação segura. "
                f"Confiança média: {media_confianca:.2f}"
            ),
            rules_applied=["evidencias_fracas"],
        )
    return None


def rule_financial_execution(
    evidencias: list[EvidenceInfo],
    execucao_financeira: dict[str, Any] | None = None,
) -> RuleResult | None:
    """Regra: execução financeira disponível → upgrade de status.

    Se valor_pago > 0 e razão > 50% → em_andamento
    Se valor_pago >= valor_previsto → parcialmente_entregue

    O denominador é o valor_previsto (Recurso do PBIA). Na ausência dele,
    usa o valor_empenhado (CGU) como proxy do orçamento comprometido.

    Args:
        evidencias: Lista de evidências vinculadas à ação.
        execucao_financeira: Dict com valor_pago, valor_empenhado e
            valor_previsto.

    Returns:
        RuleResult com status baseado na execução financeira, ou None.
    """
    if not execucao_financeira:
        return None

    pago = execucao_financeira.get("valor_pago", 0)
    previsto = execucao_financeira.get("valor_previsto", 0)
    if previsto <= 0:
        # Sem valor previsto no PBIA, usa o valor empenhado (comprometido)
        # como denominador da razão de execução.
        previsto = execucao_financeira.get("valor_empenhado", 0)

    if previsto <= 0 or pago <= 0:
        return None

    ratio = pago / previsto

    if ratio >= 0.95:
        return RuleResult(
            status=StatusAcao.parcialmente_entregue,
            confidence=0.75,
            justification=(
                f"Execução financeira indicando {ratio:.0%} de execução "
                f"(R$ {pago:,.2f} / R$ {previsto:,.2f})"
            ),
            rules_applied=["financial_execution"],
        )
    if ratio >= 0.5:
        return RuleResult(
            status=StatusAcao.em_andamento,
            confidence=0.7,
            justification=(
                f"Execução financeira parcial: {ratio:.0%} (R$ {pago:,.2f} / R$ {previsto:,.2f})"
            ),
            rules_applied=["financial_execution_partial"],
        )

    return None


def rule_official_panel(
    evidencias: list[EvidenceInfo],
    panel_status: str | None = None,
) -> RuleResult | None:
    """Regra: painel oficial do MCTI confirma status → atualiza.

    Se o painel oficial marca como entregue → entregue
    Se marca como em andamento → em_andamento

    Args:
        evidencias: Lista de evidências vinculadas à ação.
        panel_status: Status reportado pelo painel oficial.

    Returns:
        RuleResult com status do painel, ou None.
    """
    if not panel_status:
        return None

    status_lower = panel_status.lower()

    if status_lower in ("entregue", "concluido", "concluído", "deliveried"):
        return RuleResult(
            status=StatusAcao.entregue,
            confidence=0.95,
            justification=f"Painel oficial do MCTI confirma entrega: {panel_status}",
            rules_applied=["official_panel_confirmed"],
        )
    if status_lower in ("em_andamento", "em andamento", "em_execucao", "em execução", "iniciado"):
        return RuleResult(
            status=StatusAcao.em_andamento,
            confidence=0.85,
            justification="Painel oficial do MCTI indica execução em andamento",
            rules_applied=["official_panel_andamento"],
        )

    return None


# ---------------------------------------------------------------------------
# Pipeline de regras (ordem de prioridade)
# ---------------------------------------------------------------------------


def rule_government_report(evidencias: list[EvidenceInfo]) -> RuleResult | None:
    """Regra: resposta oficial do governo (ofício, relatório) → status confiável.

    Busca evidências de fontes com tipo_documental 'oficio_resposta' ou
    'relatorio_ministerial' e extrai keywords de status.
    """
    STATUS_KEYWORDS = {
        "entregue": ("entregue", "concluída", "concluído", "executado"),
        "parcialmente_entregue": (
            "parcialmente",
            "em execução",
            "em andamento",
            "iniciada",
            "seleção concluída",
        ),
    }

    for ev in evidencias:
        fonte_tipo = ev.fonte_tipo_documental or ""
        if fonte_tipo not in ("oficio_resposta", "relatorio_ministerial"):
            continue

        resumo_lower = (ev.resumo or "").lower()

        for status, keywords in STATUS_KEYWORDS.items():
            if any(kw in resumo_lower for kw in keywords):
                return RuleResult(
                    status=StatusAcao(status),
                    confidence=0.88,
                    justification=(
                        f"Resposta oficial do governo ({fonte_tipo}): {(ev.resumo or '')[:200]}"
                    ),
                    rules_applied=["government_report"],
                )

    return None


ALL_RULES: list[str] = [
    "rule_contraditorio",
    "rule_prazo_expirado",
    "rule_official_panel",
    "rule_government_report",
    "rule_sem_evidencias",
    "rule_em_andamento",
    "rule_sinalizado",
    "rule_inconclusivo",
    "rule_financial_execution",
]

RULE_FUNCTIONS: dict[str, object] = {
    "rule_contraditorio": rule_contraditorio,
    "rule_prazo_expirado": rule_prazo_expirado,
    "rule_official_panel": rule_official_panel,
    "rule_government_report": rule_government_report,
    "rule_sem_evidencias": rule_sem_evidencias,
    "rule_em_andamento": rule_em_andamento,
    "rule_sinalizado": rule_sinalizado,
    "rule_inconclusivo": rule_inconclusivo,
    "rule_financial_execution": rule_financial_execution,
}


def evaluate_status(
    evidencias: list[EvidenceInfo],
    prazo: date | None = None,
    execucao_financeira: dict[str, Any] | None = None,
    panel_status: str | None = None,
) -> RuleResult:
    """Avalia o status de uma ação aplicando todas as regras em ordem de prioridade.

    Ordem de prioridade:
    1. Contraditório (evidências incompatíveis)
    2. Prazo expirado com evidência explícita de descontinuação
    3. Painel oficial do MCTI (se disponível)
    4. Sem evidências → Não iniciado
    5. Em andamento (evidência oficial)
    6. Execução financeira (se disponível)
    7. Sinalizado (apenas notícias)
    8. Inconclusivo (fallback)

    Prazo vencido sozinho NÃO muda o status para descontinuado (issue #1080):
    o status base é mantido e a justificativa ganha indicação de atraso.

    Args:
        evidencias: Lista de evidências vinculadas à ação.
        prazo: Data limite da ação (opcional).
        execucao_financeira: Dict com valor_pago, valor_previsto e
            valor_empenhado (opcional).
        panel_status: Status do painel oficial do MCTI (opcional).

    Returns:
        RuleResult com o status avaliado e justificativa.
    """
    # Evidências normativas (ex.: o documento do plano) apenas preveem a ação e
    # NÃO comprovam execução material. Filtra-as antes de aplicar as regras para
    # que ações com apenas esse tipo de evidência fiquem nao_iniciado.
    evidencias_materiais = [e for e in evidencias if e.tipo not in TIPOS_NORMATIVOS]

    def _avaliar() -> RuleResult:
        # 1. Contraditório (prioridade máxima)
        result = rule_contraditorio(evidencias_materiais)
        if result:
            return result

        # 2. Prazo expirado (descontinuação exige evidência explícita)
        result = rule_prazo_expirado(evidencias_materiais, prazo)
        if result:
            return result

        # 3. Painel oficial do MCTI (alta confiança)
        result = rule_official_panel(evidencias_materiais, panel_status)
        if result:
            return result

        # 4. Resposta oficial do governo (ofício, relatório ministerial)
        result = rule_government_report(evidencias_materiais)
        if result:
            return result

        # 5. Sem evidências
        result = rule_sem_evidencias(evidencias_materiais)
        if result:
            return result

        # 6. Em andamento
        result = rule_em_andamento(evidencias_materiais)
        if result:
            return result

        # 7. Execução financeira
        result = rule_financial_execution(evidencias_materiais, execucao_financeira)
        if result:
            return result

        # 8. Sinalizado
        result = rule_sinalizado(evidencias_materiais)
        if result:
            return result

        # 9. Inconclusivo (fallback)
        result = rule_inconclusivo(evidencias_materiais)
        if result:
            return result

        # Fallback final: parcialmente entregue (evidências mistas com peso moderado)
        return RuleResult(
            status=StatusAcao.parcialmente_entregue,
            confidence=0.65,
            justification="Evidências de tipos misturados com peso moderado.",
            rules_applied=["fallback_parcial"],
        )

    return _com_indicacao_atraso(_avaliar(), prazo)
