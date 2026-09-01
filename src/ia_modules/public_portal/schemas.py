""" "IA Brasil — Public Portal Schemas.

Schemas Pydantic para respostas da API pública.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.db import StatusAcao, TipoIndicador, TipoMeta  # noqa: TC001

# ============================================================================
# Schemas de Resposta - Eixo
# ============================================================================


class EixoBase(BaseModel):
    """Schema base para Eixo."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único do eixo")
    numero: int = Field(description="Número do eixo (1-5)")
    nome: str = Field(description="Nome do eixo")
    descricao: str | None = Field(default=None, description="Descrição do eixo")


class EixoDetail(EixoBase):
    """Schema detalhado para Eixo com programas."""

    programas: list[ProgramaBase] = Field(
        default_factory=list, description="Lista de programas do eixo"
    )


class EixoListResponse(BaseModel):
    """Resposta para listagem de eixos."""

    data: list[EixoBase] = Field(description="Lista de eixos")
    total: int = Field(description="Total de eixos")
    page: int = Field(description="Página atual")
    page_size: int = Field(description="Itens por página")
    pages: int = Field(description="Total de páginas")


# ============================================================================
# Schemas de Resposta - Programa
# ============================================================================


class ProgramaBase(BaseModel):
    """Schema base para Programa."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único do programa")
    eixo_id: str = Field(description="ID do eixo pai")
    codigo: str | None = Field(default=None, description="Código do programa")
    nome: str = Field(description="Nome do programa")
    descricao: str | None = Field(default=None, description="Descrição do programa")


class ProgramaDetail(ProgramaBase):
    """Schema detalhado para Programa com ações."""

    acoes: list[AcaoBase] = Field(default_factory=list, description="Lista de ações do programa")


class ProgramaListResponse(BaseModel):
    """Resposta para listagem de programas."""

    data: list[ProgramaBase] = Field(description="Lista de programas")
    total: int = Field(description="Total de programas")
    page: int = Field(description="Página atual")
    page_size: int = Field(description="Itens por página")
    pages: int = Field(description="Total de páginas")


# ============================================================================
# Schemas de Resposta - Ação
# ============================================================================


class AcaoBase(BaseModel):
    """Schema base para Ação."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único da ação")
    programa_id: str = Field(description="ID do programa pai")
    codigo_oficial: str | None = Field(default=None, description="Código oficial da ação")
    nome: str = Field(description="Nome da ação")
    descricao: str | None = Field(default=None, description="Descrição da ação")
    status: StatusAcao = Field(description="Status de execução da ação")
    prazo: date | None = Field(default=None, description="Data limite da ação")
    pagina_doc: int | None = Field(default=None, description="Página no documento oficial")


class RecursoBase(BaseModel):
    """Schema base para Recurso."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único do recurso")
    valor_previsto: float | None = Field(default=None, description="Valor previsto em reais")
    valor_executado: float | None = Field(default=None, description="Valor executado em reais")
    fonte: str | None = Field(default=None, description="Fonte do recurso")
    natureza: str | None = Field(default=None, description="Natureza do recurso")
    ano_referencia: int | None = Field(default=None, description="Ano de referência")


class MetaBase(BaseModel):
    """Schema base para Meta."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único da meta")
    descricao: str = Field(description="Descrição da meta")
    tipo: TipoMeta = Field(description="Tipo da meta")
    alvo_valor: float | None = Field(default=None, description="Valor alvo")
    alvo_unidade: str | None = Field(default=None, description="Unidade do valor alvo")
    prazo: date | None = Field(default=None, description="Data limite da meta")


class IndicadorBase(BaseModel):
    """Schema base para Indicador."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único do indicador")
    nome: str = Field(description="Nome do indicador")
    tipo: TipoIndicador = Field(description="Tipo do indicador")
    linha_base: float | None = Field(default=None, description="Valor de linha de base")
    meta_valor: float | None = Field(default=None, description="Valor meta")
    unidade: str | None = Field(default=None, description="Unidade de medida")
    fonte_calculo: str | None = Field(default=None, description="Fonte de cálculo")


class InstituicaoBase(BaseModel):
    """Schema base para Instituição."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único da instituição")
    sigla: str = Field(description="Sigla da instituição")
    nome: str = Field(description="Nome completo da instituição")
    tipo: str | None = Field(default=None, description="Tipo da instituição")
    url_oficial: str | None = Field(default=None, description="URL oficial da instituição")


class AcaoInstituicaoBase(BaseModel):
    """Schema para relação Ação-Instituição."""

    model_config = ConfigDict(from_attributes=True)

    papel: str = Field(description="Papel: responsavel, apoiador, executor")
    instituicao: InstituicaoBase = Field(description="Instituição relacionada")


class AcaoDetail(AcaoBase):
    """Schema detalhado para Ação com todas as entidades relacionadas."""

    metas: list[MetaBase] = Field(default_factory=list, description="Lista de metas da ação")
    indicadores: list[IndicadorBase] = Field(
        default_factory=list, description="Lista de indicadores da ação"
    )
    recursos: list[RecursoBase] = Field(
        default_factory=list, description="Lista de recursos da ação"
    )
    instituicoes: list[AcaoInstituicaoBase] = Field(
        default_factory=list, description="Lista de instituições relacionadas"
    )


class AcaoListResponse(BaseModel):
    """Resposta para listagem de ações."""

    data: list[AcaoBase] = Field(description="Lista de ações")
    total: int = Field(description="Total de ações")
    page: int = Field(description="Página atual")
    page_size: int = Field(description="Itens por página")
    pages: int = Field(description="Total de páginas")
    next_cursor: str | None = Field(
        default=None,
        description="Cursor opaco para a próxima página (null em paginação por page)",
    )


# ============================================================================
# Schemas de Resposta - Plano
# ============================================================================


class PlanoBase(BaseModel):
    """Schema base para Plano."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Identificador único do plano")
    nome: str = Field(description="Nome do plano")
    versao: str = Field(description="Versão do plano")
    ano_referencia: int = Field(description="Ano de referência")
    fonte_url: str | None = Field(default=None, description="URL do documento oficial")
    vigencia_inicio: date | None = Field(default=None, description="Data de início da vigência")
    vigencia_fim: date | None = Field(default=None, description="Data de fim da vigência")


class PlanoDetail(PlanoBase):
    """Schema detalhado para Plano com eixos."""

    eixos: list[EixoBase] = Field(default_factory=list, description="Lista de eixos do plano")


# ============================================================================
# Schemas de Erro
# ============================================================================


class ErrorDetail(BaseModel):
    """Detalhes do erro."""

    message: str = Field(description="Mensagem de erro")
    code: str | None = Field(default=None, description="Código do erro")
    details: dict[str, Any] | None = Field(default=None, description="Detalhes adicionais")


class ErrorResponse(BaseModel):
    """Resposta de erro padronizada."""

    error: ErrorDetail = Field(description="Detalhes do erro")


# ============================================================================
# Rebuild models — resolve ForwardRef para Pydantic v2 + __future__ annotations
# ============================================================================

for _model in [
    EixoBase,
    EixoDetail,
    EixoListResponse,
    ProgramaBase,
    ProgramaDetail,
    ProgramaListResponse,
    AcaoBase,
    AcaoDetail,
    AcaoListResponse,
    RecursoBase,
    MetaBase,
    IndicadorBase,
    InstituicaoBase,
    AcaoInstituicaoBase,
    PlanoBase,
    PlanoDetail,
    ErrorDetail,
    ErrorResponse,
]:
    _model.model_rebuild()  # type: ignore[attr-defined]
