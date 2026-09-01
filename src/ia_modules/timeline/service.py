"""Serviço de timeline — IA Brasil.

Implementa o registro imutável de eventos associados a ações do PBIA.
Conforme issue #17: "feat: implementar src/modules/timeline/ — registro de eventos por ação".

Principais responsabilidades:
1. Criar eventos imutáveis na timeline de ações
2. Consultar eventos de uma ação ordenados por data
3. Integração automática com criação de avaliações e vínculos

Regras de negócio:
- Eventos são imutáveis: só criação, nunca edição ou exclusão
- Cada evento referencia a entidade que o gerou (evidência, avaliação, vínculo)
- A timeline permite reconstituir a trajetória de execução ao longo do tempo
"""

import uuid
from dataclasses import dataclass
from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db import Acao, Evento, get_session
from src.modules.timeline.schemas import EventoResponse, TipoEvento


@dataclass
class EventoData:
    """Dados para criação de evento."""

    acao_id: str
    tipo: TipoEvento
    descricao: str
    data_evento: date
    referencia_id: str | None = None
    referencia_tipo: str | None = None
    fonte_url: str | None = None


def _generate_deterministic_event_id(evento_data: EventoData) -> str:
    """Generate a deterministic event ID using UUID5 hash.

    This ensures the same event data always produces the same ID, preventing duplicates
    and making the system more predictable. Uses the event's actual data (acao_id,
    tipo, data_evento, descricao) rather than creation timestamp.

    Args:
        evento_data: EventoData object containing event information

    Returns:
        A deterministic UUID string prefixed with 'evento_'

    Example:
        >>> evento_data = EventoData(
        ...     acao_id="acao_1",
        ...     tipo=TipoEvento.ANUNCIO,
        ...     descricao="Test event",
        ...     data_evento=date(2026, 6, 15)
        ... )
        >>> _generate_deterministic_event_id(evento_data)
        'evento_3633dda9-9713-5135-8faa-24534bea228c'
    """
    # Use the event's actual data for deterministic ID generation
    key = (
        f"evento:{evento_data.acao_id}:{evento_data.tipo.value}:"
        f"{evento_data.data_evento.isoformat()}:{evento_data.descricao}"
    )
    # Include optional fields if they exist to ensure uniqueness
    if evento_data.referencia_id:
        key += f":{evento_data.referencia_id}"
    if evento_data.referencia_tipo:
        key += f":{evento_data.referencia_tipo}"
    if evento_data.fonte_url:
        key += f":{evento_data.fonte_url}"

    # Generate UUID5 hash (deterministic)
    uuid_hash = uuid.uuid5(uuid.NAMESPACE_URL, key)
    return f"evento_{uuid_hash}"


