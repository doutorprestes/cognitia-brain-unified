"""Router para endpoints de escrita — IA Brasil.

Endpoints para:
- Criação de evidências
- Criação de fontes
- Criação de vínculos
- Criação de avaliações
- Criação de eventos

Todos os endpoints requerem autenticação via API Key.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from src.core.limiter import RATE_LIMIT_AUTHENTICATED, RATE_LIMIT_WRITE, limiter
from src.modules.auth.dependencies import get_contributor_api_key
from src.modules.evidence_ingestion.schemas import (
    AvaliacaoCreateExtended,
    EventoCreateExtended,
    EvidenciaCreateExtended,
    FonteCreateExtended,
    VinculoCreateExtended,
)
from src.modules.evidence_ingestion.service import EvidenceService

router = APIRouter(prefix="/evidencias", tags=["evidências"])

# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------


@router.post("/fontes", response_model=FonteCreateExtended, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT_WRITE)
async def create_fonte(
    request: Request,
    data: FonteCreateExtended,
    _role: str = Depends(get_contributor_api_key),
) -> FonteCreateExtended:
    """Cria uma nova fonte.

    Requer role: contributor ou admin
    """
    try:
        await EvidenceService.create_fonte(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Conflito: registro duplicado ou violação de restrição"),
            ) from e
        raise
    return data.model_dump()  # type: ignore[return-value]


@router.get("/fontes/{fonte_id}", response_model=FonteCreateExtended)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_fonte(
    request: Request,
    fonte_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> FonteCreateExtended:
    """Busca uma fonte por ID."""
    fonte = await EvidenceService.get_fonte(fonte_id)
    if not fonte:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fonte não encontrada: {fonte_id}",
        )
    return FonteCreateExtended(
        id=fonte.id,
        url=fonte.url,
        titulo=fonte.titulo,
        instituicao_emissora=fonte.instituicao_emissora,
        tipo_documental=fonte.tipo_documental,
        data_publicacao=fonte.data_publicacao,
        data_coleta=fonte.data_coleta,
        hash_conteudo=fonte.hash_conteudo,
    )


@router.get("/fontes")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def list_fontes(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    _role: str = Depends(get_contributor_api_key),
) -> list[FonteCreateExtended]:
    """Lista fontes paginadas."""
    fontes = await EvidenceService.list_fontes(limit=limit, offset=offset)
    return [
        FonteCreateExtended(
            id=f.id,
            url=f.url,
            titulo=f.titulo,
            instituicao_emissora=f.instituicao_emissora,
            tipo_documental=f.tipo_documental,
            data_publicacao=f.data_publicacao,
            data_coleta=f.data_coleta,
            hash_conteudo=f.hash_conteudo,
        )
        for f in fontes
    ]


# ---------------------------------------------------------------------------
# Evidências
# ---------------------------------------------------------------------------


@router.post("/", response_model=EvidenciaCreateExtended, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT_WRITE)
async def create_evidencia(
    request: Request,
    data: EvidenciaCreateExtended,
    _role: str = Depends(get_contributor_api_key),
) -> EvidenciaCreateExtended:
    """Cria uma nova evidência.

    Requer role: contributor ou admin
    """
    try:
        await EvidenceService.create_evidencia(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Conflito: registro duplicado ou violação de restrição"),
            ) from e
        raise
    return data.model_dump()  # type: ignore[return-value]


@router.get("/{evidencia_id}", response_model=EvidenciaCreateExtended)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_evidencia(
    request: Request,
    evidencia_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> EvidenciaCreateExtended:
    """Busca uma evidência por ID."""
    evidencia = await EvidenceService.get_evidencia(evidencia_id)
    if not evidencia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidência não encontrada: {evidencia_id}",
        )
    return EvidenciaCreateExtended(
        id=evidencia.id,
        fonte_id=evidencia.fonte_id,
        tipo=evidencia.tipo,
        trecho=evidencia.trecho,
        resumo=evidencia.resumo,
        data_evidencia=evidencia.data_evidencia,
        confianca=evidencia.confianca,
    )


@router.get("/")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def list_evidencias(
    request: Request,
    fonte_id: str | None = None,
    tipo: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _role: str = Depends(get_contributor_api_key),
) -> list[EvidenciaCreateExtended]:
    """Lista evidências com filtros opcionais."""
    evidencias = await EvidenceService.list_evidencias(
        fonte_id=fonte_id, tipo=tipo, limit=limit, offset=offset
    )
    return [
        EvidenciaCreateExtended(
            id=e.id,
            fonte_id=e.fonte_id,
            tipo=e.tipo,
            trecho=e.trecho,
            resumo=e.resumo,
            data_evidencia=e.data_evidencia,
            confianca=e.confianca,
        )
        for e in evidencias
    ]


@router.get("/search")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def search_evidencias(
    request: Request,
    q: str,
    limit: int = 50,
    _role: str = Depends(get_contributor_api_key),
) -> list[EvidenciaCreateExtended]:
    """Busca evidências por texto."""
    evidencias = await EvidenceService.search_evidencias(query=q, limit=limit)
    return [
        EvidenciaCreateExtended(
            id=e.id,
            fonte_id=e.fonte_id,
            tipo=e.tipo,
            trecho=e.trecho,
            resumo=e.resumo,
            data_evidencia=e.data_evidencia,
            confianca=e.confianca,
        )
        for e in evidencias
    ]


# ---------------------------------------------------------------------------
# Vínculos
# ---------------------------------------------------------------------------


@router.post(
    "/vinculos",
    response_model=VinculoCreateExtended,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_WRITE)
async def create_vinculo(
    request: Request,
    data: VinculoCreateExtended,
    _role: str = Depends(get_contributor_api_key),
) -> VinculoCreateExtended:
    """Cria um novo vínculo entre evidência e ação/meta.

    Requer role: contributor ou admin
    """
    try:
        await EvidenceService.create_vinculo(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Conflito: registro duplicado ou violação de restrição"),
            ) from e
        raise
    return data.model_dump()  # type: ignore[return-value]


@router.get("/vinculos/{vinculo_id}", response_model=VinculoCreateExtended)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_vinculo(
    request: Request,
    vinculo_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> VinculoCreateExtended:
    """Busca um vínculo por ID."""
    vinculo = await EvidenceService.get_vinculo(vinculo_id)
    if not vinculo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vínculo não encontrado: {vinculo_id}",
        )
    return VinculoCreateExtended(
        id=vinculo.id,
        evidencia_id=vinculo.evidencia_id,
        acao_id=vinculo.acao_id,
        meta_id=vinculo.meta_id,
        justificativa=vinculo.justificativa,
        criado_por=vinculo.criado_por,
    )


@router.get("/vinculos")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def list_vinculos(
    request: Request,
    evidencia_id: str | None = None,
    acao_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _role: str = Depends(get_contributor_api_key),
) -> list[VinculoCreateExtended]:
    """Lista vínculos com filtros opcionais."""
    vinculos = await EvidenceService.list_vinculos(
        evidencia_id=evidencia_id, acao_id=acao_id, limit=limit, offset=offset
    )
    return [
        VinculoCreateExtended(
            id=v.id,
            evidencia_id=v.evidencia_id,
            acao_id=v.acao_id,
            meta_id=v.meta_id,
            justificativa=v.justificativa,
            criado_por=v.criado_por,
        )
        for v in vinculos
    ]


# ---------------------------------------------------------------------------
# Avaliações
# ---------------------------------------------------------------------------


@router.post(
    "/avaliacoes",
    response_model=AvaliacaoCreateExtended,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_WRITE)
async def create_avaliacao(
    request: Request,
    data: AvaliacaoCreateExtended,
    _role: str = Depends(get_contributor_api_key),
) -> AvaliacaoCreateExtended:
    """Cria uma nova avaliação.

    Requer role: contributor ou admin

    Regras de negócio:
    - Toda avaliação deve ter ao menos uma evidência vinculada, exceto status 'Não iniciado'
    """
    try:
        await EvidenceService.create_avaliacao(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Conflito: registro duplicado ou violação de restrição"),
            ) from e
        raise
    return data.model_dump()  # type: ignore[return-value]


@router.get("/avaliacoes/{avaliacao_id}", response_model=AvaliacaoCreateExtended)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_avaliacao(
    request: Request,
    avaliacao_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> AvaliacaoCreateExtended:
    """Busca uma avaliação por ID."""
    avaliacao = await EvidenceService.get_avaliacao(avaliacao_id)
    if not avaliacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Avaliação não encontrada: {avaliacao_id}",
        )
    return AvaliacaoCreateExtended(
        id=avaliacao.id,
        acao_id=avaliacao.acao_id,
        status_avaliado=avaliacao.status_avaliado,
        justificativa=avaliacao.justificativa,
        avaliado_por=avaliacao.avaliado_por,
        data_avaliacao=avaliacao.data_avaliacao,
        versao=avaliacao.versao,
    )


@router.get("/avaliacoes")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def list_avaliacoes(
    request: Request,
    acao_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _role: str = Depends(get_contributor_api_key),
) -> list[AvaliacaoCreateExtended]:
    """Lista avaliações com filtros opcionais."""
    avaliacoes = await EvidenceService.list_avaliacoes(
        acao_id=acao_id, status=status, limit=limit, offset=offset
    )
    return [
        AvaliacaoCreateExtended(
            id=a.id,
            acao_id=a.acao_id,
            status_avaliado=a.status_avaliado,
            justificativa=a.justificativa,
            avaliado_por=a.avaliado_por,
            data_avaliacao=a.data_avaliacao,
            versao=a.versao,
        )
        for a in avaliacoes
    ]


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------


@router.post(
    "/eventos",
    response_model=EventoCreateExtended,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_WRITE)
async def create_evento(
    request: Request,
    data: EventoCreateExtended,
    _role: str = Depends(get_contributor_api_key),
) -> EventoCreateExtended:
    """Cria um novo evento.

    Requer role: contributor ou admin
    """
    try:
        await EvidenceService.create_evento(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Conflito: registro duplicado ou violação de restrição"),
            ) from e
        raise
    return data.model_dump()  # type: ignore[return-value]


@router.get("/eventos/{evento_id}", response_model=EventoCreateExtended)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_evento(
    request: Request,
    evento_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> EventoCreateExtended:
    """Busca um evento por ID."""
    evento = await EvidenceService.get_evento(evento_id)
    if not evento:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento não encontrado: {evento_id}",
        )
    return EventoCreateExtended(
        id=evento.id,
        acao_id=evento.acao_id,
        tipo=evento.tipo,
        descricao=evento.descricao,
        data_evento=evento.data_evento,
        fonte_url=evento.fonte_url,
    )


@router.get("/eventos")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def list_eventos(
    request: Request,
    acao_id: str | None = None,
    tipo: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _role: str = Depends(get_contributor_api_key),
) -> list[EventoCreateExtended]:
    """Lista eventos com filtros opcionais."""
    eventos = await EvidenceService.list_eventos(
        acao_id=acao_id, tipo=tipo, limit=limit, offset=offset
    )
    return [
        EventoCreateExtended(
            id=e.id,
            acao_id=e.acao_id,
            tipo=e.tipo,
            descricao=e.descricao,
            data_evento=e.data_evento,
            fonte_url=e.fonte_url,
        )
        for e in eventos
    ]


# ---------------------------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------------------------


@router.get("/stats")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_stats(
    request: Request,
    _role: str = Depends(get_contributor_api_key),
) -> dict[str, Any]:
    """Retorna estatísticas de evidências, vínculos e avaliações."""
    return await EvidenceService.get_stats()
