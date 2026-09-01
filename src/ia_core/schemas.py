"""
IA Brasil — Schemas Pydantic para validação de entrada (desacoplados do ORM).

Camada isolada de `src.core.models` e `src.core.settings` para permitir
versionar DTOs públicos e testar casos de uso sem banco (issue #1081).
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003
from typing import Any

from pydantic import BaseModel

from src.core.models import (
    EstadoVinculo,
    StatusAcao,
    TipoClaim,
    TipoEvento,
    TipoEvidencia,
    TipoIndicador,
    TipoMeta,
)


class AcaoCreate(BaseModel):
    id: str
    programa_id: str
    codigo_oficial: str | None = None
    nome: str
    descricao: str | None = None
    prazo: date | None = None
    trecho_original: str | None = None
    pagina_doc: int | None = None
    tipo_estruturante: str | None = None
    area_tematica: str | None = None
    desafio: str | None = None
    status_atualizado_em: datetime | None = None


class EvidenciaCreate(BaseModel):
    id: str
    fonte_id: str
    tipo: TipoEvidencia
    tipo_claim: TipoClaim | None = None
    trecho: str | None = None
    resumo: str | None = None
    data_evidencia: date | None = None
    confianca: float | None = None


class VinculoCreate(BaseModel):
    id: str
    evidencia_id: str
    acao_id: str
    meta_id: str | None = None
    justificativa: str | None = None
    criado_por: str | None = None
    aprovado_por: str | None = None
    estado: EstadoVinculo = EstadoVinculo.proposto
    revisor: str | None = None
    metodo: str | None = None
    score: float | None = None
    revisado_em: datetime | None = None


# Schemas para Plano
class PlanoCreate(BaseModel):
    id: str
    nome: str
    versao: str
    ano_referencia: int
    fonte_url: str | None = None
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None


class PlanoRead(PlanoCreate):
    pass


# Schemas para Eixo
class EixoCreate(BaseModel):
    id: str
    plano_id: str
    numero: int
    nome: str
    descricao: str | None = None


class EixoRead(EixoCreate):
    pass


# Schemas para Programa
class ProgramaCreate(BaseModel):
    id: str
    eixo_id: str
    nome: str
    codigo: str | None = None
    descricao: str | None = None


class ProgramaRead(ProgramaCreate):
    pass


# Schemas para Meta
class MetaCreate(BaseModel):
    id: str
    acao_id: str
    descricao: str
    tipo: TipoMeta
    alvo_valor: float | None = None
    alvo_unidade: str | None = None
    prazo: date | None = None


class MetaRead(MetaCreate):
    pass


# Schemas para Indicador
class IndicadorCreate(BaseModel):
    id: str
    meta_id: str
    tipo: TipoIndicador
    linha_base: float | None = None
    meta_valor: float | None = None
    unidade: str | None = None
    fonte_calculo: str | None = None


class IndicadorRead(IndicadorCreate):
    pass


# Schemas para Recurso
class RecursoCreate(BaseModel):
    id: str
    acao_id: str
    valor_previsto: float | None = None
    valor_executado: float | None = None
    fonte: str | None = None
    natureza: str | None = None
    ano_referencia: int | None = None


class RecursoRead(RecursoCreate):
    pass


# Schemas para Instituicao
class InstituicaoCreate(BaseModel):
    id: str
    sigla: str
    nome: str
    tipo: str | None = None
    url_oficial: str | None = None


class InstituicaoRead(InstituicaoCreate):
    pass


# Schemas para AcaoInstituicao
class AcaoInstituicaoCreate(BaseModel):
    acao_id: str
    instituicao_id: str
    papel: str


# Schemas para Fonte
class FonteCreate(BaseModel):
    id: str
    url: str
    titulo: str | None = None
    instituicao_emissora: str | None = None
    tipo_documental: str | None = None
    data_publicacao: date | None = None
    data_coleta: date
    hash_conteudo: str | None = None


class FonteRead(FonteCreate):
    pass


# Schemas para Evidencia
class EvidenciaRead(EvidenciaCreate):
    pass


# Schemas para Avaliacao
class AvaliacaoCreate(BaseModel):
    id: str
    acao_id: str
    status_avaliado: StatusAcao
    justificativa: str
    avaliado_por: str | None = None
    data_avaliacao: date
    versao: int = 1
    evidencias_usadas: list[dict[str, Any]] | None = None


class AvaliacaoRead(AvaliacaoCreate):
    pass


# Schemas para Evento
class EventoCreate(BaseModel):
    id: str
    acao_id: str
    tipo: TipoEvento
    descricao: str
    data_evento: date
    fonte_url: str | None = None


class EventoRead(EventoCreate):
    pass
