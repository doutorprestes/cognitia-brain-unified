"""IA Brasil — Export Router.

Endpoints públicos de exportação de dados abertos:
- GET /export/acoes.csv — todas as ações com status atual e instituições
- GET /export/acoes.json — idem em JSON
- GET /export/acoes.xlsx — idem em XLSX
- GET /export/acoes.pdf — idem em PDF
- GET /export/eixo/{id}.csv, .json, .xlsx, .pdf — exportação por eixo

Conforme issue #19: exportação de dados abertos (CSV e JSON) por eixo e geral.
Conforme issue #1030: exportação em mais formatos (PDF, XLSX).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger
from sqlalchemy.exc import IntegrityError

from src.core.db import settings as app_settings
from src.core.json_encoder import dumps_with_encoder
from src.core.limiter import RATE_LIMIT_EXPORT, limiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.export.catalog import build_datapackage_json
from src.modules.export.service import CSV_ACOES_HEADERS, ExportCache, ExportService, get_db

router = APIRouter(prefix="/export", tags=["export"])

# ============================================================================
# Endpoints - Exportação Geral
# ============================================================================


@router.get("/acoes.csv")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_acoes_csv(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar todas as ações em formato CSV.

    Retorna um arquivo CSV com todas as ações do PBIA, incluindo:
    - Informações do eixo e programa
    - Código e nome da ação
    - Status atual e data da avaliação
    - Instituições responsáveis
    - Contagem de metas
    - Referência de origem

    Headers:
    - Content-Type: text/csv; charset=utf-8
    - Content-Disposition: attachment; filename=acoes.csv
    - Cache-Control: public, max-age=3600
    """
    cache_key = "export_acoes_csv"

    # Verificar cache
    cached_content = ExportCache.get_cached(cache_key)
    if cached_content:
        logger.debug("Servindo conteúdo cacheado para /export/acoes.csv")
    else:
        logger.debug("Gerando novo conteúdo para /export/acoes.csv")
        # Obter dados e gerar CSV
        data = await ExportService.get_all_acoes_data(session)
        cached_content = ExportService.generate_csv(data)
        ExportCache.set_cached(cache_key, cached_content)

    # Configurar headers
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": "attachment; filename=acoes.csv",
        "Cache-Control": "public, max-age=3600",
    }

    return Response(content=cached_content, headers=headers)


@router.get("/acoes.json")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_acoes_json(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar todas as ações em formato JSON.

    Retorna um arquivo JSON com todas as ações do PBIA, incluindo:
    - Informações do eixo e programa
    - Código e nome da ação
    - Status atual e data da avaliação
    - Instituições responsáveis
    - Contagem de metas
    - Referência de origem

    Headers:
    - Content-Type: application/json; charset=utf-8
    - Content-Disposition: attachment; filename=acoes.json
    - Cache-Control: public, max-age=3600
    """
    cache_key = "export_acoes_json"

    # Verificar cache
    cached_content = ExportCache.get_cached(cache_key)
    if cached_content:
        logger.debug("Servindo conteúdo cacheado para /export/acoes.json")
    else:
        logger.debug("Gerando novo conteúdo para /export/acoes.json")
        # Obter dados e gerar JSON
        data = await ExportService.get_all_acoes_data(session)
        cached_content = ExportService.generate_json(data)
        ExportCache.set_cached(cache_key, cached_content)

    # Configurar headers
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": "attachment; filename=acoes.json",
        "Cache-Control": "public, max-age=3600",
    }

    return Response(content=cached_content, headers=headers)


@router.get("/acoes.datapackage.json")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_acoes_datapackage(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Frictionless Data Package (``datapackage.json``) do export de ações.

    Descreve o schema tabular de ``acoes.csv`` (issue #1101): perfil
    ``tabular-data-package``, metadados e os campos da distribuição.

    Headers:
    - Content-Type: application/json; charset=utf-8
    - Content-Disposition: attachment; filename=acoes.datapackage.json
    - Cache-Control: public, max-age=3600
    """
    count = await ExportService.count_acoes(session)
    payload = build_datapackage_json(
        CSV_ACOES_HEADERS,
        base_url=app_settings.public_api_url.rstrip("/"),
        count=count,
    )
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": "attachment; filename=acoes.datapackage.json",
        "Cache-Control": "public, max-age=3600",
    }
    return Response(content=dumps_with_encoder(payload, indent=2), headers=headers)


