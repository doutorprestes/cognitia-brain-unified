"""
IA Brasil — Modelos ORM (SQLAlchemy async).

Modelo de domínio conforme CONTEXT.md §4:
  Plano → Eixo → Programa → Ação → Meta → Indicador
                                   ↳ Recurso
                                   ↳ Instituição (via link)
  Evidência → Vinculação → Ação/Meta
  Avaliação → Ação
  Evento → Ação
  Fonte → Evidência

Camada isolada de `src.core.settings` e `src.core.schemas` para eliminar o
acoplamento reverso do antigo `src.core.db` (issue #1081): modelos não
dependem de Settings nem de DTOs Pydantic.
"""

from __future__ import annotations

import typing
from datetime import date, datetime  # noqa: TC003
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def JSONColumn(default: dict[str, Any] | None = None) -> Any:
    """Retorna JSONB se PostgreSQL, JSON se SQLite (testes)."""
    import os

    db_url = os.getenv("DATABASE_URL", "")
    if "sqlite" in db_url.lower() or "sqlite" in (os.getenv("TEST_DATABASE_URL") or "sqlite"):
        return mapped_column(JSON, default=default or dict, nullable=False)
    return mapped_column(JSONB, default=default or dict, nullable=False)


def JSONListColumn(default: list[Any] | None = None) -> Any:
    """Retorna coluna JSONB/JSON com default de lista (ex.: evidencias_usadas)."""
    import os

    db_url = os.getenv("DATABASE_URL", "")
    if "sqlite" in db_url.lower() or "sqlite" in (os.getenv("TEST_DATABASE_URL") or "sqlite"):
        return mapped_column(JSON, default=default or list, nullable=False)
    return mapped_column(JSONB, default=default or list, nullable=False)


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums de domínio
# ---------------------------------------------------------------------------


class StatusAcao(StrEnum):
    nao_iniciado = "nao_iniciado"
    sinalizado = "sinalizado"
    em_andamento = "em_andamento"
    parcialmente_entregue = "parcialmente_entregue"
    entregue = "entregue"
    inconclusivo = "inconclusivo"
    contraditoriro = "contraditorio"
    descontinuado = "descontinuado"


class TipoMeta(StrEnum):
    quantitativa = "quantitativa"
    qualitativa = "qualitativa"


class TipoIndicador(StrEnum):
    resultado = "resultado"
    produto = "produto"
    impacto = "impacto"


class TipoEvento(StrEnum):
    """Tipos de evento conforme valores reais do banco de dados.

    Os valores foram atualizados para refletir os tipos reais usados no backend:
    - STATUS_ALTERADO: Mudança de status de ação
    - EVIDENCIA_VINCULADA: Vínculo de evidência criado
    - AVALIACAO_REGISTRADA: Avaliação registrada
    - NOTA_EDITORIAL: Notas editoriais e outros eventos"""

    STATUS_ALTERADO = "STATUS_ALTERADO"
    EVIDENCIA_VINCULADA = "EVIDENCIA_VINCULADA"
    AVALIACAO_REGISTRADA = "AVALIACAO_REGISTRADA"
    NOTA_EDITORIAL = "NOTA_EDITORIAL"


class TipoEvidencia(StrEnum):
    ato_oficial = "ato_oficial"
    ato_normativo = "ato_normativo"
    edital = "edital"
    relatorio = "relatorio"
    noticia = "noticia"
    pagina_institucional = "pagina_institucional"
    outro = "outro"


class TipoClaim(StrEnum):
    """Tipo de claim que a evidência sustenta (promessa ≠ execução).

    Separa semanticamente o que foi prometido/anunciado do que foi de fato
    executado/entregue, permitindo responder "prometeu X, contratou Y,
    entregou Z?" (research M1/M4). Distinto de ``TipoEvidencia``, que classifica
    o tipo documental da fonte.
    """

    promessa = "promessa"
    anuncio = "anuncio"
    execucao = "execucao"
    entrega = "entrega"
    resultado = "resultado"
    observacao = "observacao"


