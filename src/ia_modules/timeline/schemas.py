"""Schemas Pydantic para o módulo de timeline — IA Brasil.

Conforme especificação da issue #17: Tipos de evento e schemas de resposta.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel


class TipoEvento(StrEnum):
    """Tipos de evento conforme valores reais do backend.

    Os valores foram atualizados para refletir os tipos reais usados no banco de dados:
    - status_alterado: Mudança de status de ação
    - evidencia_vinculada: Vínculo de evidência criado
    - avaliacao_registrada: Avaliação registrada
    - nota_editorial: Notas editoriais e outros eventos"""

    STATUS_ALTERADO = "STATUS_ALTERADO"
    EVIDENCIA_VINCULADA = "EVIDENCIA_VINCULADA"
    AVALIACAO_REGISTRADA = "AVALIACAO_REGISTRADA"
    NOTA_EDITORIAL = "NOTA_EDITORIAL"


class EventoResponse(BaseModel):
    """Schema de resposta para eventos da timeline.

    Atributos:
        id: Identificador único do evento
        acao_id: ID da ação associada
        tipo: Tipo de evento (enum)
        descricao: Descrição do evento
        data_evento: Data do evento
        referencia_id: ID da entidade referenciada (opcional)
        referencia_tipo: Tipo da entidade referenciada (opcional)
        criado_em: Data de criação do registro
        fonte_url: URL de origem (opcional)
    """

    id: str
    acao_id: str
    tipo: TipoEvento
    descricao: str
    data_evento: date
    referencia_id: str | None = None
    referencia_tipo: str | None = None
    criado_em: date
    fonte_url: str | None = None


class TimelineResponse(BaseModel):
    """Resposta completa da timeline de uma ação.

    Atributos:
        acao_id: ID da ação
        eventos: Lista de eventos ordenados por data
        total: Total de eventos
    """

    acao_id: str
    eventos: list[EventoResponse]
    total: int
