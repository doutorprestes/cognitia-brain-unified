"""IA Brasil — PBIA Parser Schemas.

Schemas Pydantic para validação da ingestão do PBIA.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    """Referência à fonte no documento PBIA."""

    page: int | None = Field(default=None, ge=1, description="Número da página no documento")
    section: str | None = Field(default=None, description="Seção ou capítulo de origem")
    paragraph: int | None = Field(default=None, ge=1, description="Número do parágrafo")
    text_snippet: str | None = Field(default=None, description="Trecho do texto de origem")

    def __repr__(self) -> str:
        parts = []
        if self.page:
            parts.append(f"p.{self.page}")
        if self.section:
            parts.append(self.section)
        if self.paragraph:
            parts.append(f"§{self.paragraph}")
        return f"SourceReference({' | '.join(parts)})" if parts else "SourceReference()"


class EntityCounts(BaseModel):
    """Contador de entidades criadas/atualizadas."""

    created: int = Field(default=0, ge=0, description="N. registros criados")
    updated: int = Field(default=0, ge=0, description="N. registros atualizados")
    skipped: int = Field(default=0, ge=0, description="N. registros pulados")
    errors: int = Field(default=0, ge=0, description="N. erros durante ingestão")

    @property
    def total(self) -> int:
        """Total de registros processados."""
        return self.created + self.updated + self.skipped


class IngestionReport(BaseModel):
    """Relatório completo da ingestão do PBIA."""

    plano: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Plano")
    eixo: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Eixo")
    programa: EntityCounts = Field(
        default_factory=EntityCounts, description="Contagem para Programa"
    )
    acao: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Ação")
    meta: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Meta")
    indicador: EntityCounts = Field(
        default_factory=EntityCounts, description="Contagem para Indicador"
    )
    recurso: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Recurso")
    instituicao: EntityCounts = Field(
        default_factory=EntityCounts, description="Contagem para Instituição"
    )
    fonte: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Fonte")
    evidencia: EntityCounts = Field(
        default_factory=EntityCounts, description="Contagem para Evidência"
    )
    evento: EntityCounts = Field(default_factory=EntityCounts, description="Contagem para Evento")
    vinculos: EntityCounts = Field(
        default_factory=EntityCounts, description="Contagem para Vínculos"
    )
    avaliacao: EntityCounts = Field(
        default_factory=EntityCounts, description="Contagem para Avaliação"
    )
    source_document: str = Field(description="Caminho ou URL do documento de origem")
    ingested_at: date = Field(default_factory=date.today, description="Data da ingestão")
    errors: list[str] = Field(default_factory=list, description="Lista de erros durante a ingestão")

    @property
    def total_created(self) -> int:
        """Total de registros criados em todas as entidades."""
        return (
            self.plano.created
            + self.eixo.created
            + self.programa.created
            + self.acao.created
            + self.meta.created
            + self.indicador.created
            + self.recurso.created
            + self.instituicao.created
            + self.fonte.created
            + self.evidencia.created
            + self.evento.created
            + self.vinculos.created
            + self.avaliacao.created
        )

    @property
    def total_updated(self) -> int:
        """Total de registros atualizados em todas as entidades."""
        return (
            self.plano.updated
            + self.eixo.updated
            + self.programa.updated
            + self.acao.updated
            + self.meta.updated
            + self.indicador.updated
            + self.recurso.updated
            + self.instituicao.updated
            + self.fonte.updated
            + self.evidencia.updated
            + self.evento.updated
            + self.vinculos.updated
            + self.avaliacao.updated
            + self.evidencia.updated
            + self.evento.updated
        )

    @property
    def success(self) -> bool:
        """Indica se a ingestão foi bem-sucedida (sem erros)."""
        return len(self.errors) == 0

    def summary(self) -> str:
        """Resumo do relatório em formato legível."""
        lines = [
            "=== Relatório de Ingestão PBIA ===",
            f"Documento: {self.source_document}",
            f"Data: {self.ingested_at.isoformat()}",
            "",
            "Entidade          Criados  Atual.  Total",
            "------           -------  ------  -----",
        ]
        # Adicionar contagens para cada entidade
        entities = [
            ("Plano", self.plano),
            ("Eixo", self.eixo),
            ("Programa", self.programa),
            ("Ação", self.acao),
            ("Meta", self.meta),
            ("Indicador", self.indicador),
            ("Recurso", self.recurso),
            ("Instituição", self.instituicao),
            ("Fonte", self.fonte),
            ("Evidência", self.evidencia),
            ("Evento", self.evento),
            ("Vínculos", self.vinculos),
            ("Avaliação", self.avaliacao),
        ]
        for name, counts in entities:
            lines.append(f"  {name:<14} {counts.created:>7} {counts.updated:>7} {counts.total:>7}")
        lines.append("")
        lines.append(f"Total Criados: {self.total_created}")
        lines.append(f"Total Atualizados: {self.total_updated}")
        if self.errors:
            lines.append("")
            lines.append("Erros:")
            for error in self.errors:
                lines.append(f"  - {error}")
        lines.append("")
        lines.append(f"Status: {'SUCCESS' if self.success else 'FAILED'}")
        return "\n".join(lines)


class ParserError(Exception):
    """Erro durante o parsing do documento PBIA."""

    def __init__(self, message: str, source_ref: SourceReference | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.source_ref = source_ref

    def __repr__(self) -> str:
        ref = f" at {self.source_ref}" if self.source_ref else ""
        return f"ParserError({self.message!r}{ref})"
