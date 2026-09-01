"""Serviço de ingestão de evidências — IA Brasil.

Provedor de operações CRUD para evidências, fontes, vínculos e avaliações.
Segue as regras de negócio do domain-model.md.
"""

from datetime import date

from loguru import logger
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.core.db import (
    Avaliacao,
    EstadoVinculo,
    Evento,
    Evidencia,
    Fonte,
    VinculoEvidencia,
    get_session,
)
from src.modules.evidence_ingestion.schemas import (
    AvaliacaoCreateExtended,
    EventoCreateExtended,
    EvidenciaCreateExtended,
    FonteCreateExtended,
    VinculoCreateExtended,
)
from src.modules.webhook.outbound import notify_evidencia_nova


class EvidenceService:
    """Serviço para operações de evidências."""

    @staticmethod
    async def create_fonte(data: FonteCreateExtended) -> Fonte:
        """Cria uma nova fonte.

        Raises:
            ValueError: Se já existir uma fonte com o mesmo ID.
        """
        async with get_session() as session:
            existing = await session.execute(select(Fonte.id).where(Fonte.id == data.id).limit(1))
            if existing.scalar_one_or_none():
                raise ValueError(f"Fonte com ID '{data.id}' já existe")

            fonte = Fonte(
                id=data.id,
                url=str(data.url),
                titulo=data.titulo,
                instituicao_emissora=data.instituicao_emissora,
                tipo_documental=data.tipo_documental,
                data_publicacao=data.data_publicacao,
                data_coleta=data.data_coleta,
                hash_conteudo=data.hash_conteudo,
            )
            session.add(fonte)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ValueError(f"Fonte com ID '{data.id}' já existe")
            logger.info(f"Fonte criada: {fonte.id}")
            return fonte

    @staticmethod
    async def get_fonte(fonte_id: str) -> Fonte | None:
        """Busca uma fonte por ID."""
        async with get_session() as session:
            result = await session.execute(select(Fonte).where(Fonte.id == fonte_id))
            return result.scalar_one_or_none()

    @staticmethod
    async def list_fontes(limit: int = 100, offset: int = 0) -> list[Fonte]:
        """Lista fontes paginadas."""
        async with get_session() as session:
            result = await session.execute(
                select(Fonte).order_by(desc(Fonte.data_coleta)).limit(limit).offset(offset)
            )
            return list(result.scalars())

    @staticmethod
    async def create_evidencia(data: EvidenciaCreateExtended) -> Evidencia:
        """Cria uma nova evidência.

        Raises:
            ValueError: Se já existir uma evidência com o mesmo ID.
        """
        async with get_session() as session:
            existing = await session.execute(select(Evidencia).where(Evidencia.id == data.id))
            if existing.scalar_one_or_none():
                raise ValueError(f"Evidência com ID '{data.id}' já existe")

            evidencia = Evidencia(
                id=data.id,
                fonte_id=data.fonte_id,
                tipo=data.tipo,
                trecho=data.trecho,
                resumo=data.resumo,
                data_evidencia=data.data_evidencia,
                confianca=data.confianca,
            )
            session.add(evidencia)
            await session.flush()
            logger.info(f"Evidência criada: {evidencia.id}")

            # Disparar webhook outbound assinado (inativo por padrão — não bloqueia)
            await notify_evidencia_nova(
                {
                    "evidencia_id": evidencia.id,
                    "fonte_id": evidencia.fonte_id,
                    "tipo": evidencia.tipo.value,
                    "resumo": evidencia.resumo,
                    "data_evidencia": (
                        evidencia.data_evidencia.isoformat() if evidencia.data_evidencia else None
                    ),
                }
            )
            return evidencia

    @staticmethod
    async def get_evidencia(evidencia_id: str) -> Evidencia | None:
        """Busca uma evidência por ID com fonte carregada."""
        async with get_session() as session:
            result = await session.execute(
                select(Evidencia)
                .where(Evidencia.id == evidencia_id)
                .options(selectinload(Evidencia.fonte))
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_evidencias(
        fonte_id: str | None = None,
        tipo: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Evidencia]:
        """Lista evidências com filtros opcionais."""
        async with get_session() as session:
            stmt = select(Evidencia).order_by(desc(Evidencia.data_evidencia))

            if fonte_id:
                stmt = stmt.where(Evidencia.fonte_id == fonte_id)
            if tipo:
                stmt = stmt.where(Evidencia.tipo == tipo)

            result = await session.execute(stmt.limit(limit).offset(offset))
            return list(result.scalars())

    @staticmethod
    async def search_evidencias(query: str, limit: int = 50) -> list[Evidencia]:
        """Busca evidências por texto (trecho, resumo)."""
        async with get_session() as session:
            stmt = (
                select(Evidencia)
                .where(
                    or_(
                        Evidencia.trecho.ilike(f"%{query}%"),
                        Evidencia.resumo.ilike(f"%{query}%"),
                    )
                )
                .order_by(desc(Evidencia.data_evidencia))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars())

    @staticmethod
    async def create_vinculo(data: VinculoCreateExtended) -> VinculoEvidencia:
        """Cria um novo vínculo entre evidência e ação/meta.

        Raises:
            ValueError: Se já existir um vínculo com o mesmo ID ou mesma
                combinação (evidencia_id, acao_id).
        """
        async with get_session() as session:
            existing = await session.execute(
                select(VinculoEvidencia.id).where(VinculoEvidencia.id == data.id).limit(1)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Vínculo com ID '{data.id}' já existe")

            dup = await session.execute(
                select(VinculoEvidencia)
                .where(
                    VinculoEvidencia.evidencia_id == data.evidencia_id,
                    VinculoEvidencia.acao_id == data.acao_id,
                )
                .limit(1)
            )
            if dup.scalar_one_or_none():
                raise ValueError(
                    f"Já existe um vínculo entre evidência "
                    f"'{data.evidencia_id}' e ação '{data.acao_id}'"
                )

            vinculo = VinculoEvidencia(
                id=data.id,
                evidencia_id=data.evidencia_id,
                acao_id=data.acao_id,
                meta_id=data.meta_id,
                justificativa=data.justificativa,
                criado_por=data.criado_por,
                # Vínculo criado via API sem revisão humana entra como proposto
                # e depende de decisão explícita do operador no admin (#1098).
                estado=EstadoVinculo.proposto,
            )
            session.add(vinculo)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ValueError(f"Vínculo com ID '{data.id}' já existe")
            logger.info(f"Vínculo criado: {vinculo.id}")
            return vinculo

    @staticmethod
    async def get_vinculo(vinculo_id: str) -> VinculoEvidencia | None:
        """Busca um vínculo por ID."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia).where(VinculoEvidencia.id == vinculo_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_vinculos(
        evidencia_id: str | None = None,
        acao_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[VinculoEvidencia]:
        """Lista vínculos com filtros opcionais."""
        async with get_session() as session:
            stmt = select(VinculoEvidencia).order_by(desc(VinculoEvidencia.id))

            if evidencia_id:
                stmt = stmt.where(VinculoEvidencia.evidencia_id == evidencia_id)
            if acao_id:
                stmt = stmt.where(VinculoEvidencia.acao_id == acao_id)

            result = await session.execute(stmt.limit(limit).offset(offset))
            return list(result.scalars())

    @staticmethod
    async def create_avaliacao(data: AvaliacaoCreateExtended) -> Avaliacao:
        """Cria uma nova avaliação.

        Regras de negócio (domain-model.md):
        - Toda avaliação deve ter ao menos uma evidência vinculada, exceto status 'Não iniciado'

        Raises:
            ValueError: Se já existir uma avaliação com o mesmo ID ou mesma
                combinação (acao_id, versao).
        """
        async with get_session() as session:
            existing = await session.execute(
                select(Avaliacao.id).where(Avaliacao.id == data.id).limit(1)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Avaliação com ID '{data.id}' já existe")

            dup = await session.execute(
                select(Avaliacao)
                .where(
                    Avaliacao.acao_id == data.acao_id,
                    Avaliacao.versao == data.versao,
                )
                .limit(1)
            )
            if dup.scalar_one_or_none():
                raise ValueError(
                    f"Já existe uma avaliação versão {data.versao} para a ação '{data.acao_id}'"
                )

            # Validar regra de negócio: avaliação deve ter evidência vinculada
            # (exceto para status 'Não iniciado')
            if data.status_avaliado != "nao_iniciado":
                # Verificar se há pelo menos um vínculo para esta ação
                result = await session.execute(
                    select(VinculoEvidencia)
                    .where(VinculoEvidencia.acao_id == data.acao_id)
                    .limit(1)
                )
                if not result.scalar_one_or_none():
                    logger.warning(
                        f"Avaliação sem evidência vinculada para ação {data.acao_id}. "
                        "Isso é permitido apenas para status 'nao_iniciado'"
                    )

            avaliacao = Avaliacao(
                id=data.id,
                acao_id=data.acao_id,
                status_avaliado=data.status_avaliado,
                justificativa=data.justificativa,
                avaliado_por=data.avaliado_por,
                data_avaliacao=data.data_avaliacao,
                versao=data.versao,
                evidencias_usadas=data.evidencias_usadas or [],
            )
            session.add(avaliacao)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ValueError(f"Avaliação com ID '{data.id}' já existe")
            logger.info(f"Avaliação criada: {avaliacao.id}")
            return avaliacao

    @staticmethod
    async def get_avaliacao(avaliacao_id: str) -> Avaliacao | None:
        """Busca uma avaliação por ID."""
        async with get_session() as session:
            result = await session.execute(select(Avaliacao).where(Avaliacao.id == avaliacao_id))
            return result.scalar_one_or_none()

    @staticmethod
    async def list_avaliacoes(
        acao_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Avaliacao]:
        """Lista avaliações com filtros opcionais."""
        async with get_session() as session:
            stmt = select(Avaliacao).order_by(desc(Avaliacao.data_avaliacao))

            if acao_id:
                stmt = stmt.where(Avaliacao.acao_id == acao_id)
            if status:
                stmt = stmt.where(Avaliacao.status_avaliado == status)

            result = await session.execute(stmt.limit(limit).offset(offset))
            return list(result.scalars())

    @staticmethod
    async def get_latest_avaliacao(acao_id: str) -> Avaliacao | None:
        """Busca a avaliação mais recente para uma ação."""
        async with get_session() as session:
            result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .order_by(desc(Avaliacao.data_avaliacao), desc(Avaliacao.versao))
                .limit(1)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def create_evento(data: EventoCreateExtended) -> Evento:
        """Cria um novo evento.

        Raises:
            ValueError: Se já existir um evento com o mesmo ID.
        """
        async with get_session() as session:
            existing = await session.execute(select(Evento.id).where(Evento.id == data.id).limit(1))
            if existing.scalar_one_or_none():
                raise ValueError(f"Evento com ID '{data.id}' já existe")

            evento = Evento(
                id=data.id,
                acao_id=data.acao_id,
                tipo=data.tipo,
                descricao=data.descricao,
                data_evento=data.data_evento,
                criado_em=date.today(),
                fonte_url=str(data.fonte_url) if data.fonte_url else None,
            )
            session.add(evento)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ValueError(f"Evento com ID '{data.id}' já existe")
            logger.info(f"Evento criado: {evento.id}")
            return evento

    @staticmethod
    async def get_evento(evento_id: str) -> Evento | None:
        """Busca um evento por ID."""
        async with get_session() as session:
            result = await session.execute(select(Evento).where(Evento.id == evento_id))
            return result.scalar_one_or_none()

    @staticmethod
    async def list_eventos(
        acao_id: str | None = None,
        tipo: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Evento]:
        """Lista eventos com filtros opcionais."""
        async with get_session() as session:
            stmt = select(Evento).order_by(desc(Evento.data_evento))

            if acao_id:
                stmt = stmt.where(Evento.acao_id == acao_id)
            if tipo:
                stmt = stmt.where(Evento.tipo == tipo)

            result = await session.execute(stmt.limit(limit).offset(offset))
            return list(result.scalars())

    @staticmethod
    async def get_stats() -> dict[str, int | dict[str, int]]:
        """Retorna estatísticas de evidências."""
        async with get_session() as session:
            # Contar evidências por tipo
            result = await session.execute(
                select(Evidencia.tipo, func.count(Evidencia.id)).group_by(Evidencia.tipo)
            )
            por_tipo = {row[0]: row[1] for row in result}

            # Contar avaliações por status
            result = await session.execute(
                select(Avaliacao.status_avaliado, func.count(Avaliacao.id)).group_by(
                    Avaliacao.status_avaliado
                )
            )
            por_status = {row[0]: row[1] for row in result}

            # Total
            result = await session.execute(select(func.count(Evidencia.id)))
            total_evidencias = result.scalar() or 0

            result = await session.execute(select(func.count(Avaliacao.id)))
            total_avaliacoes = result.scalar() or 0

            return {
                "total_evidencias": total_evidencias,
                "total_avaliacoes": total_avaliacoes,
                "evidencias_por_tipo": por_tipo,
                "avaliacoes_por_status": por_status,
            }