class EstadoVinculo(StrEnum):
    """Estado de revisão de um vínculo de evidência (ADR-006)."""

    proposto = "proposto"
    aprovado = "aprovado"
    rejeitado = "rejeitado"


# ---------------------------------------------------------------------------
# Modelos ORM
# ---------------------------------------------------------------------------


class Plano(Base):
    """Versão do PBIA monitorada."""

    __tablename__ = "planos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    versao: Mapped[str] = mapped_column(String(32), nullable=False)
    ano_referencia: Mapped[int] = mapped_column(nullable=False)
    fonte_url: Mapped[str | None] = mapped_column(Text)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date)
    vigencia_fim: Mapped[date | None] = mapped_column(Date)

    eixos: Mapped[list[Eixo]] = relationship(back_populates="plano")

    __table_args__ = (UniqueConstraint("nome", "versao", name="uq_plano_nome_versao"),)


class Eixo(Base):
    """Um dos eixos estruturantes do PBIA."""

    __tablename__ = "eixos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plano_id: Mapped[str] = mapped_column(ForeignKey("planos.id"), nullable=False)
    numero: Mapped[int] = mapped_column(nullable=False)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)

    plano: Mapped[Plano] = relationship(back_populates="eixos")
    programas: Mapped[list[Programa]] = relationship(back_populates="eixo")

    __table_args__ = (UniqueConstraint("plano_id", "numero"),)


class Programa(Base):
    """Conjunto de ações dentro de um eixo."""

    __table_args__ = (UniqueConstraint("eixo_id", "nome", name="uq_programa_eixo_nome"),)

    __tablename__ = "programas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    eixo_id: Mapped[str] = mapped_column(ForeignKey("eixos.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    codigo: Mapped[str | None] = mapped_column(String(32))  # código no doc. original (drift #1081)
    descricao: Mapped[str | None] = mapped_column(Text)

    eixo: Mapped[Eixo] = relationship(back_populates="programas")
    acoes: Mapped[list[Acao]] = relationship(back_populates="programa")


class Acao(Base):
    """Unidade principal de acompanhamento do PBIA."""

    __tablename__ = "acoes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    programa_id: Mapped[str] = mapped_column(ForeignKey("programas.id"), nullable=False)
    codigo_oficial: Mapped[str | None] = mapped_column(String(32))  # código no doc. original
    nome: Mapped[str] = mapped_column(String(512), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[StatusAcao] = mapped_column(
        SAEnum(StatusAcao, name="status_acao"), default=StatusAcao.nao_iniciado, nullable=False
    )
    status_atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)
    tipo_estruturante: Mapped[str | None] = mapped_column(String(64))
    area_tematica: Mapped[str | None] = mapped_column(String(128))
    desafio: Mapped[str | None] = mapped_column(Text)
    prazo: Mapped[date | None] = mapped_column(Date)
    trecho_original: Mapped[str | None] = mapped_column(Text)  # trecho literal do PBIA
    pagina_doc: Mapped[int | None] = mapped_column()  # página no PDF
    extra: Mapped[dict[str, typing.Any]] = JSONColumn()

    programa: Mapped[Programa] = relationship(back_populates="acoes")
    metas: Mapped[list[Meta]] = relationship(back_populates="acao")
    recursos: Mapped[list[Recurso]] = relationship(back_populates="acao")
    eventos: Mapped[list[Evento]] = relationship(back_populates="acao")
    avaliacoes: Mapped[list[Avaliacao]] = relationship(back_populates="acao")
    vinculos: Mapped[list[VinculoEvidencia]] = relationship(back_populates="acao")
    instituicoes: Mapped[list[AcaoInstituicao]] = relationship(back_populates="acao")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="acao")
    execucao_financeira: Mapped[list[ExecucaoFinanceira]] = relationship(back_populates="acao")

    __table_args__ = (
        UniqueConstraint("programa_id", "codigo_oficial", name="uq_acao_programa_codigo"),
        Index("idx_acoes_programa", "programa_id"),
        Index("idx_acoes_status", "status"),
    )


