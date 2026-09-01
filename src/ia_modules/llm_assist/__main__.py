"""CLI da assistência LLM local — IA Brasil.

Uso:
    python -m src.modules.llm_assist --extract <fonte_id|arquivo> [--dry-run]
    python -m src.modules.llm_assist --contradictions [--dry-run] [--limit N]

Modo lote com saída JSON. ``--dry-run`` é o padrão: o módulo nunca persiste
status; a flag fica como garantia explícita de que nada é gravado.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from src.core.db import Evidencia, Fonte, get_session
from src.modules.llm_assist.client import OllamaClient
from src.modules.llm_assist.service import (
    claim_from_evidencia,
    extract_indicators,
    find_contradictions,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.modules.llm_assist",
        description="Assistência LLM local (Ollama) com citação obrigatória.",
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--extract",
        metavar="FONTE",
        help="Extrai indicadores de uma fonte (id/URL no banco ou caminho de arquivo).",
    )
    grupo.add_argument(
        "--contradictions",
        action="store_true",
        help="Busca candidatos a contradição entre evidências (modo lote).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Não persiste nada (padrão: True; o módulo nunca grava status).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limita evidências no modo lote.")
    parser.add_argument("--model", default=None, help="Modelo Ollama (override do padrão).")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point da CLI (retorna código de saída)."""
    args = _parser().parse_args(argv)
    client = OllamaClient(model=args.model) if args.model else None
    if args.extract:
        return asyncio.run(_cmd_extract(args.extract, client))
    return asyncio.run(_cmd_contradictions(client, args.limit, args.dry_run))


async def _cmd_extract(fonte: str, client: OllamaClient | None) -> int:
    """Extrai indicadores de um arquivo local ou de uma fonte do banco."""
    caminho = Path(fonte)
    if caminho.exists():
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        fonte_url = str(caminho)
    else:
        texto, fonte_url = await _texto_da_fonte(fonte)
    result = await extract_indicators(texto, fonte_url=fonte_url, client=client)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2, default=str))
    return 0


async def _texto_da_fonte(fonte: str) -> tuple[str, str]:
    """Concatena trecho/resumo das evidências de uma fonte do banco."""
    async with get_session() as session:
        result = await session.execute(
            select(Fonte)
            .options(selectinload(Fonte.evidencias))
            .where(or_(Fonte.id == fonte, Fonte.url == fonte))
        )
        obj = result.scalars().first()
        if obj is None:
            print(f"Fonte não encontrada: {fonte}", file=sys.stderr)
            raise SystemExit(2)
        partes: list[str] = []
        for ev in obj.evidencias:
            if ev.trecho:
                partes.append(ev.trecho)
            if ev.resumo:
                partes.append(ev.resumo)
        return "\n".join(partes), obj.url


async def _cmd_contradictions(
    client: OllamaClient | None,
    limit: int | None,
    dry_run: bool,
) -> int:
    """Modo lote: candidatos a contradição entre todas as evidências."""
    async with get_session() as session:
        query = select(Evidencia).options(joinedload(Evidencia.fonte))
        if limit is not None:
            query = query.limit(limit)
        evidencias = list((await session.execute(query)).scalars())
    claims = [claim_from_evidencia(ev) for ev in evidencias]
    candidatos = await find_contradictions(claims, client=client)
    print(json.dumps([c.model_dump() for c in candidatos], ensure_ascii=False, indent=2))
    if not dry_run:
        print(
            "AVISO: a assistência LLM não persiste propostas (autoridade humana). "
            "Nada foi gravado.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
