#!/usr/bin/env python3
import json
import sys
import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.scanner import scan_directory
from src.git_analyzer import analyze_git_history
from src.scorer import analyze

console = Console()


def confidence_bar(score: int, width: int = 12) -> Text:
    filled = int((score / 100) * width)
    bar = "█" * filled + "░" * (width - filled)
    if score >= 80:
        color = "red"
    elif score >= 50:
        color = "yellow"
    else:
        color = "blue"
    return Text(bar, style=color)


def label_style(label: str) -> str:
    if label == "Safe to delete":
        return "green"
    elif label == "Review first":
        return "yellow"
    return "blue"


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--min-confidence", default=40, help="Minimum confidence score to show (0-100)")
@click.option("--limit", default=50, help="Max results to show")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--explain", is_flag=True, help="Show detailed reasons for each result")
@click.option("--no-git", is_flag=True, help="Skip git history analysis")
def cli(path, min_confidence, limit, json_output, explain, no_git):
    """
    Dead Code Archaeologist — find unused functions in your codebase.

    Examples:

      deadcode .                     scan current directory

      deadcode ./src --explain       show why each function is flagged

      deadcode . --min-confidence 70  only show high-confidence dead code

      deadcode . --json-output > report.json
    """
    abs_path = os.path.abspath(path)

    if not json_output:
        console.print(Panel.fit(
            "[bold]Dead Code Archaeologist[/bold]\n"
            f"[dim]Scanning [cyan]{abs_path}[/cyan][/dim]",
            border_style="dim"
        ))

    # Step 1: scan files
    with console.status("[dim]Parsing files...[/dim]", spinner="dots") if not json_output else _nullctx():
        scan_result = scan_directory(abs_path)

    total_funcs = sum(len(v) for v in scan_result.definitions.values())
    total_files = len(scan_result.calls)

    if not json_output:
        console.print(f"[dim]  Found {total_funcs} functions across {total_files} files[/dim]")

    # Step 2: git history
    git_info_map = {}
    if not no_git:
        with console.status("[dim]Analyzing git history...[/dim]", spinner="dots") if not json_output else _nullctx():
            all_files = list(scan_result.calls.keys())
            git_info_map = analyze_git_history(abs_path, all_files)

    # Step 3: score
    candidates = analyze(scan_result, git_info_map, min_confidence=min_confidence)
    shown = candidates[:limit]

    if json_output:
        output = []
        for c in shown:
            output.append({
                "name": c.name,
                "file": c.file,
                "line": c.line,
                "language": c.language,
                "confidence": c.confidence,
                "label": c.label,
                "reasons": c.reasons,
                "callers_found": c.callers_found,
                "days_since_touched": c.days_since_touched,
                "author_count": c.author_count,
            })
        print(json.dumps({"total_functions": total_funcs, "suspects": output}, indent=2))
        return

    if not shown:
        console.print("\n[green]No dead code found above the confidence threshold.[/green]")
        return

    # Summary stats
    safe = sum(1 for c in candidates if c.label == "Safe to delete")
    review = sum(1 for c in candidates if c.label == "Review first")
    runtime = sum(1 for c in candidates if c.label == "Needs runtime data")

    console.print(f"\n  [red]{safe}[/red] safe to delete  "
                  f"[yellow]{review}[/yellow] review first  "
                  f"[blue]{runtime}[/blue] needs runtime data\n")

    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="dim",
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("Confidence", width=14)
    table.add_column("Function", style="cyan", no_wrap=True, max_width=30)
    table.add_column("File", style="dim", no_wrap=True, max_width=40)
    table.add_column("Verdict", width=18)
    if explain:
        table.add_column("Why", max_width=45)

    for c in shown:
        rel_file = os.path.relpath(c.file, abs_path)
        file_with_line = f"{rel_file}:{c.line}"
        verdict = Text(c.label, style=label_style(c.label))

        row = [
            confidence_bar(c.confidence),
            c.name,
            file_with_line,
            verdict,
        ]
        if explain:
            row.append(Text(" · ".join(c.reasons), style="dim"))

        table.add_row(*row)

    console.print(table)

    if len(candidates) > limit:
        console.print(f"[dim]  ... and {len(candidates) - limit} more. Use --limit to see more.[/dim]")

    console.print(f"\n[dim]  Tip: run with --explain to see why each function was flagged[/dim]")
    console.print(f"[dim]  Tip: run with --json-output to pipe results into a dashboard[/dim]\n")


class _nullctx:
    def __enter__(self): return self
    def __exit__(self, *a): pass


if __name__ == "__main__":
    cli()
