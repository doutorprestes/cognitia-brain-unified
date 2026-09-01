"""Proatividade inteligente do Cognitia Brain.

Concentra:
- Foco de pesquisa: inferido do uso recente, corrigível pelo usuário.
- Detecção de conexões entre um documento novo e o acervo (semâncica + grafo).
- Alerta de conexão com motivo/trecho (outbox para entrega via Telegram).
- Síntese de escrita: gera rascunhos de revisão de literatura por tema.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np

from cognitia_brain.config import Config
from cognitia_brain.db import VectorDB
from cognitia_brain.llm_client import LLMClient

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "o", "as", "os", "e", "de", "da", "do", "das", "dos", "em", "na", "no",
    "nas", "nos", "um", "uma", "uns", "umas", "para", "que", "com", "por", "como",
    "mas", "mais", "muito", "muita", "muitos", "muitas", "se", "é", "são", "ser",
    "tem", "ter", "nosso", "nossa", "the", "and", "of", "to", "in", "is", "for",
    "on", "with",
}


class FocusManager:
    """Gerenciador do foco de pesquisa (inferido + correção explícita)."""

    def __init__(self, config: Config) -> None:
        self.path = config.acervo_dir.parent / ".chromadb" / "foco.json"
        self._dados = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Falha ao ler foco.json: {e}")
        return {"foco": [], "origem": "nao_inferido", "atualizado_em": None, "historico": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._dados, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_foco(self) -> List[str]:
        return list(self._dados.get("foco", []))

    def get_origem(self) -> str:
        return self._dados.get("origem", "nao_inferido")

    def set_foco(self, temas: List[str], origem: str = "nao_inferido") -> List[str]:
        temas = [str(t).strip().lower() for t in temas if str(t).strip()]
        self._dados["foco"] = temas
        self._dados["origem"] = origem
        self._dados["atualizado_em"] = datetime.now().isoformat()
        self._dados.setdefault("historico", []).append(
            {"temas": temas, "origem": origem, "em": datetime.now().isoformat()}
        )
        self._save()
        return self.get_foco()

    def add(self, tema: str) -> None:
        tema_norm = tema.strip().lower()
        if tema_norm and tema_norm not in self.get_foco():
            self._dados["foco"].append(tema_norm)
            self.set_foco(self.get_foco(), origem="manual")

    def remove(self, tema: str) -> None:
        restante = [t for t in self.get_foco() if t != tema.strip().lower()]
        self.set_foco(restante, origem="manual")


class AlertasStore:
    """Histórico + outbox de alertas de conexão (entrega via Telegram)."""

    def __init__(self, config: Config) -> None:
        base = config.acervo_dir.parent / ".chromadb"
        self.hist_path = base / "alertas.json"
        self.outbox_path = base / "alerts_outbox.json"

    def adicionar(self, entrada: dict) -> None:
        entrada.setdefault("em", datetime.now().isoformat())
        self.hist_path.parent.mkdir(parents=True, exist_ok=True)
        hist = []
        if self.hist_path.exists():
            try:
                hist = json.loads(self.hist_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        hist.append(entrada)
        self.hist_path.write_text(
            json.dumps(hist[-50:], ensure_ascii=False, indent=2), encoding="utf-8"
        )

        outbox = []
        if self.outbox_path.exists():
            try:
                outbox = json.loads(self.outbox_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        outbox.append(entrada)
        self.outbox_path.write_text(json.dumps(outbox, ensure_ascii=False, indent=2), encoding="utf-8")

    def historico(self, limites=15) -> List[dict]:
        if not self.hist_path.exists():
            return []
        try:
            return json.loads(self.hist_path.read_text(encoding="utf-8"))[-limites:]
        except Exception:
            return []

    def retirar_outbox(self) -> List[dict]:
        if not self.outbox_path.exists():
            return []
        try:
            dados = json.loads(self.outbox_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        self.outbox_path.write_text(json.dumps([]), encoding="utf-8")
        return dados


def registrar_ingestao(config: Config, doc_id: str) -> None:
    """Registra documento ingerido (usado para inferir foco por recência)."""
    path = config.acervo_dir.parent / ".chromadb" / "ingest_log.json"
    log = []
    if path.exists():
        try:
            log = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    log.append({"doc_id": doc_id, "em": datetime.now().isoformat()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log[-100:], ensure_ascii=False, indent=2), encoding="utf-8")


def _summaries_recentes(config: Config, db: VectorDB, limite: int = 6) -> List[dict]:
    path = config.acervo_dir.parent / ".chromadb" / "ingest_log.json"
    if not path.exists():
        return []
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    resultados = []
    for entry in log[-limite:]:
        doc_id = entry.get("doc_id")
        if not doc_id:
            continue
        try:
            raw = db.collection.get(ids=[f"{doc_id}_summary"])
            if raw and raw.get("documents") and raw["documents"][0]:
                resultados.append({"doc_id": doc_id, "sumario": raw["documents"][0]})
        except Exception:
            continue
    return resultados


def inferir_foco(config: Config, db: VectorDB, llm: LLMClient) -> List[str]:
    """Tenta extrair até 5 temas do último acervo; fallback por frequência de palavras."""
    recentes = _summaries_recentes(config, db)
    if not recentes:
        return []

    contexto = "\n\n".join(
        f"--- Doc {i+1} ---\n{r['sumario'][:1200]}" for i, r in enumerate(recentes)
    )
    prompt = (
        "Você é um curador de pesquisa.\n"
        "Com base nos trechos abaixo, enumere até 5 temas centrais do foco atual de estudo, "
        "um por linha, sem numeração, sem maiores explicações.\n\n"
        f"Trechos:\n{contexto}"
    )
    try:
        resposta = (llm.generate(prompt) or "").strip()
        temas = [
            linha.strip()
            for linha in resposta.splitlines()
            if linha.strip()
        ]
        temas = [re.sub(r"^[-*•#0-9.\s]+", "", t) for t in temas]
        temas = [t for t in temas if t and len(t) > 2][:5]
        if temas:
            return temas
    except Exception as e:
        logger.warning(f"Foco via LLM falhou ({e}); usando fallback por frequência.")

    contador: Counter[str] = Counter()
    for r in recentes:
        palavras = re.findall(r"[a-záéíóúâãêõç]{4,}", r["sumario"].lower())
        contador.update(p for p in palavras if p not in _STOPWORDS)
    return [p for p, _ in contador.most_common(5)]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if not na or not nb:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _ent_textos(db: VectorDB, textos: List[str]) -> List[np.ndarray]:
    encs = db.emb_fn.embed_query(list(textos))
    return [np.asarray(v, dtype=float) for v in encs]


def _titulo_sumario(sumario: dict) -> str:
    texto = sumario.get("sumario", "") if isinstance(sumario, dict) else str(sumario)
    for linha in texto.splitlines()[:2]:
        l = linha.strip()
        if l.startswith("#"):
            return l.lstrip("# ").replace("Fichamento: ", "").strip() or sumario.get("doc_id", "")
    return sumario.get("doc_id", "")


def _entidades_comuns(texto: str, sumario: str, graph) -> List[str]:
    texto_l = texto.lower()
    sumario_l = sumario.lower()
    comum = set()
    try:
        if graph is not None:
            for node in graph.graph.nodes():
                nome = str(node).strip().lower()
                if len(nome) >= 3 and nome in texto_l and nome in sumario_l:
                    comum.add(nome)
    except Exception:
        pass

    if not comum:
        a = {p for p in re.findall(r"[a-záéíóúâêõç]{4,}", texto_l) if p not in _STOPWORDS}
        b = {p for p in re.findall(r"[a-záéíóúâêõç]{4,}", sumario_l) if p not in _STOPWORDS}
        comum = a & b
    return sorted(comum)[:5]


def encontrar_conexoes(
    config: Config,
    db: VectorDB,
    graph,
    doc_id: str,
    texto: str,
    topo: int = 4,
    limiar: float = 0.35,
) -> List[dict]:
    """Acha fichamentos próximos (cosseno) a um novo texto, com entidades comuns."""
    resultados = db.search(texto, n_results=8, where={"is_summary": True})
    if not resultados or not resultados.get("documents") or not resultados["documents"][0]:
        return []

    candidatos = []
    for rid, doc in zip(resultados["ids"][0], resultados["documents"][0]):
        base = rid.removesuffix("_summary")
        if base == doc_id:
            continue
        candidatos.append({"doc_id": base, "sumario": doc})

    if not candidatos:
        return []

    vetor_texto = np.asarray(db.emb_fn.embed_query([texto])[0], dtype=float)
    vetores = _ent_textos(db, [c["sumario"] for c in candidatos])

    conexoes = []
    for c, v in zip(candidatos, vetores):
        score = _cosine(vetor_texto, v)
        if score < limiar:
            continue
        conexoes.append({
            "doc_id": c["doc_id"],
            "titulo": _titulo_sumario(c),
            "score": round(score, 3),
            "trecho": c["sumario"][:220].strip(),
            "entidades": _entidades_comuns(texto, c["sumario"], graph),
            "id_conexao": f"{c['doc_id']}|{doc_id}",
            "texto_novo": texto[:4000],
        })
    conexoes.sort(key=lambda x: x["score"], reverse=True)
    return conexoes[:topo]


def montar_alerta_conexao(doc_id: str, conexoes: List[dict]) -> str:
    if not conexoes:
        return ""
    novo = doc_id.replace("_", " ").replace(".pdf", "").strip()
    linhas = [f"🔗 **Este material conecta com o acervo:** `{novo}`"]
    for c in conexoes:
        ent = ", ".join(c["entidades"]) if c["entidades"] else "termos em comum"
        linhas.append(f"• *{c['titulo']}* — afinidade {c['score']:.2f} · {ent}")
        trecho = c["trecho"][:140].replace("\n", " ")
        linhas.append(f"  _trecho: “{trecho}…”")
    return "\n".join(linhas)


def avaliar_e_registrar_conexoes(
    config: Config,
    db: VectorDB,
    graph,
    doc_id: str,
    texto: str,
    limiar: float = 0.35,
) -> List[dict]:
    """Detecta conexões de um documento recém-ingerido e grava no outbox de alertas."""
    try:
        conexoes = encontrar_conexoes(config, db, graph, doc_id, texto, limiar=limiar)
    except Exception as e:
        logger.warning(f"Falha ao avaliar conexões de {doc_id}: {e}")
        return []
    if not conexoes:
        return []
    AlertasStore(config).adicionar({
        "doc_id": doc_id,
        "conexoes": conexoes,
        "texto_novo": texto[:4000],
    })
    logger.info(f"{doc_id}: {len(conexoes)} conexões registradas no outbox.")
    return conexoes


def gerar_sintese_tema(config: Config, db: VectorDB, llm: LLMClient, tema: str) -> Path:
    """Gera rascunho .md de revisão de literatura em rascunhos/ para o tema."""
    resultados = db.search(tema, n_results=6, where={"is_summary": True})
    fontes = []
    if resultados and resultados.get("documents") and resultados["documents"][0]:
        for rid, doc in zip(resultados["ids"][0], resultados["documents"][0]):
            fontes.append({"doc_id": rid.removesuffix("_summary"), "sumario": doc})
    if not fontes:
        raise ValueError(f"Nenhum fichamento encontrado para o tema '{tema}'.")

    contexto = "\n\n".join(f"[{i+1}] {f['sumario']}" for i, f in enumerate(fontes))
    prompt = (
        "Você é um assistente de escrita acadêmica em português.\n"
        f"Escreva um rascunho de revisão de literatura sobre \"{tema}\" usando APENAS os "
        "fichamento abaixo.\n"
        "Regras:\n"
        "- Estruture em: Introdução, Estado da Arte, Lacunas e Próximos Passos.\n"
        "- Cite as fontes com colchetes [1], [2]... ao usar ideias delas.\n"
        "- Não invente informações além das fontes.\n"
        "No final, adicione a seção 'Fontes' numeradas.\n\n"
        f"Fichamentos:\n{contexto}"
    )
    try:
        rascunho = llm.generate(prompt) or "*(LLM não respondeu.)*"
    except Exception as e:
        logger.error(f"Síntese falhou: {e}")
        raise

    slug = re.sub(r"[^a-z0-9]+", "-", tema.lower()).strip("-") or "sintese"
    destino = config.acervo_dir.parent / "rascunhos" / f"{slug}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fontes_numeradas = [f"[{i+1}] {_titulo_sumario(f)}" for i, f in enumerate(fontes)]
    bloco = (
        f"# Rascunho — Revisão de Literatura: {tema}\n\n"
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')} | base: {len(fontes)} fichamentos_\n\n"
        f"{rascunho}\n\n"
        "---\nFontes:\n"
        "\n".join(fontes_numeradas) + "\n"
    )
    destino.write_text(bloco, encoding="utf-8")
    return destino


def exportar_bibtex(conteudo: str) -> str:
    """Gera um @misc simples a partir do primeiro cabeçalho do arquivo."""
    for linha in conteudo.splitlines():
        l = linha.strip()
        if l.startswith("# "):
            titulo = l.lstrip("# ").replace("Fichamento: ", "")
            chave = re.sub(r"[^a-zA-Z0-9]+", "", titulo)[:20].lower() or "nota"
            return "\n".join([
                f"@misc{{{chave},",
                f"  title = {{{titulo}}},",
                "  note = {Fichamento Cogniti Brain}",
                "}",
            ]) + "\n"
    return "% Sem título; exportação vazia.\n"