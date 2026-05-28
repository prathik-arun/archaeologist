#!/usr/bin/env python3
"""deadcode-clean — auto clean command."""
import sys
import os
import subprocess

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Confirm

from archaeologist.scanner import scan_directory
from archaeologist.git_analyzer import analyze_git_history
from archaeologist.scorer import analyze
from archaeologist.deleter import find_deletion_range, delete_function_from_file
from archaeologist.test_runner import detect_framework, run_tests
from archaeologist.pr_opener import create_cleanup_branch, commit_deletions, push_branch, open_pr

console = Console()


def _git_stash_status(project_path):
    result = subprocess.run(["git", "status", "--porcelain"],
                            cwd=project_path, capture_output=True, text=True)
    return result.stdout.strip() == ""


def _git_current_branch(project_path):
    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=project_path, capture_output=True, text=True)
    return result.stdout.strip()


def _git_reset(project_path, branch):
    subprocess.run(["git", "checkout", "-f", branch], cwd=project_path, capture_output=True)
    subprocess.run(["git", "branch", "-D", branch], cwd=project_path, capture_output=True)


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--min-confidence", default=75, help="Minimum confidence to auto-delete (default: 75)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without doing it")
@click.option("--no-pr", is_flag=True, help="Skip opening a GitHub PR")
@click.option("--no-tests", is_flag=True, help="Skip running tests")
@click.option("--limit", default=50, help="Max functions to delete in one run")
@click.option("--lang", default=None, help="Only clean a specific language (e.g. dart, python)")
def cli(path, min_confidence, dry_run, no_pr, no_tests, limit, lang):
    """
    Auto-clean dead code: scan → delete → test → open PR.

    Examples:

      deadcode-clean .                      full auto clean

      deadcode-clean . --dry-run            preview only, no changes

      deadcode-clean . --min-confidence 85  only very high confidence

      deadcode-clean . --no-pr              delete + test, skip PR

      deadcode-clean . --lang dart          only clean Dart files
    """
    abs_path = os.path.abspath(path)

    console.print(Panel.fit(
        "[bold]Dead Code Archaeologist — Auto Cleaner[/bold]\n"
        f"[dim]Project: [cyan]{abs_path}[/cyan][/dim]",
        border_style="dim"
    ))

    if not dry_run:
        if not _git_stash_status(abs_path):
            console.print("\n[red]✗ Working tree has uncommitted changes.[/red]")
            console.print("[dim]  Please commit or stash your changes first.[/dim]\n")
            sys.exit(1)

    original_branch = _git_current_branch(abs_path)
    console.print(f"[dim]  On branch: {original_branch}[/dim]")

    with console.status("[dim]Scanning codebase...[/dim]", spinner="dots"):
        scan_result = scan_directory(abs_path)

    total = sum(len(v) for v in scan_result.definitions.values())
    console.print(f"[dim]  Found {total} functions across {len(scan_result.calls)} files[/dim]")

    with console.status("[dim]Analyzing git history...[/dim]", spinner="dots"):
        git_info_map = analyze_git_history(abs_path, list(scan_result.calls.keys()))

    candidates = analyze(scan_result, git_info_map, min_confidence=min_confidence)
    targets = [c for c in candidates if c.label == "Safe to delete" and c.confidence >= min_confidence]

    if lang:
        targets = [c for c in targets if c.language == lang]

    targets = targets[:limit]

    if not targets:
        console.print(f"\n[green]No functions found above {min_confidence}% confidence. Your codebase is clean![/green]\n")
        return

    console.print(f"\n  Found [red]{len(targets)}[/red] functions to delete "
                  f"([dim]≥{min_confidence}% confidence, 'Safe to delete'[/dim])\n")

    table = Table(box=box.SIMPLE, show_header=True, header_style="dim",
                  show_edge=False, pad_edge=False)
    table.add_column("Confidence", width=12)
    table.add_column("Function", style="cyan", max_width=28)
    table.add_column("File", style="dim", max_width=45)
    table.add_column("Why", style="dim", max_width=40)

    for c in targets[:20]:
        rel = os.path.relpath(c.file, abs_path)
        table.add_row(f"{c.confidence}%", c.name, f"{rel}:{c.line}", " · ".join(c.reasons[:2]))

    if len(targets) > 20:
        table.add_row("...", f"...and {len(targets)-20} more", "", "")

    console.print(table)

    if dry_run:
        console.print("\n[yellow]Dry run — no changes made.[/yellow]\n")
        return

    if not Confirm.ask(f"\n  Proceed with deleting {len(targets)} functions?"):
        console.print("[dim]  Aborted.[/dim]\n")
        return

    framework = detect_framework(abs_path)
    if framework:
        console.print(f"[dim]  Test framework detected: {framework}[/dim]")

    cleanup_branch = None
    with console.status("[dim]Creating cleanup branch...[/dim]", spinner="dots"):
        cleanup_branch = create_cleanup_branch(abs_path)
    console.print(f"[dim]  Created branch: [cyan]{cleanup_branch}[/cyan][/dim]")

    deleted = []
    failed = []

    with console.status("[dim]Deleting functions...[/dim]", spinner="dots"):
        for candidate in targets:
            deletion = find_deletion_range(candidate.file, candidate.name,
                                           candidate.line, candidate.language)
            if deletion is None:
                failed.append(candidate)
                continue
            success = delete_function_from_file(candidate.file, deletion)
            if success:
                deleted.append({
                    "name": candidate.name,
                    "file": os.path.relpath(candidate.file, abs_path),
                    "line": candidate.line,
                    "confidence": candidate.confidence,
                    "language": candidate.language,
                })
            else:
                failed.append(candidate)

    console.print(f"  [green]✓[/green] Deleted {len(deleted)} functions  "
                  f"[dim]({len(failed)} skipped — could not locate precisely)[/dim]")

    if not deleted:
        console.print("\n[yellow]No functions deleted. Rolling back.[/yellow]")
        if cleanup_branch:
            _git_reset(abs_path, original_branch)
        return

    if not no_tests and framework:
        console.print(f"\n  Running [cyan]{framework}[/cyan] tests...")
        test_result = run_tests(abs_path, framework)
        if test_result.passed:
            console.print("  [green]✓ Tests passed[/green]")
        else:
            console.print("  [red]✗ Tests failed![/red]")
            console.print(f"[dim]{test_result.output[-1000:]}[/dim]")
            console.print("\n[yellow]  Rolling back...[/yellow]")
            if cleanup_branch:
                _git_reset(abs_path, original_branch)
            console.print("[dim]  Rolled back. No changes made.[/dim]\n")
            return
    else:
        console.print("  [dim]Skipping tests[/dim]")

    with console.status("[dim]Committing...[/dim]", spinner="dots"):
        committed = commit_deletions(abs_path, deleted)

    if not committed:
        console.print("[red]  Failed to commit.[/red]")
        return

    console.print(f"  [green]✓[/green] Committed {len(deleted)} deletions")

    if not no_pr:
        if not Confirm.ask("\n  Push branch and open a GitHub PR?"):
            console.print(f"[dim]  Branch ready: {cleanup_branch}[/dim]")
            console.print(f"[dim]  Push manually: git push origin {cleanup_branch}[/dim]\n")
            return

        with console.status("[dim]Pushing...[/dim]", spinner="dots"):
            pushed = push_branch(abs_path, cleanup_branch)

        if not pushed:
            console.print("[red]  Could not push. Do you have a remote configured?[/red]")
            console.print(f"[dim]  Branch ready locally: {cleanup_branch}[/dim]\n")
            return

        with console.status("[dim]Opening PR...[/dim]", spinner="dots"):
            pr_result = open_pr(abs_path, cleanup_branch, deleted)

        if pr_result.success:
            console.print(f"\n  [green]✓ PR opened![/green] {pr_result.pr_url}\n")
        else:
            console.print(f"\n  [yellow]Branch pushed but PR creation failed.[/yellow]")
            console.print(f"  [dim]Open manually for branch: {cleanup_branch}[/dim]\n")
    else:
        console.print(f"\n  [green]✓ Done![/green] Branch: [cyan]{cleanup_branch}[/cyan]")
        console.print(f"  [dim]Push with: git push origin {cleanup_branch}[/dim]\n")


if __name__ == "__main__":
    cli()