class Meta(Base):
    """Objetivo mensurável com prazo vinculado a uma Ação."""

    __tablename__ = "metas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    acao_id: Mapped[str] = mapped_column(ForeignKey("acoes.id"), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoMeta] = mapped_column(SAEnum(TipoMeta, name="tipo_meta"), nullable=False)
    alvo_valor: Mapped[float | None] = mapped_column(Numeric(18, 4))
    alvo_unidade: Mapped[str | None] = mapped_column(String(64))
    prazo: Mapped[date | None] = mapped_column(Date)

    acao: Mapped[Acao] = relationship(back_populates="metas")
    indicadores: Mapped[list[Indicador]] = relationship(back_populates="meta")
    vinculos: Mapped[list[VinculoEvidencia]] = relationship(back_populates="meta")

    __table_args__ = (
        UniqueConstraint("acao_id", "descricao", name="uq_meta_acao_descricao"),
        Index("idx_metas_acao", "acao_id"),
    )


class Indicador(Base):
    """Métrica de resultado, produto ou impacto."""

    __tablename__ = "indicadores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    meta_id: Mapped[str] = mapped_column(ForeignKey("metas.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    tipo: Mapped[TipoIndicador] = mapped_column(
        SAEnum(TipoIndicador, name="tipo_indicador"),
        nullable=False,
    )
    linha_base: Mapped[float | None] = mapped_column(Numeric(18, 4))
    meta_valor: Mapped[float | None] = mapped_column(Numeric(18, 4))
    unidade: Mapped[str | None] = mapped_column(String(64))
    fonte_calculo: Mapped[str | None] = mapped_column(Text)

    meta: Mapped[Meta] = relationship(back_populates="indicadores")
    resultados: Mapped[list[IndicadorResultado]] = relationship(back_populates="indicador")

    __table_args__ = (UniqueConstraint("meta_id", "nome", name="uq_indicador_meta_nome"),)


class IndicadorResultado(Base):
    """Resultado mensurado de um indicador do PBIA.

    Registra o valor atingido em uma data de apuração, com proveniência.
    """

    __tablename__ = "indicador_resultado"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    indicador_id: Mapped[str] = mapped_column(ForeignKey("indicadores.id"), nullable=False)
    valor_atingido: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    data_apuracao: Mapped[date] = mapped_column(Date, nullable=False)
    fonte_url: Mapped[str | None] = mapped_column(String(512))
    fonte_tipo: Mapped[str] = mapped_column(String(32), nullable=False, default="relatorio")
    criado_em: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    indicador: Mapped[Indicador] = relationship(back_populates="resultados")

    __table_args__ = (
        UniqueConstraint(
            "indicador_id",
            "data_apuracao",
            name="uq_indicador_resultado_data",
        ),
    )


class Recurso(Base):
    """Valor orçamentário, fonte e natureza do financiamento."""

    __tablename__ = "recursos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    acao_id: Mapped[str] = mapped_column(ForeignKey("acoes.id"), nullable=False)
    valor_previsto: Mapped[float | None] = mapped_column(Numeric(18, 2))
    valor_executado: Mapped[float | None] = mapped_column(Numeric(18, 2))
    fonte: Mapped[str | None] = mapped_column(String(256))
    natureza: Mapped[str | None] = mapped_column(String(128))
    ano_referencia: Mapped[int | None] = mapped_column()

    acao: Mapped[Acao] = relationship(back_populates="recursos")

    __table_args__ = (
        UniqueConstraint("acao_id", "fonte", "natureza", name="uq_recurso_acao_fonte_natureza"),
    )


class Instituicao(Base):
    """Orgão responsável, apoiador ou executor."""

    __tablename__ = "instituicoes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sigla: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(64))  # ex: ministerio, autarquia, empresa
    url_oficial: Mapped[str | None] = mapped_column(Text)

    acoes: Mapped[list[AcaoInstituicao]] = relationship(back_populates="instituicao")


