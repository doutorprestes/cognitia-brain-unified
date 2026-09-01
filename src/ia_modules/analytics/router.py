"""IA Brasil — Analytics Router.

Endpoints analíticos que demonstram capacidades únicas do IA-Brasil:
1. Boletim "Prometido vs. Realizado"
2. Execução Financeira (Empenho/Liq./Pag.)
3. Hierarquia de Evidências com Base Jurídica
4. Proveniência de Dados (FAIR)
5. Auditoria Independente (contradições)
6. Mapa de Capacidade Institucional
7. Relatório de Lacunas de Política Pública
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import (
    Acao,
    AcaoInstituicao,
    Avaliacao,
    Eixo,
    Evidencia,
    ExecucaoFinanceira,
    Fonte,
    Instituicao,
    Programa,
    Recurso,
    StatusAcao,
    VinculoEvidencia,
    get_session,
)
from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter
from src.core.pii import log_evidence_access, redact_pii
from src.modules.analytics.schemas import (
    AuditoriaResponse,
    BoletimResponse,
    Contradicao,
    DistribuicaoEvidencia,
    EixoBreakdown,
    ExecucaoEixo,
    ExecucaoFinanceiraResponse,
    ExecucaoPorAno,
    FonteInfo,
    HierarquiaResponse,
    InstituicaoMetrica,
    Lacuna,
    LacunasResponse,
    MapaInstitucionalResponse,
    ProvenienciaResponse,
    StatusCount,
    TipoEvidenciaPeso,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session."""
    async with get_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Entrega 1: Boletim "Prometido vs. Realizado"
# ---------------------------------------------------------------------------


