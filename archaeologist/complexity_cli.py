#!/usr/bin/env python3
"""archaeologist-complexity — cyclomatic complexity scorer.

Finds the most complex functions in your codebase — too long,
too nested, too many branches. Ranks them worst-first.
"""
import os
import sys
import re
from pathlib import Path
from dataclasses import dataclass

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from archaeologist.scanner import scan_directory

console = Console()


@dataclass
class ComplexityResult:
    name: str
    file: str
    line: int
    language: str
    score: int          # cyclomatic complexity
    lines: int          # function length in lines
    nesting: int        # max nesting depth
    branches: int       # number of decision points
    label: str          # Simple / Moderate / Complex / Very Complex


# Decision point keywords per language
BRANCH_PATTERNS = {
    'python': re.compile(
        r'\b(if|elif|else|for|while|except|with|assert|and|or|case)\b'
    ),
    'dart': re.compile(
        r'\b(if|else|for|while|do|switch|case|catch|when|&&|\|\|)\b'
    ),
    'javascript': re.compile(
        r'\b(if|else|for|while|do|switch|case|catch|&&|\|\||\?)\b'
    ),
    'go': re.compile(
        r'\b(if|else|for|switch|case|select|&&|\|\|)\b'
    ),
    'java': re.compile(
        r'\b(if|else|for|while|do|switch|case|catch|&&|\|\||\?)\b'
    ),
    'rust': re.compile(
        r'\b(if|else|for|while|loop|match|&&|\|\||\?)\b'
    ),
    'kotlin': re.compile(
        r'\b(if|else|for|while|do|when|catch|&&|\|\|)\b'
    ),
    'ruby': re.compile(
        r'\b(if|elsif|else|unless|while|until|for|rescue|case|when|&&|\|\|)\b'
    ),
    'swift': re.compile(
        r'\b(if|else|guard|for|while|repeat|switch|case|catch|&&|\|\|)\b'
    ),
}

NESTING_OPEN = re.compile(r'[{([]|\bdo\b|\bthen\b|\bbegin\b')
NESTING_CLOSE = re.compile(r'[})\]]|\bend\b')

SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    'dist', 'build', '.mypy_cache', '.pub-cache', '.dart_tool',
    'Pods', '.gradle', 'target', 'ephemeral', 'generated',
    'macos', 'ios', 'android', 'windows', 'linux',
}

NOISE_NAMES = {
    'toJson', 'fromJson', 'toMap', 'fromMap', 'copyWith', 'toString',
    'hashCode', 'equals', 'build', 'createState', 'initState', 'dispose',
    'setState', 'didChangeDependencies', 'didUpdateWidget',
}

EXT_TO_LANG = {
    '.py': 'python', '.dart': 'dart',
    '.js': 'javascript', '.ts': 'javascript', '.jsx': 'javascript', '.tsx': 'javascript',
    '.go': 'go', '.java': 'java', '.rs': 'rust',
    '.kt': 'kotlin', '.kts': 'kotlin', '.rb': 'ruby', '.swift': 'swift',
}