class TimelineService:
    """Serviço para gerenciamento de eventos da timeline."""

    @staticmethod
    def _create_evento_object(evento_data: EventoData, criado_em: date | None = None) -> Evento:
        """Cria objeto Evento a partir dos dados.

        Args:
            evento_data: Dados do evento
            criado_em: Data de criação (opcional, usa date.today() se None)

        Returns:
            Objeto Evento
        """
        # Gerar um ID determinístico usando UUID5
        event_id = _generate_deterministic_event_id(evento_data)

        return Evento(
            id=event_id,
            acao_id=evento_data.acao_id,
            tipo=evento_data.tipo,
            descricao=evento_data.descricao,
            data_evento=evento_data.data_evento,
            referencia_id=evento_data.referencia_id,
            referencia_tipo=evento_data.referencia_tipo,
            criado_em=criado_em if criado_em is not None else date.today(),
            fonte_url=evento_data.fonte_url,
        )

    @staticmethod
    async def _registrar_evento_from_data(
        evento_data: EventoData, session: AsyncSession | None = None
    ) -> Evento:
        """Registra evento a partir de EventoData.

        Verifica duplicatas antes de inserir: se já existe um evento com o mesmo
        ID determinístico, retorna o existente em vez de criar um novo.
        """
        # Gerar ID determinístico primeiro para verificar duplicatas
        event_id = _generate_deterministic_event_id(evento_data)

        async def _insert_evento(
            sess: AsyncSession,
        ) -> Evento:
            # Verificar se evento já existe antes de criar o objeto
            existing = await sess.get(Evento, event_id)
            if existing:
                logger.debug(f"Evento duplicado ignorado: {event_id} | Ação: {evento_data.acao_id}")
                return existing

            # Criar evento com criado_em = date.today() apenas para novos eventos
            evento = TimelineService._create_evento_object(evento_data)

            # Obter nome real da ação para logging
            acao_nome = evento_data.acao_id
            try:
                acao_result = await sess.execute(
                    select(Acao)
                    .where(Acao.id == evento_data.acao_id)
                    .options(selectinload(Acao.programa))
                )
                acao = acao_result.scalar_one_or_none()
                acao_nome = acao.nome if acao else f"Ação {evento_data.acao_id}"
            except SQLAlchemyError:
                logger.exception(
                    f"Falha ao consultar ação {evento_data.acao_id} para log; "
                    "usando nome de fallback"
                )
                acao_nome = f"Ação {evento_data.acao_id}"

            sess.add(evento)
            await sess.flush()
            logger.info(
                f"Evento criado: {evento.id} | Ação: {acao_nome} | Tipo: {evento_data.tipo.value}"
            )
            return evento

        if session is None:
            async with get_session() as local_session:
                return await _insert_evento(local_session)
        else:
            return await _insert_evento(session)

    @staticmethod
    async def registrar_evento(
        acao_id: str,
        tipo: TipoEvento,
        descricao: str,
        data_evento: date,
        referencia_id: str | None = None,
        referencia_tipo: str | None = None,
        fonte_url: str | None = None,
        session: AsyncSession | None = None,
    ) -> Evento:
        """Cria evento imutável na timeline da ação.

        Args:
            acao_id: ID da ação associada
            tipo: Tipo de evento (enum)
            descricao: Descrição do evento
            data_evento: Data do evento
            referencia_id: ID da entidade referenciada (opcional)
            referencia_tipo: Tipo da entidade referenciada (opcional)
            fonte_url: URL de origem (opcional)
            session: Sessão SQLAlchemy (opcional, cria nova se None)

        Returns:
            Evento criado

        Raises:
            ValueError: Se dados obrigatórios estiverem faltando
        """
        if not acao_id or not tipo or not descricao or not data_evento:
            raise ValueError("Dados obrigatórios faltando: acao_id, tipo, descricao, data_evento")

        evento_data = EventoData(
            acao_id=acao_id,
            tipo=tipo,
            descricao=descricao,
            data_evento=data_evento,
            referencia_id=referencia_id,
            referencia_tipo=referencia_tipo,
            fonte_url=fonte_url,
        )
        return await TimelineService._registrar_evento_from_data(evento_data, session)

    @staticmethod
    async def _execute_timeline_query(acao_id: str, session: AsyncSession) -> list[EventoResponse]:
        """Executa consulta de timeline e retorna EventoResponse.

        Args:
            acao_id: ID da ação
            session: Sessão SQLAlchemy ativa

        Returns:
            Lista de EventoResponse ordenados por data
        """
        result = await session.execute(
            select(Evento)
            .where(Evento.acao_id == acao_id)
            .order_by(Evento.data_evento.asc(), Evento.criado_em.asc())
        )

        eventos = result.scalars().all()

        return [
            EventoResponse(
                id=evento.id,
                acao_id=evento.acao_id,
                tipo=evento.tipo,
                descricao=evento.descricao,
                data_evento=evento.data_evento,
                referencia_id=evento.referencia_id,
                referencia_tipo=evento.referencia_tipo,
                criado_em=evento.criado_em,
                fonte_url=evento.fonte_url,
            )
            for evento in eventos
        ]

    @staticmethod
    async def get_timeline(
        acao_id: str, session: AsyncSession | None = None
    ) -> list[EventoResponse]:
        """Retorna eventos da ação ordenados por data_evento ASC.

        Args:
            acao_id: ID da ação
            session: Sessão SQLAlchemy (opcional, cria nova se None)

        Returns:
            Lista de EventoResponse ordenados por data
        """
        if session is None:
            async with get_session() as local_session:
                return await TimelineService._execute_timeline_query(acao_id, local_session)
        else:
            return await TimelineService._execute_timeline_query(acao_id, session)

    @staticmethod
    async def registrar_evento_avaliacao(
        acao_id: str,
        avaliacao_id: str,
        status_anterior: str | None,
        status_novo: str,
        data_avaliacao: date,
        session: AsyncSession | None = None,
    ) -> Evento:
        """Registra evento automático ao criar uma avaliação.

        Args:
            acao_id: ID da ação
            avaliacao_id: ID da avaliação criada
            status_anterior: Status anterior da ação
            status_novo: Novo status da ação
            data_avaliacao: Data da avaliação
            session: Sessão SQLAlchemy

        Returns:
            Evento criado
        """
        descricao = f"Avaliação registrada: status alterado de {status_anterior} para {status_novo}"
        evento_data = EventoData(
            acao_id=acao_id,
            tipo=TipoEvento.AVALIACAO_REGISTRADA,
            descricao=descricao,
            data_evento=data_avaliacao,
            referencia_id=avaliacao_id,
            referencia_tipo="avaliacao",
            fonte_url=None,
        )
        return await TimelineService._registrar_evento_from_data(evento_data, session)

    @staticmethod
    async def registrar_evento_vinculo(
        acao_id: str,
        vinculo_id: str,
        evidencia_id: str,
        data_vinculo: date,
        session: AsyncSession | None = None,
    ) -> Evento:
        """Registra evento automático ao criar um vínculo de evidência.

        Args:
            acao_id: ID da ação
            vinculo_id: ID do vínculo criado
            evidencia_id: ID da evidência vinculada
            data_vinculo: Data do vínculo
            session: Sessão SQLAlchemy

        Returns:
            Evento criado
        """
        descricao = f"Evidência vinculada: {evidencia_id}"
        evento_data = EventoData(
            acao_id=acao_id,
            tipo=TipoEvento.EVIDENCIA_VINCULADA,
            descricao=descricao,
            data_evento=data_vinculo,
            referencia_id=vinculo_id,
            referencia_tipo="vinculo",
            fonte_url=None,
        )
        return await TimelineService._registrar_evento_from_data(evento_data, session)

    @staticmethod
    async def registrar_evento_status(
        acao_id: str,
        status_anterior: str | None,
        status_novo: str,
        data_mudanca: date,
        justificativa: str | None = None,
        session: AsyncSession | None = None,
    ) -> Evento:
        """Registra evento de mudança de status.

        Args:
            acao_id: ID da ação
            status_anterior: Status anterior
            status_novo: Novo status
            data_mudanca: Data da mudança
            justificativa: Justificativa da mudança
            session: Sessão SQLAlchemy

        Returns:
            Evento criado
        """
        descricao = f"Status alterado: {status_anterior} → {status_novo}"
        if justificativa:
            descricao += f" | Justificativa: {justificativa}"

        evento_data = EventoData(
            acao_id=acao_id,
            tipo=TipoEvento.STATUS_ALTERADO,
            descricao=descricao,
            data_evento=data_mudanca,
            referencia_id=None,
            referencia_tipo=None,
            fonte_url=None,
        )
        return await TimelineService._registrar_evento_from_data(evento_data, session)
