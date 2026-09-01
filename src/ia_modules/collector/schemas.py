"""Schemas Pydantic para coleta de dados.

Estende os schemas básicos com validações específicas para coleta automática.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

# ---------------------------------------------------------------------------
# Core Collector Schemas
# ---------------------------------------------------------------------------


class CollectorResult(BaseModel):
    """Resultado da coleta de uma fonte."""

    items: list[dict[str, Any]] = Field(..., description="Itens extraídos em formato estruturado")
    provenance: dict[str, "FieldProvenance"] = Field(..., description="Provenance por campo")
    source_metadata: "SourceMetadata" = Field(..., description="Metadados da fonte")


class SourceMetadata(BaseModel):
    """Metadados da fonte de dados."""

    source_url: HttpUrl = Field(..., description="URL da fonte original")
    etag: str | None = Field(None, description="ETag para detecção de mudanças")
    last_modified: datetime | None = Field(None, description="Data da última modificação")
    content_hash: str | None = Field(None, description="Hash do conteúdo para detecção de mudanças")
    fetch_timestamp: datetime = Field(
        default_factory=datetime.now, description="Data/hora da coleta"
    )


class FieldProvenance(BaseModel):
    """Provenance de um campo específico."""

    source_url: HttpUrl = Field(..., description="URL da fonte original")
    method: str = Field(
        ...,
        description=(
            "Método de extração (pdf_text, pdf_table, html_css, csv, json, api, llm_extract)"
        ),
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="Data/hora da extração")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Nível de confiança (0.0-1.0)")
    raw_ref: str = Field(
        ...,
        description="Referência bruta (ex: 'page 3, table 2, row 5' ou 'CSS selector .meta-row')",
    )
    parser_version: str = Field(..., description="Versão do parser utilizado")


# ---------------------------------------------------------------------------
# Source Adapters
# ---------------------------------------------------------------------------


class CollectorType(StrEnum):
    """Tipos de coletores suportados."""

    MCTI_PLAN = "mcti_plan"
    CGU_TRANSPARENCIA = "cgu_transparencia"
    DADOS_GOV_BR = "dados_gov_br"
    TCU_AUDITORIA = "tcu_auditoria"
    PNCP_CONTRATOS = "pncp_contratos"
    DOU_DIARIO = "dou_diario"


class CollectorConfig(BaseModel):
    """Configuração de um coletor."""

    name: CollectorType = Field(..., description="Nome do coletor")
    source_url: HttpUrl = Field(..., description="URL base da fonte")
    schedule: str = Field(..., description="Expressão cron para agendamento")
    enabled: bool = Field(default=True, description="Se o coletor está ativo")


# ---------------------------------------------------------------------------
# Domain-Specific Schemas (PBIA)
# ---------------------------------------------------------------------------


class EixoCreate(BaseModel):
    """Schema para criação de Eixo do PBIA."""

    id: str = Field(..., description="Identificador único do eixo")
    titulo: str = Field(..., description="Título do eixo")
    descricao: str = Field(..., description="Descrição do eixo")
    ordem: int = Field(..., description="Ordem de apresentação")


class MetaCreate(BaseModel):
    """Schema para criação de Meta do PBIA."""

    id: str = Field(..., description="Identificador único da meta")
    eixo_id: str = Field(..., description="ID do eixo associado")
    titulo: str = Field(..., description="Título da meta")
    descricao: str = Field(..., description="Descrição da meta")
    indicador: str = Field(..., description="Indicador de medição")
    tipo_indicador: str = Field(..., description="Tipo de indicador (quantitativa/qualitativa)")
    alvo_valor: float | None = Field(
        None, description="Valor alvo (para indicadores quantitativos)"
    )
    alvo_unidade: str | None = Field(None, description="Unidade do valor alvo")
    prazo: str | None = Field(None, description="Prazo para atingir a meta")


class ProjetoCreate(BaseModel):
    """Schema para criação de Projeto de execução."""

    id: str = Field(..., description="Identificador único do projeto")
    titulo: str = Field(..., description="Título do projeto")
    descricao: str = Field(..., description="Descrição do projeto")
    instituicao_responsavel: str = Field(..., description="Instituição responsável")
    valor_orcado: float | None = Field(None, description="Valor orçado")
    valor_executado: float | None = Field(None, description="Valor executado")
    status: str | None = Field(None, description="Status do projeto")