@router.get("/boletim", response_model=BoletimResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def boletim_prometido_vs_realizado(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> BoletimResponse:
    """Boletim executivo: quantas ações do PBIA foram prometidas vs. realizadas.

    Demonstra: capacidade de gestão pública e mensuração de implementação.
    """
    # Total de ações
    total = await session.scalar(select(func.count()).select_from(Acao))

    # Por status
    status_stmt = select(Acao.status, func.count(Acao.id)).select_from(Acao).group_by(Acao.status)
    status_result = await session.execute(status_stmt)
    status_rows = status_result.fetchall()

    por_status = [
        StatusCount(
            status=str(row[0].value) if hasattr(row[0], "value") else str(row[0]),
            quantidade=row[1],
            percentual=round(row[1] / total * 100, 1) if total else 0,
        )
        for row in status_rows
    ]

    # Por eixo — agregação única via GROUP BY (sem N+1 por eixo)
    eixo_stmt = select(Eixo).order_by(Eixo.numero)
    eixos = (await session.execute(eixo_stmt)).scalars().all()

    eixo_agg_stmt = (
        select(Programa.eixo_id, Acao.status, func.count(Acao.id))
        .join(Acao, Acao.programa_id == Programa.id)
        .group_by(Programa.eixo_id, Acao.status)
    )
    eixo_agg_rows = (await session.execute(eixo_agg_stmt)).all()

    eixo_counts: dict[str, dict[str, int]] = {}
    for eixo_id, status, qtd in eixo_agg_rows:
        status_key = status.value if hasattr(status, "value") else str(status)
        eixo_counts.setdefault(eixo_id, {})[status_key] = qtd

    por_eixo = [
        EixoBreakdown(
            eixo=eixo.nome,
            total=sum(eixo_counts.get(eixo.id, {}).values()),
            entregues=eixo_counts.get(eixo.id, {}).get("entregue", 0),
            em_andamento=eixo_counts.get(eixo.id, {}).get("em_andamento", 0),
            parcialmente_entregue=eixo_counts.get(eixo.id, {}).get("parcialmente_entregue", 0),
            nao_iniciado=eixo_counts.get(eixo.id, {}).get("nao_iniciado", 0),
        )
        for eixo in eixos
    ]

    # Percentual de execução
    qtd_entregues = sum(s.quantidade for s in por_status if s.status == "entregue")
    pct = round(qtd_entregues / total * 100, 1) if total else 0

    return BoletimResponse(
        total_acoes=total or 0,
        por_status=por_status,
        por_eixo=por_eixo,
        percentual_execucao=pct,
        data_geracao=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Entrega 2: Execução Financeira
# ---------------------------------------------------------------------------


@router.get("/execucao-financeira", response_model=ExecucaoFinanceiraResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def execucao_financeira_analitica(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ExecucaoFinanceiraResponse:
    """Análise de execução financeira: Empenho vs. Liquidação vs. Pagamento.

    Demonstra: compreensão de direito financeiro (Lei 4.320/1964).
    """
    # Totais gerais
    total_previsto = (
        await session.scalar(select(func.coalesce(func.sum(Recurso.valor_previsto), 0))) or 0.0
    )

    # Empenho/Liquidação/Pagamento via ExecucaoFinanceira
    total_empenhado = (
        await session.scalar(select(func.coalesce(func.sum(ExecucaoFinanceira.valor_empenhado), 0)))
        or 0.0
    )
    total_liquidado = (
        await session.scalar(select(func.coalesce(func.sum(ExecucaoFinanceira.valor_liquidado), 0)))
        or 0.0
    )
    total_pago = (
        await session.scalar(select(func.coalesce(func.sum(ExecucaoFinanceira.valor_pago), 0)))
        or 0.0
    )

    # Por exercício — agregação via GROUP BY ano (issue #1095)
    por_ano_stmt = (
        select(
            ExecucaoFinanceira.ano,
            func.coalesce(func.sum(ExecucaoFinanceira.valor_empenhado), 0),
            func.coalesce(func.sum(ExecucaoFinanceira.valor_liquidado), 0),
            func.coalesce(func.sum(ExecucaoFinanceira.valor_pago), 0),
        )
        .group_by(ExecucaoFinanceira.ano)
        .order_by(ExecucaoFinanceira.ano)
    )
    por_ano_rows = (await session.execute(por_ano_stmt)).all()
    por_ano = [
        ExecucaoPorAno(
            ano=row[0],
            total_previsto=0.0,
            total_empenhado=float(row[1]),
            total_liquidado=float(row[2]),
            total_pago=float(row[3]),
        )
        for row in por_ano_rows
    ]

    ratio_emp = round(float(total_empenhado) / float(total_previsto), 4) if total_previsto else 0.0
    ratio_pag = round(float(total_pago) / float(total_empenhado), 4) if total_empenhado else 0.0

    # Por eixo — agregações via GROUP BY (2 consultas, sem N+1 por eixo)
    eixos = (await session.execute(select(Eixo).order_by(Eixo.numero))).scalars().all()

    previsto_stmt = (
        select(Programa.eixo_id, func.coalesce(func.sum(Recurso.valor_previsto), 0))
        .join(Acao, Recurso.acao_id == Acao.id)
        .join(Programa, Acao.programa_id == Programa.id)
        .group_by(Programa.eixo_id)
    )
    previsto_rows = (await session.execute(previsto_stmt)).all()
    previsto_por_eixo: dict[str, float] = {row[0]: float(row[1]) for row in previsto_rows}

    exec_stmt = (
        select(
            Programa.eixo_id,
            func.coalesce(func.sum(ExecucaoFinanceira.valor_empenhado), 0),
            func.coalesce(func.sum(ExecucaoFinanceira.valor_liquidado), 0),
            func.coalesce(func.sum(ExecucaoFinanceira.valor_pago), 0),
        )
        .join(Acao, ExecucaoFinanceira.acao_id == Acao.id)
        .join(Programa, Acao.programa_id == Programa.id)
        .group_by(Programa.eixo_id)
    )
    exec_rows = (await session.execute(exec_stmt)).all()
    exec_por_eixo: dict[str, tuple[float, float, float]] = {
        row[0]: (float(row[1]), float(row[2]), float(row[3])) for row in exec_rows
    }

    por_eixo = [
        ExecucaoEixo(
            eixo=eixo.nome,
            previsto=previsto_por_eixo.get(eixo.id, 0.0),
            empenhado=exec_por_eixo.get(eixo.id, (0.0, 0.0, 0.0))[0],
            liquidado=exec_por_eixo.get(eixo.id, (0.0, 0.0, 0.0))[1],
            pago=exec_por_eixo.get(eixo.id, (0.0, 0.0, 0.0))[2],
        )
        for eixo in eixos
    ]

    return ExecucaoFinanceiraResponse(
        total_previsto=float(total_previsto),
        total_empenhado=float(total_empenhado),
        total_liquidado=float(total_liquidado),
        total_pago=float(total_pago),
        ratio_empenhado_previsto=ratio_emp,
        ratio_pago_empenhado=ratio_pag,
        por_eixo=por_eixo,
        por_ano=por_ano,
    )


# ---------------------------------------------------------------------------
# Entrega 3: Hierarquia de Evidências
# ---------------------------------------------------------------------------


# Pesos que espelham a hierarquia normativa brasileira
_HIERARQUIA: list[dict[str, str | float]] = [
    {
        "tipo": "ato_oficial",
        "peso": 1.0,
        "descricao": "Atos oficiais: Decreto, Portaria, Edital publicados no DOU",
        "base_juridica": "Hierarquia normativa (CF > Lei > Decreto > Portaria)",
    },
    {
        "tipo": "relatorio_ministerial",
        "peso": 0.9,
        "descricao": "Relatórios oficiais de órgãos governamentais",
        "base_juridica": "LAI (Lei 12.527/2011) — obrigação de transparência",
    },
    {
        "tipo": "relatorio",
        "peso": 0.8,
        "descricao": "Relatórios técnicos e documentos institucionais",
        "base_juridica": "Lei do Governo Digital (14.129/2021)",
    },
    {
        "tipo": "pagina_institucional",
        "peso": 0.7,
        "descricao": "Páginas oficiais de órgãos gov.br",
        "base_juridica": "LAI — informações públicas obrigatórias",
    },
    {
        "tipo": "edital",
        "peso": 0.7,
        "descricao": "Editais de chamadas públicas e seleção",
        "base_juridica": "Lei 8.666/1993 e Lei 14.133/2021",
    },
    {
        "tipo": "noticia",
        "peso": 0.6,
        "descricao": "Matérias jornalísticas e imprensa",
        "base_juridica": "CF Art. 220 — liberdade de imprensa",
    },
    {
        "tipo": "outro",
        "peso": 0.3,
        "descricao": "Outras fontes não categorizadas",
        "base_juridica": "Critério de confiança reduzida",
    },
]


@router.get("/hierarquia-evidencias", response_model=HierarquiaResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def hierarquia_evidencias(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> HierarquiaResponse:
    """Hierarquia de evidências com pesos e base jurídica.

    Demonstra: jurista que codifica hierarquia normativa em software.
    """
    tipos = [
        TipoEvidenciaPeso(
            tipo=h["tipo"],
            peso=h["peso"],
            descricao=h["descricao"],
            base_juridica=h["base_juridica"],
        )
        for h in _HIERARQUIA
    ]

    # Distribuição real
    dist_stmt = select(Fonte.tipo_documental, func.count(Fonte.id)).group_by(Fonte.tipo_documental)
    dist_result = await session.execute(dist_stmt)
    dist_rows = dist_result.fetchall()

    total_fontes = sum(row[1] for row in dist_rows) or 1
    distribuicao = [
        DistribuicaoEvidencia(
            tipo=str(row[0]) if row[0] else "outro",
            quantidade=row[1],
            percentual=round(row[1] / total_fontes * 100, 1),
        )
        for row in dist_rows
    ]

    return HierarquiaResponse(tipos=tipos, distribuicao=distribuicao)


# ---------------------------------------------------------------------------
# Entrega 4: Proveniência de Dados
# ---------------------------------------------------------------------------


@router.get("/proveniencia", response_model=ProvenienciaResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def proveniencia_dados(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProvenienciaResponse:
    """Proveniência de dados: fontes, hashes, datas de coleta.

    Demonstra: rigor acadêmico — FAIR data principles.
    """
    fontes_stmt = select(Fonte).order_by(Fonte.data_coleta.desc())
    fontes_result = await session.execute(fontes_stmt)
    fontes = list(fontes_result.scalars())

    fontes_info = [
        FonteInfo(
            id=f.id,
            url=f.url,
            titulo=f.titulo,
            tipo_documental=f.tipo_documental or "outro",
            data_coleta=f.data_coleta.isoformat() if f.data_coleta else None,
            instituicao_emissora=f.instituicao_emissora,
        )
        for f in fontes
    ]

    ultima = fontes[0].data_coleta.isoformat() if fontes and fontes[0].data_coleta else None

    return ProvenienciaResponse(
        fontes=fontes_info,
        total_fontes=len(fontes_info),
        ultima_coleta=ultima,
    )


# ---------------------------------------------------------------------------
# Entrega 5: Auditoria Independente
# ---------------------------------------------------------------------------


@router.get("/auditoria-independente", response_model=AuditoriaResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def auditoria_independente(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuditoriaResponse:
    """Auditoria independente: ações com status contraditório.

    Demonstra: profissional de governança que verifica alegações governamentais.
    """
    # Busca ações com status contraditório
    contradicoes_stmt = select(Acao).where(Acao.status == StatusAcao.contraditoriro)
    contradicoes_result = await session.execute(contradicoes_stmt)
    acoes_contradicao = list(contradicoes_result.scalars())

    contradicoes: list[Contradicao] = []
    for acao in acoes_contradicao:
        # Busca última avaliação com justificativa
        aval_stmt = (
            select(Avaliacao)
            .where(Avaliacao.acao_id == acao.id)
            .order_by(Avaliacao.data_avaliacao.desc())
            .limit(1)
        )
        aval = (await session.execute(aval_stmt)).scalar_one_or_none()

        # Busca evidência vinculada
        vinc_stmt = select(VinculoEvidencia).where(VinculoEvidencia.acao_id == acao.id).limit(1)
        vinc = (await session.execute(vinc_stmt)).scalar_one_or_none()

        evidencia_texto = redact_pii(aval.justificativa if aval else "Sem justificativa registrada")
        fonte = ""
        if vinc:
            ev_stmt = select(Evidencia).where(Evidencia.id == vinc.evidencia_id)
            ev = (await session.execute(ev_stmt)).scalar_one_or_none()
            if ev:
                log_evidence_access(ev.id, "GET /api/v1/analytics/auditoria-independente")
                fonte = redact_pii(ev.trecho[:200]) if ev.trecho else ""

        contradicoes.append(
            Contradicao(
                acao_id=acao.id,
                acao_nome=acao.nome,
                status_mcti=str(acao.status.value) if acao.status else "desconhecido",
                evidencia_contraria=evidencia_texto[:200] if evidencia_texto else "",
                fonte_evidencia=fonte,
            )
        )

    # Total de ações verificadas (com pelo menos 1 avaliação)
    verificadas = await session.scalar(select(func.count(func.distinct(Avaliacao.acao_id)))) or 0

    return AuditoriaResponse(
        contradicoes=contradicoes,
        total_contradoes=len(contradicoes),
        acoes_verificadas=verificadas,
    )


# ---------------------------------------------------------------------------
# Entrega 6: Mapa Institucional
# ---------------------------------------------------------------------------


@router.get("/mapa-institucional", response_model=MapaInstitucionalResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def mapa_institucional(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MapaInstitucionalResponse:
    """Mapa de capacidade institucional: quem faz o quê.

    Demonstra: ex-COO que identifica gargalos organizacionais.
    """
    insts = (await session.execute(select(Instituicao).order_by(Instituicao.sigla))).scalars().all()

    # Agregação única via GROUP BY (sem N+1 por instituição)
    agg_stmt = (
        select(AcaoInstituicao.instituicao_id, Acao.status, func.count(Acao.id))
        .join(Acao, Acao.id == AcaoInstituicao.acao_id)
        .group_by(AcaoInstituicao.instituicao_id, Acao.status)
    )
    agg_rows = (await session.execute(agg_stmt)).all()

    inst_counts: dict[str, dict[str, int]] = {}
    for inst_id, status, qtd in agg_rows:
        status_key = status.value if hasattr(status, "value") else str(status)
        inst_counts.setdefault(inst_id, {})[status_key] = qtd

    metricas: list[InstituicaoMetrica] = []
    for inst in insts:
        counts = inst_counts.get(inst.id, {})
        total = sum(counts.values())
        entregues = counts.get("entregue", 0)
        em_andamento = counts.get("em_andamento", 0)
        parcial = counts.get("parcialmente_entregue", 0)

        metricas.append(
            InstituicaoMetrica(
                sigla=inst.sigla or "",
                nome=inst.nome or "",
                total_acoes=total,
                entregues=entregues,
                em_andamento=em_andamento,
                parcialmente_entregue=parcial,
                percentual_execucao=round(entregues / total * 100, 1) if total else 0,
            )
        )

    # Risco de concentração
    total_acoes = sum(m.total_acoes for m in metricas)
    max_acoes = max((m.total_acoes for m in metricas), default=0)
    max_inst = max(metricas, key=lambda m: m.total_acoes, default=None)

    if max_inst and total_acoes > 0:
        pct_max = max_acoes / total_acoes * 100
        if pct_max > 40:
            risco = (
                f"ALTO: {max_inst.sigla} concentra {pct_max:.0f}% das ações "
                f"({max_acoes}/{total_acoes}). Risco de gargalo institucional."
            )
        elif pct_max > 25:
            risco = (
                f"MEDIO: {max_inst.sigla} concentra {pct_max:.0f}% das ações. "
                f"Distribuição razoável mas monitorar."
            )
        else:
            risco = f"BAIXO: distribuição equilibrada entre {len(metricas)} instituições."
    else:
        risco = "Sem dados suficientes para avaliar risco."

    return MapaInstitucionalResponse(
        instituicoes=metricas,
        total_instituicoes=len(metricas),
        risco_concentracao=risco,
    )


# ---------------------------------------------------------------------------
# Entrega 7: Relatório de Lacunas
# ---------------------------------------------------------------------------


@router.get("/lacunas", response_model=LacunasResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def relatorio_lacunas(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LacunasResponse:
    """Relatório de lacunas: ações com prazo vencido e sem entrega.

    Demonstra: analista de políticas públicas que identifica o que falta.
    """
    today = date.today()

    # Ações com prazo vencido e status não finalizado
    lacunas_stmt = (
        select(Acao)
        .where(
            Acao.prazo.isnot(None),
            Acao.prazo < today,
            Acao.status.notin_(
                [
                    StatusAcao.entregue,
                    StatusAcao.descontinuado,
                ]
            ),
        )
        .order_by(Acao.prazo)
    )
    lacunas_result = await session.execute(lacunas_stmt)
    acoes_lacuna = list(lacunas_result.scalars())

    # Recursos previstos agregados em uma única consulta (sem N+1 por ação)
    recurso_map: dict[str, float] = {}
    if acoes_lacuna:
        recurso_stmt = (
            select(Recurso.acao_id, func.coalesce(func.sum(Recurso.valor_previsto), 0))
            .where(Recurso.acao_id.in_([a.id for a in acoes_lacuna]))
            .group_by(Recurso.acao_id)
        )
        recurso_rows = (await session.execute(recurso_stmt)).all()
        recurso_map = {acao_id: float(val) for acao_id, val in recurso_rows}

    lacunas: list[Lacuna] = []
    valor_total = 0.0

    for acao in acoes_lacuna:
        recurso = recurso_map.get(acao.id, 0.0)
        valor_total += recurso

        dias = (today - acao.prazo).days if acao.prazo else 0

        lacunas.append(
            Lacuna(
                acao_id=acao.id,
                acao_nome=acao.nome,
                prazo=acao.prazo.isoformat() if acao.prazo else None,
                status=str(acao.status.value) if acao.status else "desconhecido",
                recurso_previsto=recurso,
                dias_atraso=dias,
            )
        )

    return LacunasResponse(
        lacunas=lacunas,
        total_lacunas=len(lacunas),
        valor_em_risco=valor_total,
    )