@router.get("/acoes.xlsx")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_acoes_xlsx(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar todas as ações em formato XLSX (Excel).

    Retorna um arquivo XLSX com todas as ações do PBIA, incluindo:
    - Formatação profissional com cabeçalhos estilizados
    - Largura de colunas automáticas
    - Primeira linha congelada

    Headers:
    - Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
    - Content-Disposition: attachment; filename=acoes.xlsx
    - Cache-Control: public, max-age=3600
    """
    cache_key = "export_acoes_xlsx"

    cached_bytes = ExportCache.get_cached_bytes(cache_key)
    if cached_bytes:
        logger.debug("Servindo conteúdo cacheado para /export/acoes.xlsx")
    else:
        logger.debug("Gerando novo conteúdo para /export/acoes.xlsx")
        data = await ExportService.get_all_acoes_data(session)
        cached_bytes = await ExportService.generate_xlsx_async(data)
        ExportCache.set_cached_bytes(cache_key, cached_bytes)

    headers = {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": "attachment; filename=acoes.xlsx",
        "Cache-Control": "public, max-age=3600",
    }

    return Response(content=cached_bytes, headers=headers)


@router.get("/acoes.pdf")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_acoes_pdf(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar todas as ações em formato PDF.

    Retorna um arquivo PDF com todas as ações do PBIA em tabela formatada.

    Headers:
    - Content-Type: application/pdf
    - Content-Disposition: attachment; filename=acoes.pdf
    - Cache-Control: public, max-age=3600
    """
    cache_key = "export_acoes_pdf"

    cached_bytes = ExportCache.get_cached_bytes(cache_key)
    if cached_bytes:
        logger.debug("Servindo conteúdo cacheado para /export/acoes.pdf")
    else:
        logger.debug("Gerando novo conteúdo para /export/acoes.pdf")
        data = await ExportService.get_all_acoes_data(session)
        cached_bytes = await ExportService.generate_pdf_async(data, title="Ações do PBIA 2025")
        ExportCache.set_cached_bytes(cache_key, cached_bytes)

    headers = {
        "Content-Type": "application/pdf",
        "Content-Disposition": "attachment; filename=acoes.pdf",
        "Cache-Control": "public, max-age=3600",
    }

    return Response(content=cached_bytes, headers=headers)


# ============================================================================
# Endpoints - Exportação por Eixo
# ============================================================================


@router.get("/eixo/{eixo_id}.csv")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_eixo_csv(
    request: Request,
    eixo_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar ações de um eixo específico em formato CSV.

    Args:
        eixo_id: ID do eixo para exportar

    Retorna um arquivo CSV com as ações do eixo especificado.

    Headers:
    - Content-Type: text/csv; charset=utf-8
    - Content-Disposition: attachment; filename={eixo_nome}.csv
    - Cache-Control: public, max-age=3600
    """
    try:
        cache_key = f"export_eixo_{eixo_id}_csv"

        # Verificar cache
        cached_content = ExportCache.get_cached(cache_key)
        if cached_content:
            logger.debug(f"Servindo conteúdo cacheado para /export/eixo/{eixo_id}.csv")
        else:
            logger.debug(f"Gerando novo conteúdo para /export/eixo/{eixo_id}.csv")
            # Obter dados e gerar CSV
            data = await ExportService.get_acoes_by_eixo_data(session, eixo_id)
            if not data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Eixo não encontrado ou sem ações: {eixo_id}",
                )
            cached_content = ExportService.generate_csv(data)
            ExportCache.set_cached(cache_key, cached_content)

        # Obter nome do eixo para o filename
        eixo_name = await ExportService.get_eixo_name(session, eixo_id)
        safe_filename = "".join(c if c.isalnum() else "_" for c in eixo_name)[:50]

        # Configurar headers
        headers = {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f"attachment; filename={safe_filename}.csv",
            "Cache-Control": "public, max-age=3600",
        }

        return Response(content=cached_content, headers=headers)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Conflito: registro duplicado ou violação de restrição",
        )
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Erro ao exportar eixo {eixo_id} CSV", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao exportar eixo {eixo_id} CSV",
        )


@router.get("/eixo/{eixo_id}.json")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_eixo_json(
    request: Request,
    eixo_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar ações de um eixo específico em formato JSON.

    Args:
        eixo_id: ID do eixo para exportar

    Retorna um arquivo JSON com as ações do eixo especificado.

    Headers:
    - Content-Type: application/json; charset=utf-8
    - Content-Disposition: attachment; filename={eixo_nome}.json
    - Cache-Control: public, max-age=3600
    """
    cache_key = f"export_eixo_{eixo_id}_json"

    # Verificar cache
    cached_content = ExportCache.get_cached(cache_key)
    if cached_content:
        logger.debug(f"Servindo conteúdo cacheado para /export/eixo/{eixo_id}.json")
    else:
        logger.debug(f"Gerando novo conteúdo para /export/eixo/{eixo_id}.json")
        # Obter dados e gerar JSON
        data = await ExportService.get_acoes_by_eixo_data(session, eixo_id)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"Eixo não encontrado ou sem ações: {eixo_id}",
            )
        cached_content = ExportService.generate_json(data)
        ExportCache.set_cached(cache_key, cached_content)

    # Obter nome do eixo para o filename
    eixo_name = await ExportService.get_eixo_name(session, eixo_id)
    safe_filename = "".join(c if c.isalnum() else "_" for c in eixo_name)[:50]

    return Response(
        content=cached_content.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={safe_filename}.json",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/eixo/{eixo_id}.xlsx")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_eixo_xlsx(
    request: Request,
    eixo_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar ações de um eixo específico em formato XLSX.

    Args:
        eixo_id: ID do eixo para exportar

    Headers:
    - Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
    - Content-Disposition: attachment; filename={eixo_nome}.xlsx
    - Cache-Control: public, max-age=3600
    """
    cache_key = f"export_eixo_{eixo_id}_xlsx"

    cached_bytes = ExportCache.get_cached_bytes(cache_key)
    if cached_bytes:
        logger.debug(f"Servindo conteúdo cacheado para /export/eixo/{eixo_id}.xlsx")
    else:
        logger.debug(f"Gerando novo conteúdo para /export/eixo/{eixo_id}.xlsx")
        data = await ExportService.get_acoes_by_eixo_data(session, eixo_id)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"Eixo não encontrado ou sem ações: {eixo_id}",
            )
        eixo_name = await ExportService.get_eixo_name(session, eixo_id)
        cached_bytes = await ExportService.generate_xlsx_async(data, sheet_name=eixo_name[:31])
        ExportCache.set_cached_bytes(cache_key, cached_bytes)

    eixo_name = await ExportService.get_eixo_name(session, eixo_id)
    safe_filename = "".join(c if c.isalnum() else "_" for c in eixo_name)[:50]

    headers = {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": f"attachment; filename={safe_filename}.xlsx",
        "Cache-Control": "public, max-age=3600",
    }

    return Response(content=cached_bytes, headers=headers)


@router.get("/eixo/{eixo_id}.pdf")
@limiter.limit(RATE_LIMIT_EXPORT)
async def export_eixo_pdf(
    request: Request,
    eixo_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Exportar ações de um eixo específico em formato PDF.

    Args:
        eixo_id: ID do eixo para exportar

    Headers:
    - Content-Type: application/pdf
    - Content-Disposition: attachment; filename={eixo_nome}.pdf
    - Cache-Control: public, max-age=3600
    """
    cache_key = f"export_eixo_{eixo_id}_pdf"

    cached_bytes = ExportCache.get_cached_bytes(cache_key)
    if cached_bytes:
        logger.debug(f"Servindo conteúdo cacheado para /export/eixo/{eixo_id}.pdf")
    else:
        logger.debug(f"Gerando novo conteúdo para /export/eixo/{eixo_id}.pdf")
        data = await ExportService.get_acoes_by_eixo_data(session, eixo_id)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"Eixo não encontrado ou sem ações: {eixo_id}",
            )
        eixo_name = await ExportService.get_eixo_name(session, eixo_id)
        cached_bytes = await ExportService.generate_pdf_async(data, title=f"Ações — {eixo_name}")
        ExportCache.set_cached_bytes(cache_key, cached_bytes)

    eixo_name = await ExportService.get_eixo_name(session, eixo_id)
    safe_filename = "".join(c if c.isalnum() else "_" for c in eixo_name)[:50]

    headers = {
        "Content-Type": "application/pdf",
        "Content-Disposition": f"attachment; filename={safe_filename}.pdf",
        "Cache-Control": "public, max-age=3600",
    }

    return Response(content=cached_bytes, headers=headers)
