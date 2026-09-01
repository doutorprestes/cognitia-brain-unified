"""IA Brasil — Analytics Schemas.

Pydantic models para os 7 endpoints analíticos de valor.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Entrega 1: Boletim "Prometido vs. Realizado"
# ---------------------------------------------------------------------------


class StatusCount(BaseModel):
    """Contagem por status."""

    status: str
    quantidade: int
    percentual: float


class EixoBreakdown(BaseModel):
    """Breakdown de ações por eixo."""

    eixo: str
    total: int
    entregues: int
    em_andamento: int
    parcialmente_entregue: int
    nao_iniciado: int


class BoletimResponse(BaseModel):
    """Resposta do boletim executivo."""

    total_acoes: int
    por_status: list[StatusCount]
    por_eixo: list[EixoBreakdown]
    percentual_execucao: float = Field(..., description="% de ações entregues")
    data_geracao: str


# ---------------------------------------------------------------------------
# Entrega 2: Execução Financeira
# ---------------------------------------------------------------------------


class ExecucaoEixo(BaseModel):
    """Execução financeira por eixo."""

    eixo: str
    previsto: float
    empenhado: float
    liquidado: float
    pago: float


class ExecucaoPorAno(BaseModel):
    """Execução financeira por exercício (ano)."""

    ano: int
    total_previsto: float
    total_empenhado: float
    total_liquidado: float
    total_pago: float


class ExecucaoFinanceiraResponse(BaseModel):
    """Resposta da execução financeira analítica."""

    total_previsto: float
    total_empenhado: float
    total_liquidado: float
    total_pago: float
    ratio_empenhado_previsto: float = Field(..., description="Empenhado / Previsto")
    ratio_pago_empenhado: float = Field(..., description="Pago / Empenhado")
    por_eixo: list[ExecucaoEixo]
    por_ano: list[ExecucaoPorAno] = Field(default_factory=list, description="Por exercício")


# ---------------------------------------------------------------------------
# Entrega 3: Hierarquia de Evidências
# ---------------------------------------------------------------------------


class TipoEvidenciaPeso(BaseModel):
    """Tipo de evidência com peso e base jurídica."""

    tipo: str
    peso: float
    descricao: str
    base_juridica: str


class DistribuicaoEvidencia(BaseModel):
    """Distribuição real de evidências por tipo."""

    tipo: str
    quantidade: int
    percentual: float


class HierarquiaResponse(BaseModel):
    """Resposta da hierarquia de evidências."""

    tipos: list[TipoEvidenciaPeso]
    distribuicao: list[DistribuicaoEvidencia]


# ---------------------------------------------------------------------------
# Entrega 4: Proveniência de Dados
# ---------------------------------------------------------------------------


class FonteInfo(BaseModel):
    """Informação de uma fonte de dados."""

    id: str
    url: str | None
    titulo: str
    tipo_documental: str
    data_coleta: str | None
    instituicao_emissora: str | None


class ProvenienciaResponse(BaseModel):
    """Resposta da proveniência de dados."""

    fontes: list[FonteInfo]
    total_fontes: int
    ultima_coleta: str | None


# ---------------------------------------------------------------------------
# Entrega 5: Auditoria Independente
# ---------------------------------------------------------------------------


class Contradicao(BaseModel):
    """Contradição encontrada entre fontes."""

    acao_id: str
    acao_nome: str
    status_mcti: str
    evidencia_contraria: str
    fonte_evidencia: str


class AuditoriaResponse(BaseModel):
    """Resposta da auditoria independente."""

    contradicoes: list[Contradicao]
    total_contradoes: int
    acoes_verificadas: int


# ---------------------------------------------------------------------------
# Entrega 6: Mapa Institucional
# ---------------------------------------------------------------------------


class InstituicaoMetrica(BaseModel):
    """Métricas de uma instituição."""

    sigla: str
    nome: str
    total_acoes: int
    entregues: int
    em_andamento: int
    parcialmente_entregue: int
    percentual_execucao: float


class MapaInstitucionalResponse(BaseModel):
    """Resposta do mapa institucional."""

    instituicoes: list[InstituicaoMetrica]
    total_instituicoes: int
    risco_concentracao: str = Field(..., description="Avaliação de risco de concentração")


# ---------------------------------------------------------------------------
# Entrega 7: Relatório de Lacunas
# ---------------------------------------------------------------------------


class Lacuna(BaseModel):
    """Ação com lacuna de execução."""

    acao_id: str
    acao_nome: str
    prazo: str | None
    status: str
    recurso_previsto: float
    dias_atraso: int


class LacunasResponse(BaseModel):
    """Resposta do relatório de lacunas."""

    lacunas: list[Lacuna]
    total_lacunas: int
    valor_em_risco: float = Field(..., description="Soma de recursos de ações em lacuna")