def measure_complexity(filepath: str, func_name: str, func_line: int, language: str) -> ComplexityResult:
    """Measure complexity of a function by analyzing its source lines."""
    try:
        all_lines = Path(filepath).read_text(encoding='utf-8', errors='replace').splitlines()
        total_lines = len(all_lines)

        # Find function start
        start = max(0, func_line - 1)

        # Find function end by tracking braces/indentation
        end = start
        brace_count = 0
        found_open = False
        base_indent = len(all_lines[start]) - len(all_lines[start].lstrip()) if start < total_lines else 0

        if language == 'python':
            # Python: use indentation
            for i in range(start + 1, min(start + 500, total_lines)):
                line = all_lines[i]
                if not line.strip():
                    continue
                indent = len(line) - len(line.lstrip())
                if indent <= base_indent and line.strip():
                    end = i - 1
                    break
                end = i
        else:
            # Brace-based languages
            for i in range(start, min(start + 500, total_lines)):
                line = all_lines[i]
                brace_count += line.count('{') - line.count('}')
                if brace_count > 0:
                    found_open = True
                if found_open and brace_count <= 0:
                    end = i
                    break
                end = i

        func_lines = all_lines[start:end + 1]
        func_text = '\n'.join(func_lines)
        line_count = len(func_lines)

        # Count branches (cyclomatic complexity)
        pattern = BRANCH_PATTERNS.get(language, BRANCH_PATTERNS['javascript'])
        branches = len(pattern.findall(func_text))

        # Cyclomatic complexity = branches + 1
        cyclomatic = branches + 1

        # Max nesting depth
        max_depth = 0
        current_depth = 0
        for line in func_lines:
            opens = len(NESTING_OPEN.findall(line))
            closes = len(NESTING_CLOSE.findall(line))
            current_depth += opens - closes
            max_depth = max(max_depth, current_depth)

        # Combined score (weighted)
        score = cyclomatic + (line_count // 10) + (max_depth * 2)

        # Label
        if score >= 30:
            label = "Very Complex"
        elif score >= 15:
            label = "Complex"
        elif score >= 8:
            label = "Moderate"
        else:
            label = "Simple"

        return ComplexityResult(
            name=func_name, file=filepath, line=func_line,
            language=language, score=score, lines=line_count,
            nesting=max_depth, branches=branches, label=label
        )
    except Exception:
        return ComplexityResult(
            name=func_name, file=filepath, line=func_line,
            language=language, score=0, lines=0,
            nesting=0, branches=0, label="Simple"
        )


def label_color(label: str) -> str:
    return {
        'Very Complex': 'red',
        'Complex': 'yellow',
        'Moderate': 'cyan',
        'Simple': 'green',
    }.get(label, 'white')


def build_complexity_html(results: list, project: str, total_fns: int) -> str:
    rows_html = ''
    for r in results[:200]:
        rel = os.path.relpath(r.file, project)
        color = {'Very Complex':'#E24B4A','Complex':'#EF9F27','Moderate':'#74b9ff','Simple':'#4a9e6b'}.get(r.label,'#888')
        bar_w = min(100, r.score * 2)
        rows_html += f'''<tr onclick="selectRow(this,'{rel.replace("'","\\'")}','{r.name}',{r.score},{r.lines},{r.nesting},{r.branches},'{r.label}','{color}')">
          <td><div style="display:flex;align-items:center;gap:8px">
            <div style="width:80px;height:5px;background:#2a2a24;border-radius:3px;overflow:hidden">
              <div style="width:{bar_w}%;height:5px;background:{color};border-radius:3px"></div>
            </div>
            <span style="font-family:'DM Mono',monospace;font-size:12px;color:{color}">{r.score}</span>
          </div></td>
          <td style="font-family:'DM Mono',monospace;font-size:12px;color:#e8e4dc">{r.name}</td>
          <td style="font-size:11px;color:#6b6b5f;font-family:monospace">{rel}:{r.line}</td>
          <td><span style="font-size:10px;padding:2px 8px;border-radius:99px;background:{color}22;color:{color};border:1px solid {color}44">{r.label}</span></td>
          <td style="font-size:12px;color:#6b6b5f;text-align:center">{r.lines}</td>
          <td style="font-size:12px;color:#6b6b5f;text-align:center">{r.branches}</td>
          <td style="font-size:12px;color:#6b6b5f;text-align:center">{r.nesting}</td>
        </tr>'''

    very = sum(1 for r in results if r.label == 'Very Complex')
    comp = sum(1 for r in results if r.label == 'Complex')
    mod  = sum(1 for r in results if r.label == 'Moderate')
    simp = sum(1 for r in results if r.label == 'Simple')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complexity Report — {Path(project).name}</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Mono:wght@400;500&family=Syne:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box;margin:0;padding:0; }}
