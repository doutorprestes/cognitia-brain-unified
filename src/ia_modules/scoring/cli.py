"""CLI para scoring — IA Brasil.

Uso:
    python -m src.modules.scoring run --all
    python -m src.modules.scoring run --eixo-id eixo1
"""

from __future__ import annotations

import asyncio
import sys

from src.modules.scoring.pipeline import ScoringPipeline


async def main(args: list[str]) -> None:
    """Entry point do CLI de scoring.

    Args:
        args: Argumentos da linha de comando.
    """
    if len(args) < 2 or args[1] != "run":
        print("Uso: python -m src.modules.scoring run [opções]")
        print("Opções:")
        print("  --all          Processar todas as ações")
        print("  --eixo-id ID   Filtrar por eixo")
        sys.exit(1)

    eixo_id: str | None = None

    i = 2
    while i < len(args):
        if args[i] == "--eixo-id" and i + 1 < len(args):
            eixo_id = args[i + 1]
            i += 2
        elif args[i] == "--all":
            i += 1
        else:
            print(f"Argumento desconhecido: {args[i]}")
            sys.exit(1)

    print("Iniciando pipeline de scoring...")

    if eixo_id:
        result = await ScoringPipeline.run_for_eixo(eixo_id)
    else:
        result = await ScoringPipeline.run_all()

    print("\nResultado:")
    print(f"  Total: {result.total}")
    print(f"  Processadas: {result.processadas}")
    print(f"  Atualizadas: {result.atualizadas}")
    print(f"  Erros: {result.erros}")

    if result.resultados:
        print("\nDetalhes:")
        for r in result.resultados:
            changed = r.status_anterior != r.status_novo
            marker = "*" if changed else " "
            print(
                f"  [{marker}] {r.acao_id}: "
                f"{r.status_anterior.value} -> {r.status_novo.value} "
                f"(conf={r.confidence:.2f})"
            )


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