class AcaoInstituicao(Base):
    """Relacionamento N:M entre Ação e Instituição com papel."""

    __tablename__ = "acoes_instituicoes"

    acao_id: Mapped[str] = mapped_column(ForeignKey("acoes.id"), primary_key=True)
    instituicao_id: Mapped[str] = mapped_column(ForeignKey("instituicoes.id"), primary_key=True)
    papel: Mapped[str] = mapped_column(String(64), nullable=False)  # responsavel|apoiador|executor

    acao: Mapped[Acao] = relationship(back_populates="instituicoes")
    instituicao: Mapped[Instituicao] = relationship(back_populates="acoes")


class Fonte(Base):
    """URL, documento, ato oficial ou página de origem de uma evidência."""

    __tablename__ = "fontes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    titulo: Mapped[str | None] = mapped_column(String(512))
    instituicao_emissora: Mapped[str | None] = mapped_column(String(256))
    tipo_documental: Mapped[str | None] = mapped_column(String(128))
    data_publicacao: Mapped[date | None] = mapped_column(Date)
    data_coleta: Mapped[date] = mapped_column(Date, nullable=False)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64))  # sha256 do arquivo coletado

    evidencias: Mapped[list[Evidencia]] = relationship(back_populates="fonte")


class Evidencia(Base):
    """Documento ou registro público que comprova ou refuta execução."""

    __tablename__ = "evidencias"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fonte_id: Mapped[str] = mapped_column(ForeignKey("fontes.id"), nullable=False)
    tipo: Mapped[TipoEvidencia] = mapped_column(
        SAEnum(TipoEvidencia, name="tipo_evidencia"),
        nullable=False,
    )
    tipo_claim: Mapped[TipoClaim | None] = mapped_column(SAEnum(TipoClaim, name="tipo_claim"))
    trecho: Mapped[str | None] = mapped_column(Text)  # trecho literal que sustenta a conclusão
    resumo: Mapped[str | None] = mapped_column(Text)
    data_evidencia: Mapped[date | None] = mapped_column(Date)
    confianca: Mapped[float | None] = mapped_column(Numeric(4, 3))  # 0.0-1.0

    fonte: Mapped[Fonte] = relationship(back_populates="evidencias")
    vinculos: Mapped[list[VinculoEvidencia]] = relationship(back_populates="evidencia")

    __table_args__ = (
        UniqueConstraint("fonte_id", "tipo", "trecho", name="uq_evidencia_fonte_tipo_trecho"),
        Index("idx_evidencias_fonte", "fonte_id"),
    )


class VinculoEvidencia(Base):
    """Associação entre Evidência e Ação/Meta (ADR-006: vinculação explícita e rastreavel)."""

    __tablename__ = "vinculos_evidencia"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evidencia_id: Mapped[str] = mapped_column(ForeignKey("evidencias.id"), nullable=False)
    acao_id: Mapped[str] = mapped_column(ForeignKey("acoes.id"), nullable=False)
    meta_id: Mapped[str | None] = mapped_column(ForeignKey("metas.id"))
    justificativa: Mapped[str | None] = mapped_column(Text)
    criado_por: Mapped[str | None] = mapped_column(String(64))  # perfil Hermes ou usuario
    aprovado_por: Mapped[str | None] = mapped_column(String(64))
    estado: Mapped[EstadoVinculo] = mapped_column(
        SAEnum(EstadoVinculo, name="estado_vinculo"),
        default=EstadoVinculo.proposto,
        nullable=False,
    )
    revisor: Mapped[str | None] = mapped_column(String(64))  # quem revisou o vínculo
    metodo: Mapped[str | None] = mapped_column(String(64))  # ex: manual, regra, llm
    score: Mapped[float | None] = mapped_column(Numeric(4, 3))  # score de revisão 0.0-1.0
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime)

    evidencia: Mapped[Evidencia] = relationship(back_populates="vinculos")
    acao: Mapped[Acao] = relationship(back_populates="vinculos")
    meta: Mapped[Meta | None] = relationship(back_populates="vinculos")

    __table_args__ = (
        UniqueConstraint("evidencia_id", "acao_id", name="uq_vinculo_evidencia_acao"),
        Index("idx_vinculos_acao", "acao_id"),
        Index("idx_vinculos_evidencia", "evidencia_id"),
    )


