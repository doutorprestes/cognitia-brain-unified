"""CLI para o módulo de vinculação — IA Brasil.

Uso:
    python -m src.modules.linking run [--threshold 0.7] [--dry-run]
    python -m src.modules.linking stats
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="linking",
    help="Vinculação de evidências a ações do PBIA",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    threshold: float = typer.Option(0.7, help="Confiança mínima para criar vínculo"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Apenas sugerir, não criar vínculos"
    ),
    limit: int | None = typer.Option(None, help="Limite de evidências a processar"),
) -> None:
    """Executa o pipeline de vinculação automática."""
    from src.modules.linking.auto_linker import auto_link

    console.print("[bold]Iniciando vinculação automática...[/bold]")

    result = asyncio.run(auto_link(confidence_threshold=threshold, dry_run=dry_run, limit=limit))

    # Resumo
    console.print("\n[bold]Resumo:[/bold]")
    console.print(f"  Total de evidências: {result.total_evidencias}")
    console.print(f"  Com vínculo existente: {result.evidencias_com_vinculo}")
    console.print(f"  Sem vínculo (novas): {result.evidencias_novas}")

    if dry_run:
        console.print("\n[bold yellow]MODO DRY-RUN — Nenhum vínculo criado[/bold yellow]")
    else:
        console.print(f"  Vínculos criados: {result.vinculos_criados}")

    if result.errors:
        console.print(f"\n[bold red]Erros ({len(result.errors)}):[/bold red]")
        for err in result.errors[:5]:
            console.print(f"  - {err}")
        if len(result.errors) > 5:
            console.print(f"  ... e mais {len(result.errors) - 5} erros")

    # Top sugestões
    if result.suggestions:
        table = Table(title="Top Sugestões")
        table.add_column("Evidência", style="cyan")
        table.add_column("Ação", style="green")
        table.add_column("Confiança", justify="right")
        table.add_column("Status")
        table.add_column("Justificativa", max_width=50)

        for s in result.suggestions[:20]:
            table.add_row(
                s.evidencia_id[:16],
                s.action_name[:40] or s.acao_id[:16],
                f"{s.confidence:.3f}",
                s.status,
                s.justification[:50],
            )

        console.print(table)


@app.command()
def stats() -> None:
    """Mostra estatísticas de vinculação."""
    from src.modules.linking.auto_linker import get_stats

    data = asyncio.run(get_stats())

    console.print("[bold]Estatísticas de Vinculação[/bold]\n")

    table = Table(show_header=False)
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", justify="right")

    table.add_row("Total de vínculos", str(data["total_vinculos"]))
    table.add_row("Total de evidências", str(data["total_evidencias"]))
    table.add_row("Evidências com vínculo", str(data["evidencias_com_vinculo"]))
    table.add_row("Evidências sem vínculo", str(data["evidencias_sem_vinculo"]))

    console.print(table)

    # Por método
    por_metodo_raw = data.get("por_metodo", {})
    por_metodo = por_metodo_raw if isinstance(por_metodo_raw, dict) else {}
    if por_metodo:
        console.print("\n[bold]Por método de criação:[/bold]")
        table2 = Table(show_header=False)
        table2.add_column("Método", style="cyan")
        table2.add_column("Quantidade", justify="right")
        for metodo, count in por_metodo.items():
            table2.add_row(metodo, str(count))
        console.print(table2)


if __name__ == "__main__":
    app()
