"""IA Brasil — Schemas Pydantic para a assistência LLM local (Ollama).

Saídas validadas do LLM. Toda saída carrega a citação da fonte
(``trecho_citado``/``trecho_*`` + ``fonte_url``) e registra a versão de
prompt/modelo usada (rastreabilidade). Nenhum schema publica status: o LLM
apenas propõe candidatos para revisão humana — nunca é autoridade final.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedIndicator(BaseModel):
    """Indicador/métrica extraído de uma fonte, com citação literal."""

    nome: str = Field(..., min_length=3, description="Nome do indicador extraído")
    valor: float | None = Field(None, description="Valor numérico, se houver")
    unidade: str | None = Field(None, description="Unidade de medida (ex.: %, unidades)")
    tipo: str | None = Field(None, description="resultado | produto | impacto")
    trecho_citado: str = Field(
        ...,
        min_length=3,
        description="Trecho LITERAL do texto que sustenta a extração",
    )
    fonte_url: str | None = Field(None, description="URL da fonte de origem")


class ExtractionResult(BaseModel):
    """Resultado da extração assistida de indicadores."""

    indicadores: list[ExtractedIndicator] = Field(default_factory=list)
    fonte_url: str | None = Field(None, description="URL da fonte analisada")
    prompt_version: str = Field(
        default="", description="Versão do prompt (preenchida pelo serviço)"
    )
    model_used: str | None = Field(None, description="Modelo usado (None=fallback local)")


class SummarizationResult(BaseModel):
    """Resumo de uma evidência com citação obrigatória da fonte."""

    resumo: str = Field(..., min_length=10, description="Resumo fiel ao texto-fonte")
    fonte_url: str | None = Field(None, description="URL da fonte")
    trecho_citado: str = Field(..., min_length=3, description="Citação literal do texto-fonte")
    prompt_version: str = Field(
        default="", description="Versão do prompt (preenchida pelo serviço)"
    )
    model_used: str | None = Field(None, description="Modelo usado (None=fallback local)")


class ContradictionJudgment(BaseModel):
    """Julgamento do LLM sobre um par de claims (nunca altera status)."""

    is_contradiction: bool = Field(..., description="Se as claims são incompatíveis")
    razao: str = Field(..., min_length=3, description="Justificativa do julgamento")


class ContradictionCandidate(BaseModel):
    """Candidato a contradição entre duas evidências, com trechos citados.

    É apenas um CANDIDATO para revisão humana: o LLM/heurística propõe,
    nunca publica status nem altera vínculos.
    """

    evidencia_a_id: str = Field(..., description="ID da evidência A")
    evidencia_b_id: str = Field(..., description="ID da evidência B")
    claim_a: str = Field(..., description="Texto de suporte da claim A")
    claim_b: str = Field(..., description="Texto de suporte da claim B")
    trecho_a: str = Field(..., min_length=3, description="Citação literal da evidência A")
    trecho_b: str = Field(..., min_length=3, description="Citação literal da evidência B")
    fonte_url_a: str | None = Field(None, description="URL da fonte A")
    fonte_url_b: str | None = Field(None, description="URL da fonte B")
    razao: str = Field(..., min_length=3, description="Por que as claims parecem incompatíveis")
    prompt_version: str = Field(
        default="", description="Versão do prompt (preenchida pelo serviço)"
    )
    model_used: str | None = Field(None, description="Modelo usado (None=heurística local)")


class ClaimData(BaseModel):
    """Claim simplificada para comparação (aceita dict ou ORM convertido).

    Campo ``tipo_claim`` usa os valores de ``TipoClaim`` (promessa, anuncio,
    execucao, entrega, resultado, observacao).
    """

    id: str
    titulo: str | None = None
    resumo: str | None = None
    trecho: str | None = None
    fonte_url: str | None = None
    tipo_claim: str | None = None

    @property
    def texto(self) -> str:
        """Texto consolidado da claim (resumo + trecho)."""
        return " ".join(filter(None, [self.resumo or "", self.trecho or ""])).strip()
