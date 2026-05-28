#!/usr/bin/env python3
"""archaeologist-impact — change impact analyzer.

Given a file or function you're about to change, shows:
- Everything that calls it (direct callers)
- Everything that imports it (files at risk)
- Test coverage (which tests cover it)
- Blast radius score (how risky is this change)
"""
import os
import sys
import re
from pathlib import Path
from collections import defaultdict

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich import box

from archaeologist.scanner import scan_directory

console = Console()


def find_target_files(project_path: str, target: str) -> list[str]:
    """Find files matching the target pattern."""
    target = target.strip('./')
    matches = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {
            '.git', 'node_modules', '.dart_tool', 'build',
            '.pub-cache', 'Pods', '.gradle', 'ephemeral'
        }]
        for f in files:
            filepath = os.path.join(root, f)
            rel = os.path.relpath(filepath, project_path)
            if (target in rel or
                target == f or
                target == Path(f).stem or
                rel.endswith(target)):
                matches.append(filepath)
    return matches


def find_callers(scan_result, target_file: str, project_path: str) -> dict:
    """Find all files and functions that call functions defined in target_file."""
    # Get all function names defined in the target file
    target_functions = set()
    for name, defs in scan_result.definitions.items():
        for d in defs:
            if d.file == target_file:
                target_functions.add(name)

    if not target_functions:
        return {}

    # Find which files call these functions
    callers = defaultdict(set)  # file -> set of function names it calls from target
    for calling_file, called_names in scan_result.calls.items():
        if calling_file == target_file:
            continue
        clean_calls = {n for n in called_names
                      if not n.startswith('__qualified__')
                      and not n.startswith('__imported__')}
        overlap = target_functions & clean_calls
        if overlap:
            callers[calling_file] = overlap

    return dict(callers)


def find_importers(project_path: str, target_file: str) -> list[str]:
    """Find all files that import the target file."""
    rel_target = os.path.relpath(target_file, project_path)
    target_name = Path(target_file).name
    target_stem = Path(target_file).stem

    importers = []
    import_patterns = [
        re.compile(r"import\s+['\"]([^'\"]+)['\"]"),          # Dart/JS
        re.compile(r"from\s+['\"]?([^'\";\s]+)['\"]?\s+import"), # Python
        re.compile(r"import\s+\"([^\"]+)\""),                   # Go
    ]

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {
            '.git', 'node_modules', '.dart_tool', 'build',
            '.pub-cache', 'Pods', '.gradle', 'ephemeral'
        }]
        for fname in files:
            if not any(fname.endswith(ext) for ext in
                      ['.dart', '.py', '.js', '.ts', '.go', '.java', '.rb', '.rs', '.kt', '.swift']):
                continue
            filepath = os.path.join(root, fname)
            if filepath == target_file:
                continue
            try:
                content = Path(filepath).read_text(encoding='utf-8', errors='replace')
                for pattern in import_patterns:
                    for m in pattern.finditer(content):
                        imp = m.group(1)
                        if (target_name in imp or
                            target_stem in imp or
                            rel_target in imp or
                            imp.endswith(target_stem)):
                            importers.append(filepath)
                            break
            except Exception:
                continue

    return list(set(importers))


def find_tests(project_path: str, target_file: str, callers: dict) -> list[str]:
    """Find test files that likely cover the target."""
    target_stem = Path(target_file).stem
    test_files = []

    # Direct test files (test_X.py, X_test.dart etc.)
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '.dart_tool', 'build'}]
        for fname in files:
            filepath = os.path.join(root, fname)
            is_test = (
                fname.startswith('test_') or
                fname.endswith('_test.dart') or
                fname.endswith('_test.py') or
                fname.endswith('.test.ts') or
                fname.endswith('.spec.ts') or
                fname.endswith('_spec.rb') or
                'test' in filepath.lower().split(os.sep)
            )
            if is_test and (target_stem in fname or target_stem in filepath):
                test_files.append(filepath)

    # Also check if any callers are test files
    for caller_file in callers:
        if ('test' in caller_file.lower() or
            Path(caller_file).name.startswith('test_') or
            caller_file.endswith('_test.dart')):
            if caller_file not in test_files:
                test_files.append(caller_file)

    return list(set(test_files))


