"""Serviço de vinculação — IA Brasil.

Implementa a camada de vinculação entre evidências e ações/metas do PBIA.
Garante que toda conclusão seja rastreável até a evidência que a sustenta.
"""

from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.core.db import (
    Acao,
    EstadoVinculo,
    Evidencia,
    Meta,
    VinculoEvidencia,
    get_session,
)
from src.modules.linking.schemas import LinkCreate, LinkSearch


class LinkingService:
    """Serviço para operações de vinculação."""

    @staticmethod
    async def create_link(data: LinkCreate) -> VinculoEvidencia:
        """Cria um novo vínculo entre evidência e ação/meta.

        Valida que:
        - A evidência existe
        - A ação existe
        - Não existe vínculo duplicado para o par (evidencia_id, acao_id)
        - Se meta_id for informado, a meta deve existir e pertencer à ação

        Raises:
            ValueError: Se já existir um vínculo duplicado ou entidade não encontrada.
        """
        async with get_session() as session:
            existing = await session.execute(
                select(VinculoEvidencia).where(VinculoEvidencia.id == data.id)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Vínculo com ID '{data.id}' já existe")

            dup = await session.execute(
                select(VinculoEvidencia).where(
                    VinculoEvidencia.evidencia_id == data.evidencia_id,
                    VinculoEvidencia.acao_id == data.acao_id,
                )
            )
            if dup.scalar_one_or_none():
                raise ValueError(
                    f"Vínculo duplicado: evidência {data.evidencia_id} "
                    f"já está vinculada à ação {data.acao_id}"
                )
            # Validar que evidência existe
            evidencia_result = await session.execute(
                select(Evidencia).where(Evidencia.id == data.evidencia_id)
            )
            if not evidencia_result.scalar_one_or_none():
                raise ValueError(f"Evidência não encontrada: {data.evidencia_id}")

            # Validar que ação existe
            acao_result = await session.execute(select(Acao).where(Acao.id == data.acao_id))
            if not acao_result.scalar_one_or_none():
                raise ValueError(f"Ação não encontrada: {data.acao_id}")

            # Verificar duplicata: mesmo par (evidencia_id, acao_id)
            existing = await session.execute(
                select(VinculoEvidencia).where(
                    VinculoEvidencia.evidencia_id == data.evidencia_id,
                    VinculoEvidencia.acao_id == data.acao_id,
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(
                    f"Vínculo duplicado: evidência {data.evidencia_id} "
                    f"já está vinculada à ação {data.acao_id}"
                )

            # Validar que meta existe e pertence à ação (se informado)
            if data.meta_id:
                meta_result = await session.execute(
                    select(Meta).where(Meta.id == data.meta_id, Meta.acao_id == data.acao_id)
                )
                if not meta_result.scalar_one_or_none():
                    raise ValueError(f"Meta não encontrada ou não pertence à ação: {data.meta_id}")

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
                raise ValueError(
                    f"Vínculo duplicado: evidência {data.evidencia_id} "
                    f"já está vinculada à ação {data.acao_id}"
                )
            logger.info(f"Vínculo criado: {vinculo.id} ({data.evidencia_id} -> {data.acao_id})")
            return vinculo

    @staticmethod
    async def get_link(link_id: str) -> VinculoEvidencia | None:
        """Busca um vínculo por ID com detalhes."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia)
                .where(VinculoEvidencia.id == link_id)
                .options(
                    joinedload(VinculoEvidencia.evidencia),
                    joinedload(VinculoEvidencia.acao),
                    joinedload(VinculoEvidencia.meta),
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_links(params: LinkSearch) -> list[VinculoEvidencia]:
        """Lista vínculos com filtros."""
        async with get_session() as session:
            stmt = select(VinculoEvidencia).order_by(desc(VinculoEvidencia.id))

            if params.evidencia_id:
                stmt = stmt.where(VinculoEvidencia.evidencia_id == params.evidencia_id)
            if params.acao_id:
                stmt = stmt.where(VinculoEvidencia.acao_id == params.acao_id)
            if params.meta_id:
                stmt = stmt.where(VinculoEvidencia.meta_id == params.meta_id)
            if params.criado_por:
                stmt = stmt.where(VinculoEvidencia.criado_por == params.criado_por)

            result = await session.execute(stmt.limit(params.limit).offset(params.offset))
            return list(result.scalars())

    @staticmethod
    async def get_links_by_acao(acao_id: str) -> list[VinculoEvidencia]:
        """Busca todos os vínculos para uma ação específica."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia)
                .where(VinculoEvidencia.acao_id == acao_id)
                .order_by(desc(VinculoEvidencia.id))
                .options(
                    joinedload(VinculoEvidencia.evidencia).joinedload(Evidencia.fonte),
                    joinedload(VinculoEvidencia.meta),
                )
            )
            return list(result.scalars())

    @staticmethod
    async def get_links_by_evidencia(evidencia_id: str) -> list[VinculoEvidencia]:
        """Busca todos os vínculos para uma evidência específica."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia)
                .where(VinculoEvidencia.evidencia_id == evidencia_id)
                .order_by(desc(VinculoEvidencia.id))
                .options(
                    joinedload(VinculoEvidencia.acao),
                    joinedload(VinculoEvidencia.meta),
                )
            )
            return list(result.scalars())

    @staticmethod
    async def delete_link(link_id: str) -> bool:
        """Remove um vínculo pelo ID."""
        async with get_session() as session:
            result = await session.execute(
                select(VinculoEvidencia).where(VinculoEvidencia.id == link_id)
            )
            vinculo = result.scalar_one_or_none()
            if vinculo:
                await session.delete(vinculo)
                await session.flush()
                logger.info(f"Vínculo removido: {link_id}")
                return True
            return False

    @staticmethod
    async def get_link_stats() -> dict[str, Any]:
        """Retorna estatísticas de vinculação."""
        async with get_session() as session:
            # Total de vínculos
            result = await session.execute(select(func.count()).select_from(VinculoEvidencia))
            total = result.scalar() or 0

            # Vínculos por ação
            result = await session.execute(
                select(VinculoEvidencia.acao_id, func.count(VinculoEvidencia.id)).group_by(
                    VinculoEvidencia.acao_id
                )
            )
            por_acao = {row[0]: row[1] for row in result}

            # Vínculos por tipo de evidência
            result = await session.execute(
                select(Evidencia.tipo, func.count(VinculoEvidencia.id))
                .join(Evidencia, Evidencia.id == VinculoEvidencia.evidencia_id)
                .group_by(Evidencia.tipo)
            )
            por_tipo_evidencia = {row[0]: row[1] for row in result}

            return {
                "total_vinculos": total,
                "vinculos_por_acao": por_acao,
                "vinculos_por_tipo_evidencia": por_tipo_evidencia,
            }