class Avaliacao(Base):
    """Leitura analítica do status com justificativa rastreável."""

    __tablename__ = "avaliacoes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    acao_id: Mapped[str] = mapped_column(ForeignKey("acoes.id"), nullable=False)
    status_avaliado: Mapped[StatusAcao] = mapped_column(
        SAEnum(StatusAcao, name="status_acao"), nullable=False
    )
    justificativa: Mapped[str] = mapped_column(Text, nullable=False)
    avaliado_por: Mapped[str | None] = mapped_column(String(64))
    data_avaliacao: Mapped[date] = mapped_column(Date, nullable=False)
    versao: Mapped[int] = mapped_column(default=1, nullable=False)
    # Lista formal de evidências usadas: [{"evidencia_id": "...", "trecho": "..."}]
    evidencias_usadas: Mapped[list[dict[str, Any]]] = JSONListColumn()

    acao: Mapped[Acao] = relationship(back_populates="avaliacoes")

    __table_args__ = (
        UniqueConstraint("acao_id", "versao", name="uq_avaliacao_acao_versao"),
        Index("idx_avaliacoes_acao", "acao_id"),
    )


class Evento(Base):
    """Marco temporal: anúncio, lançamento, contratação, entrega, revisão, suspensão.

    Conforme issue #17: eventos são imutáveis e referenciam entidades geradoras.
    """

    __tablename__ = "eventos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    acao_id: Mapped[str | None] = mapped_column(ForeignKey("acoes.id"), nullable=True)
    tipo: Mapped[TipoEvento] = mapped_column(SAEnum(TipoEvento, name="tipo_evento"), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    data_evento: Mapped[date] = mapped_column(Date, nullable=False)
    referencia_id: Mapped[str | None] = mapped_column(String(64))
    referencia_tipo: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[date] = mapped_column(Date, nullable=False)
    fonte_url: Mapped[str | None] = mapped_column(Text)

    acao: Mapped[Acao | None] = relationship(back_populates="eventos")

    __table_args__ = (
        UniqueConstraint(
            "acao_id",
            "tipo",
            "data_evento",
            name="uq_evento_acao_tipo_data",
        ),
        Index("idx_eventos_acao", "acao_id"),
    )


class IngestionRun(Base):
    """Registro de uma execução de re-ingestão periódica.

    Rastreia cada execução do pipeline de re-ingestão, incluindo
    timestamp, fontes coletadas, dados alterados e hash do estado anterior.
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(64), nullable=False)  # ex: 'dou', 'pbia'
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running, success, error
    previous_hash: Mapped[str | None] = mapped_column(String(64))  # hash do estado anterior
    current_hash: Mapped[str | None] = mapped_column(String(64))  # hash do estado novo
    items_fetched: Mapped[int] = mapped_column(default=0, nullable=False)
    items_new: Mapped[int] = mapped_column(default=0, nullable=False)
    items_updated: Mapped[int] = mapped_column(default=0, nullable=False)
    items_unchanged: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, typing.Any]] = JSONColumn()

    __table_args__ = (
        Index("idx_ingestion_runs_source", "source"),
        Index("idx_ingestion_runs_started", "started_at"),
    )


class ExecucaoFinanceira(Base):
    """Execução financeira (CGU/Portal da Transparência) vinculada a ações.

    Dados coletados da API de despesas por função-programática do
    Portal da Transparência (CGU).
    """

    __tablename__ = "execucao_financeira"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    acao_id: Mapped[str | None] = mapped_column(
        ForeignKey("acoes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ano: Mapped[int] = mapped_column(nullable=False, index=True)
    codigo_funcao: Mapped[str] = mapped_column(String(4), nullable=False)
    funcao: Mapped[str] = mapped_column(String(128), nullable=False)
    codigo_subfuncao: Mapped[str] = mapped_column(String(4), nullable=False)
    subfuncao: Mapped[str] = mapped_column(String(128), nullable=False)
    codigo_programa: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    programa: Mapped[str] = mapped_column(String(256), nullable=False)
    codigo_acao_siafi: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    nome_acao: Mapped[str] = mapped_column(String(512), nullable=False)
    valor_empenhado: Mapped[float | None] = mapped_column(Numeric(18, 2))
    valor_liquidado: Mapped[float | None] = mapped_column(Numeric(18, 2))
    valor_pago: Mapped[float | None] = mapped_column(Numeric(18, 2))
    # Dimensões de execução financeira de primeira classe (issue #1095):
    # restos a pagar (inscritos) e dotações (LOA inicial vs. atualizada).
    restos_a_pagar: Mapped[float | None] = mapped_column(Numeric(18, 2))
    dotacao_inicial: Mapped[float | None] = mapped_column(Numeric(18, 2))
    dotacao_atual: Mapped[float | None] = mapped_column(Numeric(18, 2))
    # Classificação orçamentária (além de função/subfunção já existentes):
    # programa de trabalho (PTRES), unidade orçamentária, fonte de recurso
    # e natureza da despesa (item de despesa).
    programa_trabalho: Mapped[str | None] = mapped_column(String(128))
    uo: Mapped[str | None] = mapped_column(String(32))
    fonte_recurso: Mapped[str | None] = mapped_column(String(64))
    natureza_despesa: Mapped[str | None] = mapped_column(String(64))
    fonte_coleta: Mapped[str] = mapped_column(String(32), default="CGU/Portal da Transparência")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    acao: Mapped[Acao | None] = relationship(back_populates="execucao_financeira")

    __table_args__ = (
        Index("ix_exec_fin_ano_prog_acao", "ano", "codigo_programa", "codigo_acao_siafi"),
        # Chave natural: um registro por exercício/programa/ação SIAFI.
        # Garante idempotência da ingestão mesmo sob concorrência.
        UniqueConstraint(
            "ano",
            "codigo_programa",
            "codigo_acao_siafi",
            name="uq_exec_fin_ano_prog_acao",
        ),
    )


class MapeamentoSiafiPbia(Base):
    """Mapeamento provisório SIAFI → PBIA (código oficial de ação).

    Corresponde à tabela `mapeamento_siafi_pbia`, criada via migration
    Alembic (antes era criada manualmente pelo CLI `mapear_siafi_pbia`).
    """

    __tablename__ = "mapeamento_siafi_pbia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_acao_siafi: Mapped[str] = mapped_column(String(8), nullable=False)
    acao_pbia_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo_mapeamento: Mapped[str] = mapped_column(String(32), nullable=False, default="automatico")
    confianca: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    observacao: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    # Versionamento (issue #1095): a versão vigente do mapeamento tem
    # ativo=True; atualizações desativam a versão anterior (histórico
    # preservado) e `data_alteracao` registra quando a versão mudou.
    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    data_alteracao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "codigo_acao_siafi",
            "acao_pbia_id",
            name="uq_mapeamento_siafi_pbia",
        ),
        Index("idx_mapeamento_siafi", "codigo_acao_siafi"),
        Index("idx_mapeamento_pbia", "acao_pbia_id"),
    )


class AuditLog(Base):
    """Registro imutável de mudanças de status de ações.

    Conforme CONTEXT.md §8: "o histórico de avaliações é imutável".
    Cada mudança de status cria um novo registro, nunca atualiza ou exclui.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    acao_id: Mapped[str] = mapped_column(ForeignKey("acoes.id"), nullable=False)
    status_anterior: Mapped[StatusAcao | None] = mapped_column(
        SAEnum(StatusAcao, name="status_acao")
    )
    status_novo: Mapped[StatusAcao] = mapped_column(
        SAEnum(StatusAcao, name="status_acao"), nullable=False
    )
    justificativa: Mapped[str] = mapped_column(Text, nullable=False)
    criado_por: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # autor automático ou manual
    data_criacao: Mapped[date] = mapped_column(Date, nullable=False)
    extra_data: Mapped[dict[str, typing.Any]] = JSONColumn()

    acao: Mapped[Acao] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_logs_acao", "acao_id"),
        Index("idx_audit_logs_data", "data_criacao"),
    )