def calculate_blast_radius(callers: dict, importers: list, tests: list,
                            target_functions: int) -> tuple[int, str]:
    """Calculate a blast radius score and risk label."""
    score = 0

    # Number of direct callers
    caller_count = len(callers)
    if caller_count == 0:
        score += 0
    elif caller_count <= 3:
        score += 20
    elif caller_count <= 10:
        score += 40
    elif caller_count <= 20:
        score += 60
    else:
        score += 80

    # Number of importers
    importer_count = len(importers)
    if importer_count > 20:
        score += 20
    elif importer_count > 10:
        score += 15
    elif importer_count > 5:
        score += 10
    elif importer_count > 0:
        score += 5

    # Test coverage
    if len(tests) == 0:
        score += 20  # No tests = higher risk
    elif len(tests) < 3:
        score += 10

    score = min(score, 100)

    if score >= 70:
        label = "HIGH RISK"
        color = "red"
    elif score >= 40:
        label = "MEDIUM RISK"
        color = "yellow"
    else:
        label = "LOW RISK"
        color = "green"

    return score, label, color



def build_impact_html(data: dict) -> str:
    """Build a beautiful HTML impact report."""
    score = data['score']
    risk_label = data['risk_label']
    risk_color = '#E24B4A' if score >= 70 else '#EF9F27' if score >= 40 else '#4a9e6b'
    
    callers_html = ''
    for cf, fns in sorted(data['callers'].items())[:50]:
        fn_tags = ''.join(f'<span class="fn-tag">{f}</span>' for f in sorted(fns)[:5])
        if len(fns) > 5:
            fn_tags += f'<span class="fn-tag dim">+{len(fns)-5} more</span>'
        callers_html += f'<div class="dep-row"><div class="dep-file">{cf}</div><div class="dep-fns">{fn_tags}</div></div>'
    if not callers_html:
        callers_html = '<div class="empty">No direct callers found — changes here are low risk</div>'

    importers_html = ''
    for f in sorted(data['importers'])[:50]:
        importers_html += f'<div class="dep-row simple"><div class="dep-file">{f}</div></div>'
    if not importers_html:
        importers_html = '<div class="empty">No files import this directly</div>'

    tests_html = ''
    for t in data['tests'][:20]:
        tests_html += f'<div class="dep-row simple"><div class="dep-file" style="color:#4a9e6b">✓ {t}</div></div>'
    if not tests_html:
        tests_html = '<div class="empty" style="color:#e05a3a">✗ No test files found — changes are unverified</div>'

    fns_html = ''
    for fn in data['functions'][:30]:
        fns_html += f'<div class="fn-item"><span class="fn-name">{fn["name"]}</span><span class="fn-line">line {fn["line"]}</span></div>'

    rec_color = '#E24B4A' if score >= 70 else '#EF9F27' if score >= 40 else '#4a9e6b'
    rec_icon = '⚠' if score >= 70 else '△' if score >= 40 else '✓'
    if score >= 70:
        rec_text = f'{len(data["callers"])} files call this directly. Run your full test suite after any changes.'
        if not data["tests"]:
            rec_text += ' <strong style="color:#e05a3a">No tests found — write tests before making changes.</strong>'
    elif score >= 40:
        rec_text = f'Review the {len(data["callers"])} callers before changing. Check that callers can handle any signature changes.'
    else:
        rec_text = 'Low blast radius. Safe to change with normal care.'
        if not data["callers"]:
            rec_text += ' No callers found — this may be unused code.'

    bar_pct = score

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Impact Analysis — {data["target"]}</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Mono:wght@400;500&family=Syne:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0a0a08; color: #e8e4dc; font-family: 'Syne', sans-serif; min-height: 100vh; }}
.topbar {{ background: #111110; border-bottom: 1px solid #2a2a24; padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem; }}
.logo {{ font-family: 'Instrument Serif', serif; font-size: 16px; color: #c9a84c; font-style: italic; }}
.target-name {{ font-family: 'DM Mono', monospace; font-size: 13px; color: #74b9ff; }}
.project-name {{ font-size: 12px; color: #6b6b5f; margin-left: auto; }}

.hero {{ padding: 3rem 2rem 2rem; max-width: 1000px; margin: 0 auto; }}
.hero-title {{ font-family: 'Instrument Serif', serif; font-size: 42px; color: #f5f0e8; line-height: 1.1; margin-bottom: 0.5rem; }}
.hero-title em {{ font-style: italic; color: #c9a84c; }}
.hero-sub {{ font-size: 14px; color: #6b6b5f; margin-bottom: 2rem; }}

.score-block {{ display: flex; align-items: center; gap: 2rem; background: #111110; border: 1px solid #2a2a24; padding: 1.5rem 2rem; margin-bottom: 2rem; flex-wrap: wrap; }}
.score-num {{ font-family: 'Instrument Serif', serif; font-size: 64px; line-height: 1; color: {risk_color}; }}
.score-right {{ flex: 1; }}
.score-label {{ font-size: 18px; font-weight: 600; color: {risk_color}; margin-bottom: 8px; }}
.score-bar-track {{ height: 8px; background: #2a2a24; border-radius: 4px; overflow: hidden; margin-bottom: 12px; }}
.score-bar-fill {{ height: 8px; border-radius: 4px; background: {risk_color}; width: {bar_pct}%; transition: width 1s ease; }}
.score-stats {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
.score-stat {{ text-align: center; }}
.score-stat-n {{ font-family: 'Instrument Serif', serif; font-size: 32px; color: #c9a84c; line-height: 1; }}
.score-stat-l {{ font-size: 11px; color: #6b6b5f; margin-top: 4px; letter-spacing: 0.08em; text-transform: uppercase; }}

.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2px; background: #2a2a24; max-width: 1000px; margin: 0 auto 2px; }}
.grid-full {{ max-width: 1000px; margin: 0 auto 2px; background: #111110; border: 1px solid #2a2a24; }}
.panel {{ background: #111110; padding: 1.5rem; }}
.panel-title {{ font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: #6b6b5f; font-weight: 600; margin-bottom: 1rem; display: flex; align-items: center; gap: 8px; }}
.panel-count {{ font-family: 'DM Mono', monospace; font-size: 11px; background: #1a1a17; border: 1px solid #2a2a24; padding: 2px 8px; border-radius: 99px; color: #c9a84c; }}

.dep-row {{ display: flex; align-items: flex-start; gap: 1rem; padding: 8px 0; border-bottom: 1px solid #1a1a17; }}
.dep-row:last-child {{ border-bottom: none; }}
.dep-row.simple {{ align-items: center; }}
.dep-file {{ font-family: 'DM Mono', monospace; font-size: 12px; color: #74b9ff; flex-shrink: 0; max-width: 50%; word-break: break-all; }}
.dep-fns {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.fn-tag {{ font-family: 'DM Mono', monospace; font-size: 10px; padding: 2px 8px; background: #1a1a17; border: 1px solid #2a2a24; color: #c9a84c; border-radius: 99px; }}
.fn-tag.dim {{ color: #6b6b5f; }}
.empty {{ font-size: 13px; color: #4a4a40; font-style: italic; padding: 8px 0; }}

.fn-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }}
.fn-item {{ background: #1a1a17; border: 1px solid #2a2a24; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; }}
.fn-name {{ font-family: 'DM Mono', monospace; font-size: 12px; color: #e8e4dc; }}
.fn-line {{ font-size: 11px; color: #6b6b5f; }}

.rec-block {{ max-width: 1000px; margin: 0 auto 2rem; background: #111110; border: 1px solid #2a2a24; border-left: 3px solid {rec_color}; padding: 1.25rem 1.5rem; display: flex; align-items: flex-start; gap: 12px; }}
.rec-icon {{ font-size: 20px; color: {rec_color}; flex-shrink: 0; margin-top: 2px; }}
.rec-text {{ font-size: 14px; color: #b0aa9a; line-height: 1.7; }}

::-webkit-scrollbar {{ width: 6px; }} ::-webkit-scrollbar-track {{ background: #111110; }} ::-webkit-scrollbar-thumb {{ background: #2a2a24; }}
</style>
</head>
<body>

<div class="topbar">
  <span class="logo">☠ archaeologist-impact</span>
  <span style="color:#2a2a24">|</span>
  <span class="target-name">{data["target"]}</span>
  <span class="project-name">{data["project"]}</span>
</div>

<div class="hero">
  <h1 class="hero-title">Change Impact: <em>{data["target_short"]}</em></h1>
  <p class="hero-sub">{data["target"]} · {data["project"]}</p>

  <div class="score-block">
    <div class="score-num">{score}</div>
    <div class="score-right">
      <div class="score-label">{risk_label}</div>
      <div class="score-bar-track"><div class="score-bar-fill"></div></div>
      <div class="score-stats">
        <div class="score-stat"><div class="score-stat-n">{len(data["functions"])}</div><div class="score-stat-l">Functions</div></div>
        <div class="score-stat"><div class="score-stat-n">{len(data["callers"])}</div><div class="score-stat-l">Direct callers</div></div>
        <div class="score-stat"><div class="score-stat-n">{len(data["importers"])}</div><div class="score-stat-l">Importers</div></div>
        <div class="score-stat"><div class="score-stat-n">{len(data["tests"])}</div><div class="score-stat-l">Test files</div></div>
      </div>
    </div>
  </div>
</div>

<div class="rec-block">
  <div class="rec-icon">{rec_icon}</div>
  <div class="rec-text"><strong style="color:#e8e4dc">Before you change this file:</strong> {rec_text}</div>
</div>

<div class="grid">
  <div class="panel">
    <div class="panel-title">Files that call this <span class="panel-count">{len(data["callers"])}</span></div>
    {callers_html}
  </div>
  <div class="panel">
    <div class="panel-title">Files that import this <span class="panel-count">{len(data["importers"])}</span></div>
    {importers_html}
  </div>
</div>

<div class="grid">
  <div class="panel">
    <div class="panel-title">Test coverage <span class="panel-count">{len(data["tests"])}</span></div>
    {tests_html}
  </div>
  <div class="panel">
    <div class="panel-title">Functions in this file <span class="panel-count">{len(data["functions"])}</span></div>
    <div class="fn-grid">{fns_html}</div>
  </div>
</div>

</body>
</html>"""


@click.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.argument("target")
@click.option("--no-git", is_flag=True, help="Skip git analysis")
@click.option("--html", "open_html", is_flag=True, help="Open results as HTML in browser")
@click.option("--output", default=None, help="Save HTML to file")
def cli(project_path, target, no_git, open_html, output):
    """
    Analyze the blast radius of changing a file or function.

    TARGET can be a file name, partial path, or function name.

    Examples:

      archaeologist-impact ./my-project user_service.dart

      archaeologist-impact ./my-project lib/services/user_service.dart

      archaeologist-impact . logger.dart
    """
    abs_path = os.path.abspath(project_path)

    console.print(Panel.fit(
        f"[bold]☠ archaeologist-impact[/bold]\n"
        f"[dim]Project: [cyan]{abs_path}[/cyan][/dim]\n"
        f"[dim]Target:  [cyan]{target}[/cyan][/dim]",
        border_style="dim"
    ))

    # Find target file(s)
    with console.status("[dim]Locating target...[/dim]", spinner="dots"):
        target_files = find_target_files(abs_path, target)

    if not target_files:
        console.print(f"\n[red]✗ Could not find '{target}' in {abs_path}[/red]")
        console.print("[dim]  Try a partial file name, e.g. 'user_service' or 'logger.dart'[/dim]\n")
        sys.exit(1)

    if len(target_files) > 1:
        console.print(f"\n[yellow]Multiple matches found — showing first result:[/yellow]")
        for f in target_files:
            console.print(f"  [dim]{os.path.relpath(f, abs_path)}[/dim]")
        console.print()

    target_file = target_files[0]
    rel_target = os.path.relpath(target_file, abs_path)

    console.print(f"\n[dim]  Analyzing: [cyan]{rel_target}[/cyan][/dim]\n")

    # Scan project
    with console.status("[dim]Scanning codebase...[/dim]", spinner="dots"):
        scan_result = scan_directory(abs_path)

    # Get target functions
    target_functions = []
    for name, defs in scan_result.definitions.items():
        for d in defs:
            if d.file == target_file and not d.is_test:
                target_functions.append(d)

    # Find callers, importers, tests
    with console.status("[dim]Finding callers...[/dim]", spinner="dots"):
        callers = find_callers(scan_result, target_file, abs_path)

    with console.status("[dim]Finding importers...[/dim]", spinner="dots"):
        importers = find_importers(abs_path, target_file)

    with console.status("[dim]Finding tests...[/dim]", spinner="dots"):
        tests = find_tests(abs_path, target_file, callers)

    # Calculate blast radius
    score, risk_label, risk_color = calculate_blast_radius(
        callers, importers, tests, len(target_functions)
    )

    # ── Display results ───────────────────────────────────────────────────

    # Blast radius score
    bar_width = 30
    filled = int((score / 100) * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    bar_colored = Text(bar, style=risk_color)

    console.print(f"  [bold]Blast Radius[/bold]")
    console.print(f"  ", end="")
    console.print(bar_colored, end="")
    console.print(f"  [{risk_color}]{score}/100 — {risk_label}[/{risk_color}]\n")

    # Summary stats
    console.print(
        f"  [cyan]{len(target_functions)}[/cyan] functions defined  "
        f"[cyan]{len(callers)}[/cyan] direct callers  "
        f"[cyan]{len(importers)}[/cyan] files import it  "
        f"[cyan]{len(tests)}[/cyan] test files\n"
    )

    # Functions in this file
    if target_functions:
        console.print(f"  [dim]── Functions in this file ──────────────────────────[/dim]")
        for fn in target_functions[:15]:
            console.print(f"  [cyan]{fn.name}[/cyan] [dim](line {fn.line})[/dim]")
        if len(target_functions) > 15:
            console.print(f"  [dim]  ...and {len(target_functions)-15} more[/dim]")
        console.print()

    # Direct callers
    console.print(f"  [dim]── Files that call functions here ──────────────────[/dim]")
    if callers:
        table = Table(box=box.SIMPLE, show_header=True, header_style="dim",
                      show_edge=False, pad_edge=False)
        table.add_column("File", style="dim", max_width=50)
        table.add_column("Calls", style="cyan", max_width=40)

        for caller_file, fns in sorted(callers.items())[:20]:
            rel = os.path.relpath(caller_file, abs_path)
            fn_list = ", ".join(sorted(fns)[:4])
            if len(fns) > 4:
                fn_list += f" +{len(fns)-4} more"
            table.add_row(rel, fn_list)

        if len(callers) > 20:
            table.add_row(f"...and {len(callers)-20} more", "")

        console.print(table)
    else:
        console.print("  [dim]  No direct callers found — this file may be safe to change freely[/dim]")
    console.print()

    # Importers
    console.print(f"  [dim]── Files that import this file ─────────────────────[/dim]")
    if importers:
        for f in sorted(importers)[:15]:
            rel = os.path.relpath(f, abs_path)
            console.print(f"  [dim]{rel}[/dim]")
        if len(importers) > 15:
            console.print(f"  [dim]  ...and {len(importers)-15} more[/dim]")
    else:
        console.print("  [dim]  No files import this directly[/dim]")
    console.print()

    # Tests
    console.print(f"  [dim]── Test coverage ────────────────────────────────────[/dim]")
    if tests:
        for t in tests[:10]:
            rel = os.path.relpath(t, abs_path)
            console.print(f"  [green]✓[/green] [dim]{rel}[/dim]")
    else:
        console.print("  [red]✗ No test files found for this file — changes are unverified[/red]")
    console.print()

    # Recommendations
    console.print(f"  [dim]── Before you change this file ─────────────────────[/dim]")
    if score >= 70:
        console.print(f"  [red]⚠  High blast radius.[/red] {len(callers)} files call this directly.")
        console.print(f"  [dim]   Run your full test suite after changes.[/dim]")
        if not tests:
            console.print(f"  [red]   No tests found — write tests before making changes.[/red]")
    elif score >= 40:
        console.print(f"  [yellow]△  Medium blast radius.[/yellow] Review the {len(callers)} callers above before changing.")
        console.print(f"  [dim]   Check that callers can handle any signature changes.[/dim]")
    else:
        console.print(f"  [green]✓  Low blast radius.[/green] Safe to change with normal care.")
        if not callers:
            console.print(f"  [dim]   No callers found — this may be unused code.[/dim]")
    console.print()

    # HTML output
    if open_html or output:
        import webbrowser, tempfile, json
        
        data = {
            "project": abs_path,
            "target": rel_target,
            "target_short": Path(target_file).stem,
            "score": score,
            "risk_label": risk_label,
            "functions": [{"name": f.name, "line": f.line} for f in target_functions],
            "callers": {os.path.relpath(k, abs_path): list(v) for k, v in callers.items()},
            "importers": [os.path.relpath(f, abs_path) for f in importers],
            "tests": [os.path.relpath(f, abs_path) for f in tests],
        }
        
        html = build_impact_html(data)
        
        if output:
            out_path = os.path.abspath(output)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(html)
            console.print(f"[green]✓ Report saved:[/green] {out_path}")
            console.print(f"[dim]  Open with: open {out_path}[/dim]\n")
        else:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                             prefix='archaeologist_impact_', encoding='utf-8') as f:
                f.write(html)
                tmp = f.name
            webbrowser.open(f'file://{tmp}')
            console.print(f"[green]✓ Impact report opened in browser![/green]\n")


if __name__ == "__main__":
    cli()
