"""Módulo de matching textual para vinculação automática — IA Brasil.

Combina TF-IDF + cosine similarity, fuzzy matching e keyword matching
para encontrar pares evidência-ação relevantes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from src.modules.linking.embedder import PBIA_KEYWORDS, Embedder, _tokenize

# ── Termos-chave para keyword matching ──────────────────────────────────

_ACAO_KEYWORDS: list[str] = [
    "infraestrutura",
    "plataforma",
    "laboratório",
    "centro",
    "programa",
    "fundo",
    "edital",
    "chamada",
    "financiamento",
    "capacitação",
    "formação",
    "pesquisa",
    "desenvolvimento",
    "inovação",
    "startup",
    "ecossistema",
    "dados",
    "governo",
    "digital",
    "transformação",
]


@dataclass
class MatchResult:
    """Resultado de um match entre evidência e ação."""

    evidencia_id: str
    acao_id: str
    tfidf_score: float = 0.0
    fuzzy_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0
    matching_keywords: list[str] = field(default_factory=list)


class TextMatcher:
    """Matcher que combina múltiplas estratégias de similaridade textual."""

    def __init__(
        self,
        weight_tfidf: float = 0.5,
        weight_fuzzy: float = 0.3,
        weight_keyword: float = 0.2,
    ) -> None:
        self._embedder = Embedder()
        self._weight_tfidf = weight_tfidf
        self._weight_fuzzy = weight_fuzzy
        self._weight_keyword = weight_keyword
        self._acao_texts: dict[str, str] = {}
        self._acao_names: dict[str, str] = {}

    def fit_acoes(self, acoes: list[dict[str, str | None]]) -> None:
        """Ajusta o matcher com textos das ações.

        Args:
            acoes: Lista de dicts com 'id', 'nome', 'descricao', 'trecho_original'.
        """
        texts: list[str] = []
        ids: list[str] = []

        for acao in acoes:
            acao_id = str(acao.get("id", ""))
            nome = str(acao.get("nome") or "")
            desc = str(acao.get("descricao") or "")
            trecho = str(acao.get("trecho_original") or "")

            combined = f"{nome} {desc} {trecho}".strip()
            if combined and acao_id:
                self._acao_texts[acao_id] = combined
                self._acao_names[acao_id] = nome
                texts.append(combined)
                ids.append(acao_id)

        if texts:
            self._embedder.fit(texts, ids)
            logger.info(f"Matcher ajustado com {len(ids)} ações")

    def _fuzzy_score(self, text1: str, text2: str) -> float:
        """Calcula score fuzzy entre dois textos usando rapidfuzz."""
        try:
            from rapidfuzz import fuzz

            return float(fuzz.token_sort_ratio(text1.lower(), text2.lower())) / 100.0
        except ImportError:
            logger.warning("rapidfuzz não disponível, usando difflib")
            import difflib

            return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def _keyword_score(self, text1: str, text2: str) -> tuple[float, list[str]]:
        """Calcula score baseado em overlap de keywords do PBIA.

        Uma keyword só conta quando está presente em AMBOS os textos
        (interseção dos tokens). Keywords que existem apenas em um dos lados
        (ex.: só na ação) não elevam a relevância, evitando falsos positivos.
        """
        tokens1 = set(_tokenize(text1))
        tokens2 = set(_tokenize(text2))
        shared_tokens = tokens1 & tokens2

        all_keywords = set(PBIA_KEYWORDS + _ACAO_KEYWORDS)
        matches = []
        for kw in all_keywords:
            kw_tokens = set(_tokenize(kw))
            if kw_tokens and kw_tokens.issubset(shared_tokens):
                matches.append(kw)

        if not matches:
            return 0.0, []

        score = min(len(matches) / 3.0, 1.0)
        return score, matches

    def match_evidence(
        self,
        evidencia_id: str,
        texto_evidencia: str,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Encontra as melhores ações para uma evidência.

        Args:
            evidencia_id: ID da evidência.
            texto_evidencia: Texto relevante da evidência (resumo + trecho).
            top_k: Número máximo de resultados.

        Returns:
            Lista dos top_k matches ordenados por combined_score decrescente.
        """
        if not self._acao_texts:
            logger.warning("Matcher não ajustado — chame fit_acoes() primeiro")
            return []

        # TF-IDF similarity
        tfidf_scores = self._embedder.get_corpus_similarity(texto_evidencia)
        tfidf_map = dict(tfidf_scores)

        results: list[MatchResult] = []

        for acao_id, acao_text in self._acao_texts.items():
            # Fuzzy matching
            f_score = self._fuzzy_score(texto_evidencia, acao_text)

            # Keyword matching
            k_score, k_matches = self._keyword_score(texto_evidencia, acao_text)

            # TF-IDF
            t_score = tfidf_map.get(acao_id, 0.0)

            # Combined score
            combined = (
                self._weight_tfidf * t_score
                + self._weight_fuzzy * f_score
                + self._weight_keyword * k_score
            )

            results.append(
                MatchResult(
                    evidencia_id=evidencia_id,
                    acao_id=acao_id,
                    tfidf_score=t_score,
                    fuzzy_score=f_score,
                    keyword_score=k_score,
                    combined_score=combined,
                    matching_keywords=k_matches,
                )
            )

        results.sort(key=lambda r: r.combined_score, reverse=True)
        return results[:top_k]

    def match_all(
        self,
        evidencias: list[dict[str, str | None]],
        top_k: int = 10,
    ) -> dict[str, list[MatchResult]]:
        """Encontra os melhores matches para todas as evidências.

        Args:
            evidencias: Lista de dicts com 'id', 'resumo', 'trecho'.
            top_k: Número máximo de matches por evidência.

        Returns:
            Dict mapeando evidencia_id para lista de matches.
        """
        all_matches: dict[str, list[MatchResult]] = {}

        for ev in evidencias:
            ev_id = str(ev.get("id", ""))
            resumo = str(ev.get("resumo") or "")
            trecho = str(ev.get("trecho") or "")
            texto = f"{resumo} {trecho}".strip()

            if texto and ev_id:
                matches = self.match_evidence(ev_id, texto, top_k)
                all_matches[ev_id] = matches

        return all_matches
