"""Serviço admin — IA Brasil.

Implementa operações administrativas: CRUD de evidências,
revisão de vínculos, gestão de avaliações e dashboard.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.core.db import (
    Acao,
    Avaliacao,
    EstadoVinculo,
    Evento,
    Evidencia,
    IngestionRun,
    VinculoEvidencia,
    get_session,
)
from src.modules.admin.schemas import (
    AdminAvaliacaoCreate,
    AdminAvaliacaoFilter,
    AdminAvaliacaoRead,
    AdminAvaliacaoUpdate,
    AdminDashboard,
    AdminDashboardMetrics,
    AdminEventoFilter,
    AdminEventoRead,
    AdminEvidenciaCreate,
    AdminEvidenciaFilter,
    AdminEvidenciaRead,
    AdminEvidenciaUpdate,
    AdminIngestionStatus,
    AdminPaginatedResponse,
    AdminQualityAlert,
    AdminVinculoApprove,
    AdminVinculoCreate,
    AdminVinculoFilter,
    AdminVinculoRead,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AdminService:
    """Serviço para operações administrativas."""

    # -----------------------------------------------------------------------
    # Evidências
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_evidencias(
        filters: AdminEvidenciaFilter,
    ) -> AdminPaginatedResponse:
        """Lista evidências com filtros e paginação."""
        async with get_session() as session:
            stmt = select(Evidencia).options(joinedload(Evidencia.fonte))

            if filters.fonte_id:
                stmt = stmt.where(Evidencia.fonte_id == filters.fonte_id)
            if filters.tipo:
                stmt = stmt.where(Evidencia.tipo == filters.tipo)
            if filters.data_inicio:
                stmt = stmt.where(Evidencia.data_evidencia >= filters.data_inicio)
            if filters.data_fim:
                stmt = stmt.where(Evidencia.data_evidencia <= filters.data_fim)
            if filters.confianca_min is not None:
                stmt = stmt.where(Evidencia.confianca >= filters.confianca_min)
            if filters.confianca_max is not None:
                stmt = stmt.where(Evidencia.confianca <= filters.confianca_max)

            count_stmt = select(func.count(Evidencia.id))
            if filters.fonte_id:
                count_stmt = count_stmt.where(Evidencia.fonte_id == filters.fonte_id)
            if filters.tipo:
                count_stmt = count_stmt.where(Evidencia.tipo == filters.tipo)
            if filters.data_inicio:
                count_stmt = count_stmt.where(Evidencia.data_evidencia >= filters.data_inicio)
            if filters.data_fim:
                count_stmt = count_stmt.where(Evidencia.data_evidencia <= filters.data_fim)
            if filters.confianca_min is not None:
                count_stmt = count_stmt.where(Evidencia.confianca >= filters.confianca_min)
            if filters.confianca_max is not None:
                count_stmt = count_stmt.where(Evidencia.confianca <= filters.confianca_max)

            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            stmt = stmt.order_by(desc(Evidencia.data_evidencia))
            stmt = stmt.offset(filters.offset).limit(filters.limit)
            result = await session.execute(stmt)
            evidencias = result.scalars().unique().all()

            items = [
                AdminEvidenciaRead(
                    id=e.id,
                    fonte_id=e.fonte_id,
                    tipo=e.tipo,
                    trecho=e.trecho,
                    resumo=e.resumo,
                    data_evidencia=e.data_evidencia,
                    confianca=(float(e.confianca) if e.confianca is not None else None),
                    fonte_url=e.fonte.url if e.fonte else None,
                    fonte_titulo=e.fonte.titulo if e.fonte else None,
                ).model_dump()
                for e in evidencias
            ]

            total_pages = max(1, (total + filters.limit - 1) // filters.limit)
            page = (filters.offset // filters.limit) + 1

            return AdminPaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=filters.limit,
                total_pages=total_pages,
            )

    @staticmethod
    async def get_evidencia(
        evidencia_id: str,
    ) -> AdminEvidenciaRead | None:
        """Busca uma evidência por ID."""
        async with get_session() as session:
            result = await session.execute(
                select(Evidencia)
                .where(Evidencia.id == evidencia_id)
                .options(joinedload(Evidencia.fonte))
            )
            evidencia = result.scalars().unique().one_or_none()
            if not evidencia:
                return None
            return AdminEvidenciaRead(
                id=evidencia.id,
                fonte_id=evidencia.fonte_id,
                tipo=evidencia.tipo,
                trecho=evidencia.trecho,
                resumo=evidencia.resumo,
                data_evidencia=evidencia.data_evidencia,
                confianca=(float(evidencia.confianca) if evidencia.confianca is not None else None),
                fonte_url=evidencia.fonte.url if evidencia.fonte else None,
                fonte_titulo=(evidencia.fonte.titulo if evidencia.fonte else None),
            )

    @staticmethod
    async def create_evidencia(
        data: AdminEvidenciaCreate,
    ) -> AdminEvidenciaRead:
        """Cria uma nova evidência.

        Raises:
            ValueError: Se já existir uma evidência com o mesmo ID.
        """
        async with get_session() as session:
            existing = await session.execute(
                select(Evidencia.id).where(Evidencia.id == data.id).limit(1)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Evidência já existe com ID: {data.id}")

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
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ValueError(f"Evidência já existe com ID: {data.id}")
            logger.info(f"Evidência criada (admin): {evidencia.id}")

            return AdminEvidenciaRead(
                id=evidencia.id,
                fonte_id=evidencia.fonte_id,
                tipo=evidencia.tipo,
                trecho=evidencia.trecho,
                resumo=evidencia.resumo,
                data_evidencia=evidencia.data_evidencia,
                confianca=(float(evidencia.confianca) if evidencia.confianca is not None else None),
            )

    @staticmethod
    async def update_evidencia(
        evidencia_id: str,
        data: AdminEvidenciaUpdate,
    ) -> AdminEvidenciaRead | None:
        """Atualiza metadados de uma evidência."""
        async with get_session() as session:
            result = await session.execute(
                select(Evidencia)
                .where(Evidencia.id == evidencia_id)
                .options(joinedload(Evidencia.fonte))
            )
            evidencia = result.scalars().unique().one_or_none()
            if not evidencia:
                return None

            if data.tipo is not None:
                evidencia.tipo = data.tipo
            if data.trecho is not None:
                evidencia.trecho = data.trecho
            if data.resumo is not None:
                evidencia.resumo = data.resumo
            if data.data_evidencia is not None:
                evidencia.data_evidencia = data.data_evidencia
            if data.confianca is not None:
                evidencia.confianca = data.confianca

            await session.flush()
            logger.info(f"Evidência atualizada (admin): {evidencia.id}")

            return AdminEvidenciaRead(
                id=evidencia.id,
                fonte_id=evidencia.fonte_id,
                tipo=evidencia.tipo,
                trecho=evidencia.trecho,
                resumo=evidencia.resumo,
                data_evidencia=evidencia.data_evidencia,
                confianca=(float(evidencia.confianca) if evidencia.confianca is not None else None),
                fonte_url=evidencia.fonte.url if evidencia.fonte else None,
                fonte_titulo=(evidencia.fonte.titulo if evidencia.fonte else None),
            )

    @staticmethod
    async def delete_evidencia(evidencia_id: str) -> bool:
        """Remove uma evidência pelo ID."""
        async with get_session() as session:
            result = await session.execute(select(Evidencia).where(Evidencia.id == evidencia_id))
            evidencia = result.scalar_one_or_none()
            if not evidencia:
                return False
            await session.delete(evidencia)
            await session.flush()
            logger.info(f"Evidência removida (admin): {evidencia_id}")
            return True

    # -----------------------------------------------------------------------
    # Vínculos
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_vinculos(
        filters: AdminVinculoFilter,
    ) -> AdminPaginatedResponse:
        """Lista vínculos com filtros e paginação."""
        async with get_session() as session:
            stmt = select(VinculoEvidencia).options(
                joinedload(VinculoEvidencia.evidencia),
                joinedload(VinculoEvidencia.acao),
            )

            if filters.acao_id:
                stmt = stmt.where(VinculoEvidencia.acao_id == filters.acao_id)
            if filters.evidencia_id:
                stmt = stmt.where(VinculoEvidencia.evidencia_id == filters.evidencia_id)
            if filters.criado_por:
                stmt = stmt.where(VinculoEvidencia.criado_por == filters.criado_por)
            if filters.estado:
                stmt = stmt.where(VinculoEvidencia.estado == filters.estado)

            count_stmt = select(func.count(VinculoEvidencia.id))
            if filters.acao_id:
                count_stmt = count_stmt.where(VinculoEvidencia.acao_id == filters.acao_id)
            if filters.evidencia_id:
                count_stmt = count_stmt.where(VinculoEvidencia.evidencia_id == filters.evidencia_id)
            if filters.criado_por:
                count_stmt = count_stmt.where(VinculoEvidencia.criado_por == filters.criado_por)
            if filters.estado:
                count_stmt = count_stmt.where(VinculoEvidencia.estado == filters.estado)

            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            stmt = stmt.order_by(desc(VinculoEvidencia.id))
            stmt = stmt.offset(filters.offset).limit(filters.limit)
            result = await session.execute(stmt)
            vinculos = result.scalars().unique().all()

            items = [
                AdminVinculoRead(
                    id=v.id,
                    evidencia_id=v.evidencia_id,
                    acao_id=v.acao_id,
                    meta_id=v.meta_id,
                    justificativa=v.justificativa,
                    criado_por=v.criado_por,
                    aprovado_por=v.aprovado_por,
                    estado=v.estado,
                    revisor=v.revisor,
                    metodo=v.metodo,
                    score=v.score,
                    revisado_em=v.revisado_em,
                    evidencia_resumo=(v.evidencia.resumo if v.evidencia else None),
                    acao_nome=v.acao.nome if v.acao else None,
                ).model_dump()
                for v in vinculos
            ]

            total_pages = max(1, (total + filters.limit - 1) // filters.limit)
            page = (filters.offset // filters.limit) + 1

            return AdminPaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=filters.limit,
                total_pages=total_pages,
            )

    @staticmethod
    async def get_vinculo(
        vinculo_id: str,
    ) -> AdminVinculoRead | None:
        """Busca um vínculo por ID."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia)
                .where(VinculoEvidencia.id == vinculo_id)
                .options(
                    joinedload(VinculoEvidencia.evidencia),
                    joinedload(VinculoEvidencia.acao),
                )
            )
            vinculo = result.scalars().unique().one_or_none()
            if not vinculo:
                return None
            return AdminVinculoRead(
                id=vinculo.id,
                evidencia_id=vinculo.evidencia_id,
                acao_id=vinculo.acao_id,
                meta_id=vinculo.meta_id,
                justificativa=vinculo.justificativa,
                criado_por=vinculo.criado_por,
                aprovado_por=vinculo.aprovado_por,
                estado=vinculo.estado,
                revisor=vinculo.revisor,
                metodo=vinculo.metodo,
                score=vinculo.score,
                revisado_em=vinculo.revisado_em,
                evidencia_resumo=(vinculo.evidencia.resumo if vinculo.evidencia else None),
                acao_nome=vinculo.acao.nome if vinculo.acao else None,
            )

    @staticmethod
    async def create_vinculo(
        data: AdminVinculoCreate,
        operador: str | None = None,
    ) -> AdminVinculoRead:
        """Cria um novo vínculo manualmente.

        Vínculos criados explicitamente pelo operador admin entram como
        ``aprovado`` (ação explícita do operador); qualquer outra origem
        (API, coletor) entra como ``proposto`` e depende de revisão humana
        (issue #1098).

        Args:
            data: Dados do vínculo.
            operador: Identidade do operador autenticado (nome/prefixo da API
                key). Usado para rastrear revisor/aprovado_por.

        Raises:
            ValueError: Se já existir um vínculo com o mesmo ID ou mesma
                combinação (evidencia_id, acao_id).
        """
        operador_final = operador or "admin"
        async with get_session() as session:
            existing = await session.execute(
                select(VinculoEvidencia.id).where(VinculoEvidencia.id == data.id).limit(1)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Vínculo já existe com ID: {data.id}")

            dup = await session.execute(
                select(VinculoEvidencia).where(
                    VinculoEvidencia.evidencia_id == data.evidencia_id,
                    VinculoEvidencia.acao_id == data.acao_id,
                )
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
                aprovado_por=operador_final if data.criado_por == "admin" else None,
                estado=(
                    EstadoVinculo.aprovado if data.criado_por == "admin" else EstadoVinculo.proposto
                ),
                revisor=operador_final if data.criado_por == "admin" else None,
                metodo="manual" if data.criado_por == "admin" else None,
                revisado_em=datetime.now() if data.criado_por == "admin" else None,
            )
            session.add(vinculo)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ValueError(f"Vínculo já existe com ID: {data.id}")
            logger.info(f"Vínculo criado (admin): {vinculo.id}")

            return AdminVinculoRead(
                id=vinculo.id,
                evidencia_id=vinculo.evidencia_id,
                acao_id=vinculo.acao_id,
                meta_id=vinculo.meta_id,
                justificativa=vinculo.justificativa,
                criado_por=vinculo.criado_por,
                aprovado_por=vinculo.aprovado_por,
                estado=vinculo.estado,
                revisor=vinculo.revisor,
                metodo=vinculo.metodo,
                score=vinculo.score,
                revisado_em=vinculo.revisado_em,
            )

    @staticmethod
    async def approve_vinculo(
        vinculo_id: str,
        data: AdminVinculoApprove,
        operador: str | None = None,
    ) -> AdminVinculoRead | None:
        """Registra a decisão de revisão (aprovar/rejeitar) de um vínculo.

        Primeira decisão sobre um vínculo ``proposto``: grava o novo estado
        no próprio registro com trilha de operador (``revisor``, ``metodo``
        e ``revisado_em``). Rejeição NÃO remove o vínculo — ele permanece
        com ``estado=rejeitado`` para compor a fila de revisão (issue #1098).

        Decisão posterior sobre um vínculo já revisado: preserva a decisão
        anterior como linha de histórico na ``justificativa`` antes de
        registrar a nova decisão — o schema atual permite apenas um registro
        por par (evidencia_id, acao_id) (unique constraint sem migration),
        então a "nova versão" da decisão é anexada ao histórico em vez de
        sobrescrever silenciosamente.

        Args:
            vinculo_id: ID do vínculo.
            data: Decisão (aprovado + justificativa opcional).
            operador: Identidade do operador autenticado (nome/prefixo da API
                key), registrada como revisor.

        Returns:
            AdminVinculoRead atualizado, ou None se o vínculo não existir.
        """
        operador_final = operador or "admin"
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia)
                .where(VinculoEvidencia.id == vinculo_id)
                .with_for_update()
                .options(
                    joinedload(VinculoEvidencia.evidencia),
                    joinedload(VinculoEvidencia.acao),
                )
            )
            vinculo = result.scalars().unique().one_or_none()
            if not vinculo:
                return None

            novo_estado = EstadoVinculo.aprovado if data.aprovado else EstadoVinculo.rejeitado
            agora = datetime.now()

            # Decisão posterior sobre vínculo já revisado: preserva o histórico
            # da decisão anterior antes de registrar a nova.
            historico: str | None = None
            if vinculo.estado != EstadoVinculo.proposto and vinculo.revisado_em is not None:
                registro_anterior = (
                    f"[{vinculo.revisado_em.isoformat(sep=' ')}] "
                    f"{vinculo.revisor or 'desconhecido'}: {vinculo.estado.value}"
                )
                if vinculo.justificativa:
                    registro_anterior = f"{registro_anterior} — {vinculo.justificativa}"
                historico = f"[Histórico] {registro_anterior}"

            vinculo.estado = novo_estado
            vinculo.revisor = operador_final
            vinculo.metodo = "manual"
            vinculo.revisado_em = agora
            if data.aprovado:
                vinculo.aprovado_por = operador_final
            else:
                vinculo.aprovado_por = None

            if historico:
                vinculo.justificativa = (
                    f"{historico}\n{data.justificativa}" if data.justificativa else historico
                )
            elif data.justificativa:
                vinculo.justificativa = data.justificativa

            await session.flush()
            acao_desc = "aprovado" if data.aprovado else "rejeitado"
            logger.info(f"Vínculo {acao_desc} (admin): {vinculo.id} por {operador_final}")

            return AdminVinculoRead(
                id=vinculo.id,
                evidencia_id=vinculo.evidencia_id,
                acao_id=vinculo.acao_id,
                meta_id=vinculo.meta_id,
                justificativa=vinculo.justificativa,
                criado_por=vinculo.criado_por,
                aprovado_por=vinculo.aprovado_por,
                estado=vinculo.estado,
                revisor=vinculo.revisor,
                metodo=vinculo.metodo,
                score=vinculo.score,
                revisado_em=vinculo.revisado_em,
                evidencia_resumo=(vinculo.evidencia.resumo if vinculo.evidencia else None),
                acao_nome=vinculo.acao.nome if vinculo.acao else None,
            )

    @staticmethod
    async def delete_vinculo(vinculo_id: str) -> bool:
        """Remove um vínculo pelo ID."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia).where(VinculoEvidencia.id == vinculo_id)
            )
            vinculo = result.scalar_one_or_none()
            if not vinculo:
                return False
            await session.delete(vinculo)
            await session.flush()
            logger.info(f"Vínculo removido (admin): {vinculo_id}")
            return True

    # -----------------------------------------------------------------------
    # Avaliações
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_avaliacoes(
        filters: AdminAvaliacaoFilter,
    ) -> AdminPaginatedResponse:
        """Lista avaliações com filtros e paginação."""
        async with get_session() as session:
            stmt = select(Avaliacao).options(joinedload(Avaliacao.acao))

            if filters.acao_id:
                stmt = stmt.where(Avaliacao.acao_id == filters.acao_id)
            if filters.status:
                stmt = stmt.where(Avaliacao.status_avaliado == filters.status)
            if filters.avaliado_por:
                stmt = stmt.where(Avaliacao.avaliado_por == filters.avaliado_por)

            count_stmt = select(func.count(Avaliacao.id))
            if filters.acao_id:
                count_stmt = count_stmt.where(Avaliacao.acao_id == filters.acao_id)
            if filters.status:
                count_stmt = count_stmt.where(Avaliacao.status_avaliado == filters.status)
            if filters.avaliado_por:
                count_stmt = count_stmt.where(Avaliacao.avaliado_por == filters.avaliado_por)

            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            stmt = stmt.order_by(desc(Avaliacao.data_avaliacao))
            stmt = stmt.offset(filters.offset).limit(filters.limit)
            result = await session.execute(stmt)
            avaliacoes = result.scalars().unique().all()

            items = [
                AdminAvaliacaoRead(
                    id=a.id,
                    acao_id=a.acao_id,
                    status_avaliado=a.status_avaliado,
                    justificativa=a.justificativa,
                    avaliado_por=a.avaliado_por,
                    data_avaliacao=a.data_avaliacao,
                    versao=a.versao,
                    evidencias_usadas=a.evidencias_usadas,
                    acao_nome=a.acao.nome if a.acao else None,
                ).model_dump()
                for a in avaliacoes
            ]

            total_pages = max(1, (total + filters.limit - 1) // filters.limit)
            page = (filters.offset // filters.limit) + 1

            return AdminPaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=filters.limit,
                total_pages=total_pages,
            )

    @staticmethod
    async def get_avaliacao(
        avaliacao_id: str,
    ) -> AdminAvaliacaoRead | None:
        """Busca uma avaliação por ID."""
        async with get_session() as session:
            result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.id == avaliacao_id)
                .options(joinedload(Avaliacao.acao))
            )
            avaliacao = result.scalars().unique().one_or_none()
            if not avaliacao:
                return None
            return AdminAvaliacaoRead(
                id=avaliacao.id,
                acao_id=avaliacao.acao_id,
                status_avaliado=avaliacao.status_avaliado,
                justificativa=avaliacao.justificativa,
                avaliado_por=avaliacao.avaliado_por,
                data_avaliacao=avaliacao.data_avaliacao,
                versao=avaliacao.versao,
                evidencias_usadas=avaliacao.evidencias_usadas,
                acao_nome=avaliacao.acao.nome if avaliacao.acao else None,
            )

    @staticmethod
    async def create_avaliacao(
        data: AdminAvaliacaoCreate,
    ) -> AdminAvaliacaoRead:
        """Cria uma nova avaliação.

        Raises:
            ValueError: Se já existir uma avaliação com o mesmo ID ou mesma
                combinação (acao_id, versao).
        """
        async with get_session() as session:
            existing = await session.execute(
                select(Avaliacao.id).where(Avaliacao.id == data.id).limit(1)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Avaliação já existe com ID: {data.id}")

            dup = await session.execute(
                select(Avaliacao).where(
                    Avaliacao.acao_id == data.acao_id,
                    Avaliacao.versao == data.versao,
                )
            )
            if dup.scalar_one_or_none():
                raise ValueError(
                    f"Já existe uma avaliação versão {data.versao} para a ação '{data.acao_id}'"
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
                raise ValueError(f"Avaliação já existe com ID: {data.id}")
            logger.info(f"Avaliação criada (admin): {avaliacao.id}")

            return AdminAvaliacaoRead(
                id=avaliacao.id,
                acao_id=avaliacao.acao_id,
                status_avaliado=avaliacao.status_avaliado,
                justificativa=avaliacao.justificativa,
                avaliado_por=avaliacao.avaliado_por,
                data_avaliacao=avaliacao.data_avaliacao,
                versao=avaliacao.versao,
                evidencias_usadas=avaliacao.evidencias_usadas,
            )

    @staticmethod
    async def update_avaliacao(
        avaliacao_id: str,
        data: AdminAvaliacaoUpdate,
    ) -> AdminAvaliacaoRead | None:
        """Atualiza uma avaliação criando uma NOVA versão (histórico imutável).

        O registro original é preservado intacto; a edição gera uma nova
        Avaliacao com versão incrementada (máximo atual + 1), conforme a regra
        de imutabilidade do histórico de avaliações.
        """
        async with get_session() as session:
            result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.id == avaliacao_id)
                .options(joinedload(Avaliacao.acao))
            )
            avaliacao = result.scalars().unique().one_or_none()
            if not avaliacao:
                return None

            # Próxima versão = máximo atual da ação + 1 (nunca sobrescreve)
            max_result = await session.execute(
                select(func.max(Avaliacao.versao)).where(Avaliacao.acao_id == avaliacao.acao_id)
            )
            next_version = (max_result.scalar() or 0) + 1

            nova_avaliacao = Avaliacao(
                id=f"{avaliacao_id}_v{next_version}"[:64],
                acao_id=avaliacao.acao_id,
                status_avaliado=(
                    data.status_avaliado
                    if data.status_avaliado is not None
                    else avaliacao.status_avaliado
                ),
                justificativa=(
                    data.justificativa
                    if data.justificativa is not None
                    else avaliacao.justificativa
                ),
                avaliado_por=avaliacao.avaliado_por,
                data_avaliacao=date.today(),
                versao=next_version,
                evidencias_usadas=avaliacao.evidencias_usadas,
            )
            session.add(nova_avaliacao)
            await session.flush()
            logger.info(
                f"Avaliação atualizada (admin): {avaliacao_id} -> {nova_avaliacao.id} "
                f"(v{next_version})"
            )

            return AdminAvaliacaoRead(
                id=nova_avaliacao.id,
                acao_id=nova_avaliacao.acao_id,
                status_avaliado=nova_avaliacao.status_avaliado,
                justificativa=nova_avaliacao.justificativa,
                avaliado_por=nova_avaliacao.avaliado_por,
                data_avaliacao=nova_avaliacao.data_avaliacao,
                versao=nova_avaliacao.versao,
                evidencias_usadas=nova_avaliacao.evidencias_usadas,
                acao_nome=avaliacao.acao.nome if avaliacao.acao else None,
            )

    @staticmethod
    async def get_avaliacao_history(
        acao_id: str,
    ) -> list[AdminAvaliacaoRead]:
        """Retorna histórico de avaliações de uma ação."""
        async with get_session() as session:
            result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .options(joinedload(Avaliacao.acao))
                .order_by(
                    desc(Avaliacao.data_avaliacao),
                    desc(Avaliacao.versao),
                )
            )
            avaliacoes = result.scalars().unique().all()
            return [
                AdminAvaliacaoRead(
                    id=a.id,
                    acao_id=a.acao_id,
                    status_avaliado=a.status_avaliado,
                    justificativa=a.justificativa,
                    avaliado_por=a.avaliado_por,
                    data_avaliacao=a.data_avaliacao,
                    versao=a.versao,
                    evidencias_usadas=a.evidencias_usadas,
                    acao_nome=a.acao.nome if a.acao else None,
                )
                for a in avaliacoes
            ]

    # -----------------------------------------------------------------------
    # Eventos
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_eventos(
        filters: AdminEventoFilter,
    ) -> AdminPaginatedResponse:
        """Lista eventos com filtros e paginação."""
        async with get_session() as session:
            query = select(Evento).options(joinedload(Evento.acao))

            if filters.acao_id:
                query = query.where(Evento.acao_id == filters.acao_id)
            if filters.tipo:
                query = query.where(Evento.tipo == filters.tipo)

            count_query = select(func.count()).select_from(query.subquery())
            total = await session.scalar(count_query) or 0

            query = query.order_by(desc(Evento.data_evento))
            query = query.offset(filters.offset).limit(filters.limit)

            result = await session.execute(query)
            eventos = result.scalars().unique().all()

            items = [
                AdminEventoRead(
                    id=e.id,
                    acao_id=e.acao_id or "",
                    tipo=str(e.tipo.value) if hasattr(e.tipo, "value") else str(e.tipo),
                    descricao=e.descricao,
                    data_evento=e.data_evento,
                    fonte_url=e.fonte_url,
                    acao_nome=e.acao.nome if e.acao else None,
                ).model_dump()
                for e in eventos
            ]

            total_pages = max(1, (total + filters.limit - 1) // filters.limit)
            page = (filters.offset // filters.limit) + 1

            return AdminPaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=filters.limit,
                total_pages=total_pages,
            )

    # -----------------------------------------------------------------------
    # Dashboard
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_dashboard() -> AdminDashboard:
        """Retorna dados do dashboard admin."""
        async with get_session() as session:
            # Total de ações
            result = await session.execute(select(func.count(Acao.id)))
            total_acoes = result.scalar() or 0

            # Ações por status
            result = await session.execute(
                select(Acao.status, func.count(Acao.id)).group_by(Acao.status)
            )
            acoes_por_status = {
                row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in result
            }

            acoes_com_status = sum(
                count for status, count in acoes_por_status.items() if status != "nao_iniciado"
            )
            acoes_sem_status = total_acoes - acoes_com_status

            # Total de evidências
            result = await session.execute(select(func.count(Evidencia.id)))
            total_evidencias = result.scalar() or 0

            # Evidências por tipo
            result = await session.execute(
                select(Evidencia.tipo, func.count(Evidencia.id)).group_by(Evidencia.tipo)
            )
            evidencias_por_tipo = {
                row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in result
            }

            # Evidências sem vínculo (pendentes)
            result = await session.execute(
                select(func.count(Evidencia.id))
                .outerjoin(
                    VinculoEvidencia,
                    Evidencia.id == VinculoEvidencia.evidencia_id,
                )
                .where(VinculoEvidencia.id.is_(None))
            )
            evidencias_pendentes = result.scalar() or 0

            # Total de vínculos
            result = await session.execute(select(func.count(VinculoEvidencia.id)))
            total_vinculos = result.scalar() or 0

            # Vínculos propostos (aguardando revisão humana)
            result = await session.execute(
                select(func.count(VinculoEvidencia.id)).where(
                    VinculoEvidencia.estado == EstadoVinculo.proposto
                )
            )
            vinculos_pendentes = result.scalar() or 0

            # Total de avaliações
            result = await session.execute(select(func.count(Avaliacao.id)))
            total_avaliacoes = result.scalar() or 0

            metrics = AdminDashboardMetrics(
                total_acoes=total_acoes,
                acoes_com_status=acoes_com_status,
                acoes_sem_status=acoes_sem_status,
                total_evidencias=total_evidencias,
                evidencias_pendentes=evidencias_pendentes,
                total_vinculos=total_vinculos,
                vinculos_pendentes=vinculos_pendentes,
                total_avaliacoes=total_avaliacoes,
                acoes_por_status=acoes_por_status,
                evidencias_por_tipo=evidencias_por_tipo,
            )

            # Últimas coletas
            result = await session.execute(
                select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(10)
            )
            ingestion_runs = list(result.scalars().all())
            ultimas_coletas = [
                AdminIngestionStatus(
                    id=r.id,  # type: ignore[attr-defined]
                    source=r.source,  # type: ignore[attr-defined]
                    started_at=r.started_at,  # type: ignore[attr-defined]
                    finished_at=r.finished_at,  # type: ignore[attr-defined]
                    status=r.status,  # type: ignore[attr-defined]
                    items_fetched=r.items_fetched,  # type: ignore[attr-defined]
                    items_new=r.items_new,  # type: ignore[attr-defined]
                    items_updated=r.items_updated,  # type: ignore[attr-defined]
                    error_message=r.error_message,  # type: ignore[attr-defined]
                )
                for r in ingestion_runs
            ]

            # Alertas de qualidade
            alertas = await AdminService._generate_quality_alerts(session)

            return AdminDashboard(
                metrics=metrics,
                ultimas_coletas=ultimas_coletas,
                alertas=alertas,
            )

    @staticmethod
    async def _generate_quality_alerts(
        session: AsyncSession,
    ) -> list[AdminQualityAlert]:
        """Gera alertas de qualidade para o dashboard."""
        alertas: list[AdminQualityAlert] = []

        # Alerta: ações sem evidência
        result = await session.execute(
            select(Acao.id, Acao.nome)
            .outerjoin(VinculoEvidencia, Acao.id == VinculoEvidencia.acao_id)
            .where(VinculoEvidencia.id.is_(None))
            .limit(5)
        )
        acoes_sem_evidencia = result.all()
        if acoes_sem_evidencia:
            alertas.append(
                AdminQualityAlert(
                    tipo="acoes_sem_evidencia",
                    descricao=(f"{len(acoes_sem_evidencia)} ação(ões) sem evidência vinculada"),
                    severidade="warning",
                )
            )

        # Alerta: evidências com baixa confiança
        result = await session.execute(
            select(func.count(Evidencia.id)).where(Evidencia.confianca < 0.5)
        )
        baixa_confianca = result.scalar() or 0
        if baixa_confianca > 0:
            alertas.append(
                AdminQualityAlert(
                    tipo="evidencias_baixa_confianca",
                    descricao=(f"{baixa_confianca} evidência(s) com confiança abaixo de 50%"),
                    severidade="info",
                )
            )

        # Alerta: ingestões com erro
        result = await session.execute(
            select(func.count(IngestionRun.id)).where(IngestionRun.status == "error")
        )
        ingestoes_erro = result.scalar() or 0
        if ingestoes_erro > 0:
            alertas.append(
                AdminQualityAlert(
                    tipo="ingestoes_com_erro",
                    descricao=(f"{ingestoes_erro} ingestão(ões) com erro"),
                    severidade="error",
                )
            )

        return alertas