body {{ background:#0a0a08;color:#e8e4dc;font-family:'Syne',sans-serif;display:flex;flex-direction:column;height:100vh;overflow:hidden; }}
.topbar {{ background:#111110;border-bottom:1px solid #2a2a24;padding:.875rem 1.5rem;display:flex;align-items:center;gap:1rem;flex-shrink:0; }}
.logo {{ font-family:'Instrument Serif',serif;font-size:15px;color:#c9a84c;font-style:italic; }}
.proj {{ font-size:12px;color:#6b6b5f;margin-left:auto; }}
.stats {{ display:flex;gap:1.5rem;padding:.75rem 1.5rem;background:#111110;border-bottom:1px solid #2a2a24;flex-shrink:0;flex-wrap:wrap; }}
.stat {{ display:flex;align-items:center;gap:8px;font-size:13px; }}
.stat-n {{ font-family:'Instrument Serif',serif;font-size:22px; }}
.controls {{ display:flex;gap:8px;padding:.75rem 1.5rem;background:#111110;border-bottom:1px solid #2a2a24;flex-shrink:0;flex-wrap:wrap; }}
button {{ font-size:12px;padding:5px 12px;border-radius:6px;border:1px solid #2a2a24;background:transparent;color:#6b6b5f;cursor:pointer;font-family:'Syne',sans-serif; }}
button:hover,button.on {{ background:#c9a84c;color:#0a0a08;border-color:#c9a84c;font-weight:600; }}
input.search {{ font-size:12px;padding:5px 12px;border-radius:6px;border:1px solid #2a2a24;background:#1a1a17;color:#e8e4dc;outline:none;width:200px; }}
.main {{ display:flex;flex:1;min-height:0; }}
.table-wrap {{ flex:1;overflow-y:auto; }}
table {{ width:100%;border-collapse:collapse; }}
thead th {{ padding:8px 12px;text-align:left;font-size:11px;color:#6b6b5f;font-weight:600;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #2a2a24;position:sticky;top:0;background:#111110; }}
tbody tr {{ border-bottom:1px solid #1a1a17;cursor:pointer;transition:background .1s; }}
tbody tr:hover,tbody tr.sel {{ background:#1a1a17; }}
td {{ padding:8px 12px; }}
.detail {{ width:280px;flex-shrink:0;background:#111110;border-left:1px solid #2a2a24;padding:1.25rem;overflow-y:auto; }}
.d-placeholder {{ font-size:13px;color:#4a4a40;font-style:italic;text-align:center;margin-top:2rem; }}
.d-title {{ font-size:14px;font-weight:500;color:#e8e4dc;font-family:monospace;word-break:break-all;margin-bottom:4px; }}
.d-file {{ font-size:11px;color:#6b6b5f;margin-bottom:1rem; }}
.d-score {{ font-family:'Instrument Serif',serif;font-size:48px;line-height:1;margin-bottom:4px; }}
.d-label {{ font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin-bottom:1rem; }}
.d-bar {{ height:6px;background:#2a2a24;border-radius:3px;overflow:hidden;margin-bottom:1.5rem; }}
.d-bar-fill {{ height:6px;border-radius:3px;transition:width .5s; }}
.d-row {{ display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1a1a17;font-size:13px; }}
.d-row:last-child {{ border-bottom:none; }}
.d-key {{ color:#6b6b5f; }} .d-val {{ color:#e8e4dc;font-family:'DM Mono',monospace; }}
.d-tip {{ margin-top:1rem;padding:10px 12px;font-size:12px;color:#6b6b5f;line-height:1.6;border-left:3px solid #c9a84c;background:#1a1a17; }}
::-webkit-scrollbar {{ width:4px; }} ::-webkit-scrollbar-track {{ background:#111110; }} ::-webkit-scrollbar-thumb {{ background:#2a2a24; }}
</style>
</head>
<body>
<div class="topbar">
  <span class="logo">☠ archaeologist-complexity</span>
  <span style="color:#2a2a24">|</span>
  <span style="font-size:12px;color:#74b9ff">{Path(project).name}</span>
  <span class="proj">{project}</span>
</div>
<div class="stats">
  <div class="stat"><span class="stat-n" style="color:#e8e4dc">{total_fns}</span><span>total functions</span></div>
  <div class="stat"><span class="stat-n" style="color:#E24B4A">{very}</span><span>very complex</span></div>
  <div class="stat"><span class="stat-n" style="color:#EF9F27">{comp}</span><span>complex</span></div>
  <div class="stat"><span class="stat-n" style="color:#74b9ff">{mod}</span><span>moderate</span></div>
  <div class="stat"><span class="stat-n" style="color:#4a9e6b">{simp}</span><span>simple</span></div>
</div>
<div class="controls">
  <button class="on" onclick="filterLabel('all',this)">All</button>
  <button onclick="filterLabel('Very Complex',this)">Very Complex</button>
  <button onclick="filterLabel('Complex',this)">Complex</button>
  <button onclick="filterLabel('Moderate',this)">Moderate</button>
  <input class="search" type="text" placeholder="Search function or file..." oninput="doSearch(this.value)">
</div>
<div class="main">
  <div class="table-wrap">
    <table>
      <thead><tr><th>Score</th><th>Function</th><th>File</th><th>Label</th><th style="text-align:center">Lines</th><th style="text-align:center">Branches</th><th style="text-align:center">Nesting</th></tr></thead>
      <tbody id="tbody">{rows_html}</tbody>
    </table>
  </div>
  <div class="detail" id="detail"><div class="d-placeholder">Click any row<br>to see details</div></div>
</div>
<script>
let currentLabel='all', currentSearch='';
const allRows = Array.from(document.querySelectorAll('tbody tr'));

function filterLabel(label, btn) {{
  currentLabel = label;
  document.querySelectorAll('.controls button').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  applyFilters();
}}
function doSearch(q) {{ currentSearch=q.toLowerCase(); applyFilters(); }}
function applyFilters() {{
  allRows.forEach(row => {{
    const text = row.textContent.toLowerCase();
    const labelCell = row.querySelector('span');
    const label = labelCell ? labelCell.textContent.trim() : '';
    const matchLabel = currentLabel==='all' || label===currentLabel;
    const matchSearch = !currentSearch || text.includes(currentSearch);
    row.style.display = matchLabel && matchSearch ? '' : 'none';
  }});
}}
function selectRow(row, file, name, score, lines, branches, nesting, label, color) {{
  document.querySelectorAll('tbody tr').forEach(r=>r.classList.remove('sel'));
  row.classList.add('sel');
  const tips = {{
    'Very Complex': 'This function is very hard to test and maintain. Consider breaking it into smaller functions.',
    'Complex': 'High number of branches or nesting. Good candidate for refactoring.',
    'Moderate': 'Getting complex. Worth keeping an eye on as it grows.',
    'Simple': 'Well structured. No action needed.',
  }};
  document.getElementById('detail').innerHTML = `
    <div class="d-title">${{name}}</div>
    <div class="d-file">${{file}}</div>
    <div class="d-score" style="color:${{color}}">${{score}}</div>
    <div class="d-label" style="color:${{color}}">${{label}}</div>
    <div class="d-bar"><div class="d-bar-fill" style="width:${{Math.min(100,score*2)}}%;background:${{color}}"></div></div>
    <div class="d-row"><span class="d-key">Lines</span><span class="d-val">${{lines}}</span></div>
    <div class="d-row"><span class="d-key">Decision branches</span><span class="d-val">${{branches}}</span></div>
    <div class="d-row"><span class="d-key">Max nesting depth</span><span class="d-val">${{nesting}}</span></div>
    <div class="d-row"><span class="d-key">Cyclomatic complexity</span><span class="d-val">${{branches+1}}</span></div>
    <div class="d-tip">${{tips[label]||''}}</div>
  `;
}}
</script>
</body>
</html>"""


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--limit", default=50, help="Max results to show in terminal")
@click.option("--min-score", default=8, help="Minimum complexity score to show")
@click.option("--html", "open_html", is_flag=True, help="Open results as HTML in browser")
@click.option("--output", default=None, help="Save HTML to file")
@click.option("--lang", default=None, help="Filter by language")
def cli(path, limit, min_score, open_html, output, lang):
    """
    Score the complexity of every function in your codebase.

    Examples:

      archaeologist-complexity ./my-project

      archaeologist-complexity ./my-project --html

      archaeologist-complexity ./my-project --min-score 15

      archaeologist-complexity ./my-project --lang dart
    """
    abs_path = os.path.abspath(path)

    console.print(Panel.fit(
        f"[bold]☠ archaeologist-complexity[/bold]\n"
        f"[dim]Scanning [cyan]{abs_path}[/cyan][/dim]",
        border_style="dim"
    ))

    with console.status("[dim]Parsing files...[/dim]", spinner="dots"):
        scan_result = scan_directory(abs_path)

    total_fns = sum(len(v) for v in scan_result.definitions.values())
    console.print(f"[dim]  Found {total_fns} functions across {len(scan_result.calls)} files[/dim]\n")

    results = []
    with console.status("[dim]Measuring complexity...[/dim]", spinner="dots"):
        for name, defs in scan_result.definitions.items():
            if name in NOISE_NAMES:
                continue
            for d in defs:
                if d.is_test or d.is_entry_point:
                    continue
                if lang and d.language != lang:
                    continue
                # Skip platform files
                rel = os.path.relpath(d.file, abs_path)
                if any(p in rel for p in ['macos/', 'ios/', 'android/', 'windows/', 'scripts/', '.g.dart']):
                    continue
                r = measure_complexity(d.file, d.name, d.line, d.language)
                if r.score >= min_score:
                    results.append(r)

    results.sort(key=lambda x: x.score, reverse=True)

    if not results:
        console.print("[green]No complex functions found above the threshold.[/green]\n")
        return

    very = sum(1 for r in results if r.label == 'Very Complex')
    comp = sum(1 for r in results if r.label == 'Complex')
    mod  = sum(1 for r in results if r.label == 'Moderate')

    console.print(
        f"  [red]{very}[/red] very complex  "
        f"[yellow]{comp}[/yellow] complex  "
        f"[cyan]{mod}[/cyan] moderate\n"
    )

    table = Table(box=box.SIMPLE, show_header=True, header_style="dim",
                  show_edge=False, pad_edge=False)
    table.add_column("Score", width=8)
    table.add_column("Function", style="cyan", max_width=28)
    table.add_column("File", style="dim", max_width=42)
    table.add_column("Label", width=14)
    table.add_column("Lines", width=6)
    table.add_column("Branches", width=9)

    for r in results[:limit]:
        rel = os.path.relpath(r.file, abs_path)
        color = label_color(r.label)
        table.add_row(
            Text(str(r.score), style=color),
            r.name,
            f"{rel}:{r.line}",
            Text(r.label, style=color),
            str(r.lines),
            str(r.branches),
        )

    console.print(table)

    if len(results) > limit:
        console.print(f"[dim]  ...and {len(results)-limit} more. Use --limit to see more.[/dim]")

    console.print(f"\n[dim]  Tip: run with --html to open an interactive report in your browser[/dim]\n")

    if open_html or output:
        import webbrowser, tempfile
        html = build_complexity_html(results, abs_path, total_fns)
        if output:
            out = os.path.abspath(output)
            with open(out, 'w', encoding='utf-8') as f:
                f.write(html)
            console.print(f"[green]✓ Report saved:[/green] {out}")
            console.print(f"[dim]  Open with: open {out}[/dim]\n")
        else:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                             prefix='archaeologist_complexity_', encoding='utf-8') as f:
                f.write(html)
                tmp = f.name
            webbrowser.open(f'file://{tmp}')
            console.print(f"[green]✓ Complexity report opened in browser![/green]\n")


if __name__ == "__main__":
    cli()
