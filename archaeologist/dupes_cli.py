#!/usr/bin/env python3
"""archaeologist-dupes — duplicate code detector.

Finds functions that do the same thing written differently.
Uses a combination of structural fingerprinting and token similarity.
"""
import os
import re
import sys
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv',
    'dist', 'build', '.pub-cache', '.dart_tool', 'Pods',
    '.gradle', 'target', 'ephemeral', 'generated',
    'macos', 'ios', 'android', 'windows', 'linux',
}

NOISE_NAMES = {
    'toJson', 'fromJson', 'toMap', 'fromMap', 'copyWith',
    'toString', 'hashCode', 'equals', 'build', 'createState',
    'initState', 'dispose', 'setState',
}

EXT_TO_LANG = {
    '.py': 'python', '.dart': 'dart',
    '.js': 'javascript', '.ts': 'javascript',
    '.jsx': 'javascript', '.tsx': 'javascript',
    '.go': 'go', '.java': 'java', '.rs': 'rust',
    '.kt': 'kotlin', '.rb': 'ruby', '.swift': 'swift',
}

# Tokens to strip when comparing (variable names, string literals, numbers)
NORMALIZE_PATTERN = re.compile(
    r'"[^"]*"|\'[^\']*\'|`[^`]*`'  # string literals
    r'|\b\d+\.?\d*\b'               # numbers
    r'|\b[a-z_][a-zA-Z0-9_]{2,}\b' # identifiers (keep structure words)
)

STRUCTURE_WORDS = {
    # Control flow
    'if', 'else', 'elif', 'for', 'while', 'do', 'switch', 'case',
    'return', 'break', 'continue', 'throw', 'try', 'catch', 'finally',
    'async', 'await', 'yield', 'import', 'export', 'class', 'extends',
    # Dart/Flutter
    'final', 'const', 'var', 'void', 'null', 'true', 'false',
    # Python
    'def', 'lambda', 'pass', 'raise', 'with', 'as', 'from', 'in', 'not', 'and', 'or',
}


@dataclass
class FunctionSource:
    name: str
    file: str
    line: int
    language: str
    source: str          # raw source
    normalized: str      # normalized for comparison
    token_hash: str      # hash of normalized tokens
    length: int          # line count


@dataclass
class DuplicateGroup:
    similarity: int      # 0-100
    functions: list = field(default_factory=list)
    reason: str = ""


def extract_function_source(filepath: str, func_line: int, language: str) -> str:
    """Extract the source of a function starting at func_line."""
    try:
        lines = Path(filepath).read_text(encoding='utf-8', errors='replace').splitlines()
        start = max(0, func_line - 1)
        end = start

        if language == 'python':
            base_indent = len(lines[start]) - len(lines[start].lstrip()) if start < len(lines) else 0
            for i in range(start + 1, min(start + 300, len(lines))):
                line = lines[i]
                if not line.strip():
                    continue
                indent = len(line) - len(line.lstrip())
                if indent <= base_indent:
                    end = i - 1
                    break
                end = i
        else:
            brace_count = 0
            found_open = False
            for i in range(start, min(start + 300, len(lines))):
                brace_count += lines[i].count('{') - lines[i].count('}')
                if brace_count > 0:
                    found_open = True
                if found_open and brace_count <= 0:
                    end = i
                    break
                end = i

        return '\n'.join(lines[start:end + 1])
    except Exception:
        return ""


# Keep type names that add structural meaning
TYPE_WORDS = {
    # Dart types
    'String', 'int', 'double', 'bool', 'void', 'dynamic', 'Object',
    'List', 'Map', 'Set', 'Future', 'Stream', 'Widget', 'BuildContext',
    'State', 'StatelessWidget', 'StatefulWidget', 'Provider', 'Scaffold',
    # Python types
    'str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'set', 'None',
    'Optional', 'Union', 'Any', 'Dict', 'List', 'Tuple',
    # JS/TS types
    'string', 'number', 'boolean', 'undefined', 'null', 'Promise', 'Array',
    # Go types
    'error', 'interface', 'struct', 'chan', 'func',
    # Java/Kotlin types
    'Integer', 'Boolean', 'Long', 'Float', 'Double', 'ArrayList', 'HashMap',
}

def normalize_source(source: str) -> str:
    """Normalize source for comparison — strip variable names but keep types and structure."""
    # Remove comments
    source = re.sub(r'//[^\n]*', '', source)
    source = re.sub(r'#[^\n]*', '', source)
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    # Remove string literals and numbers
    source = re.sub(r'"[^"]*"', 'STR', source)
    source = re.sub(r"'[^']*'", 'STR', source)
    source = re.sub(r'\b\d+\.?\d*\b', 'NUM', source)

    lines = [line.strip() for line in source.splitlines() if line.strip()]

    normalized_lines = []
    for line in lines:
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|[{}()\[\];,.<>+\-*/=!&|?:]', line)
        normalized = ' '.join(
            t if (t in STRUCTURE_WORDS or t in TYPE_WORDS or not t[0].isalpha()) else 'VAR'
            for t in tokens
        )
        if normalized:
            normalized_lines.append(normalized)

    return '\n'.join(normalized_lines)


def token_similarity(a: str, b: str) -> int:
    """Calculate similarity between two normalized sources (0-100)."""
    if not a or not b:
        return 0

    tokens_a = set(a.split())
    tokens_b = set(b.split())

    if not tokens_a or not tokens_b:
        return 0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    jaccard = len(intersection) / len(union)

    # Also check length similarity
    len_ratio = min(len(a), len(b)) / max(len(a), len(b)) if max(len(a), len(b)) > 0 else 0

    return int((jaccard * 0.7 + len_ratio * 0.3) * 100)


def scan_functions(project_path: str, lang_filter: str = None) -> list[FunctionSource]:
    """Extract all functions with their source."""
    from archaeologist.scanner import scan_directory
    scan_result = scan_directory(project_path)

    functions = []
    for name, defs in scan_result.definitions.items():
        if name in NOISE_NAMES:
            continue
        for d in defs:
            if d.is_test or d.is_entry_point:
                continue
            if lang_filter and d.language != lang_filter:
                continue
            rel = os.path.relpath(d.file, project_path)
            if any(p in rel for p in ['macos/', 'ios/', 'android/', 'windows/', 'scripts/', '.g.dart']):
                continue

            source = extract_function_source(d.file, d.line, d.language)
            if len(source.strip()) < 30:  # skip trivial functions
                continue

            normalized = normalize_source(source)
            if len(normalized.strip()) < 10:
                continue

            token_hash = hashlib.md5(normalized.encode()).hexdigest()[:8]
            line_count = len(source.splitlines())

            functions.append(FunctionSource(
                name=d.name, file=d.file, line=d.line,
                language=d.language, source=source,
                normalized=normalized, token_hash=token_hash,
                length=line_count
            ))

    return functions


from difflib import SequenceMatcher


def _exact_body(source: str) -> str:
    """Strip whitespace for exact comparison."""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    # Remove first line (function signature differs)
    return '\n'.join(lines[1:]) if len(lines) > 1 else ''


def _body_sim(src_a: str, src_b: str) -> int:
    """Sequence-based similarity on cleaned source."""
    # Remove comments and string literals
    def clean(s):
        s = re.sub(r'//[^\n]*', '', s)
        s = re.sub(r'#[^\n]*', '', s)
        s = re.sub(r'"[^"]{0,30}"', '"_"', s)
        s = re.sub(r"'[^']{0,30}'", "'_'", s)
        s = re.sub(r'\b\d+\b', 'N', s)
        return ' '.join(s.split())
    
    ca, cb = clean(src_a), clean(src_b)
    if len(ca) < 60 or len(cb) < 60:
        return 0
    # Length ratio — functions must be similar size
    if min(len(ca), len(cb)) / max(len(ca), len(cb)) < 0.65:
        return 0
    return int(SequenceMatcher(None, ca, cb).ratio() * 100)


def find_duplicates(functions: list[FunctionSource],
                    min_similarity: int = 85) -> list[DuplicateGroup]:
    """Find duplicate functions using 3 clear signals."""
    groups = []
    used = set()

    # Signal 1: Same name in different files
    name_map = defaultdict(list)
    for fn in functions:
        name_map[fn.name].append(fn)

    for name, fns in name_map.items():
        # Deduplicate by file
        seen_files = set()
        unique = []
        for fn in fns:
            if fn.file not in seen_files:
                seen_files.add(fn.file)
                unique.append(fn)
        if len(unique) >= 2:
            # Check if bodies are actually similar (not just same name)
            sim = _body_sim(unique[0].source, unique[1].source) if len(unique) >= 2 else 60
            sim = max(sim, 60)  # same name is always worth flagging
            for fn in unique:
                used.add(id(fn))
            groups.append(DuplicateGroup(
                similarity=sim,
                functions=unique,
                reason=f"Same function name in {len(unique)} different files"
            ))

    # Signal 2: Exact copy-paste (identical body, different signature)
    body_map = defaultdict(list)
    for fn in functions:
        if id(fn) in used:
            continue
        if fn.length < 4:  # skip trivial functions
            continue
        body_key = _exact_body(fn.source)
        if len(body_key) > 20:
            body_map[body_key].append(fn)

    for body_key, fns in body_map.items():
        if len(fns) >= 2:
            for fn in fns:
                used.add(id(fn))
            groups.append(DuplicateGroup(
                similarity=100,
                functions=fns,
                reason="Exact copy-paste — identical function body in multiple places"
            ))

    # Signal 3: High body similarity (> min_similarity) for longer functions
    remaining = [fn for fn in functions if id(fn) not in used and fn.length >= 6]

    for i in range(len(remaining)):
        if id(remaining[i]) in used:
            continue
        group_members = [remaining[i]]

        for j in range(i + 1, min(i + 100, len(remaining))):  # limit comparisons
            if id(remaining[j]) in used:
                continue
            if remaining[i].language != remaining[j].language:
                continue
            sim = _body_sim(remaining[i].source, remaining[j].source)
            if sim >= min_similarity:
                group_members.append(remaining[j])

        if len(group_members) >= 2:
            for fn in group_members:
                used.add(id(fn))
            sim = _body_sim(group_members[0].source, group_members[1].source)
            groups.append(DuplicateGroup(
                similarity=sim,
                functions=group_members,
                reason=f"Near-identical implementation — {sim}% code similarity"
            ))

    groups.sort(key=lambda g: (-g.similarity, -len(g.functions)))
    return groups


def build_dupes_html(groups: list, project: str, total_fns: int) -> str:
    groups_html = ''
    for i, g in enumerate(groups[:100]):
        sim_color = '#E24B4A' if g.similarity >= 90 else '#EF9F27' if g.similarity >= 80 else '#74b9ff'
        fns_html = ''
        for fn in g.functions:
            rel = os.path.relpath(fn.file, project)
            fns_html += f'''<div class="fn-row">
              <div class="fn-name">{fn.name}</div>
              <div class="fn-file">{rel}:{fn.line}</div>
              <div class="fn-len">{fn.length} lines</div>
            </div>'''

        groups_html += f'''<div class="group" onclick="toggleGroup(this)">
          <div class="group-header">
            <div style="display:flex;align-items:center;gap:12px">
              <div class="sim-badge" style="background:{sim_color}22;color:{sim_color};border-color:{sim_color}44">{g.similarity}%</div>
              <div>
                <div class="group-title">{", ".join(fn.name for fn in g.functions[:3])}{"..." if len(g.functions)>3 else ""}</div>
                <div class="group-reason">{g.reason}</div>
              </div>
            </div>
            <div class="group-count">{len(g.functions)} copies</div>
          </div>
          <div class="group-body">{fns_html}</div>
        </div>'''

    exact = sum(1 for g in groups if g.similarity >= 90)
    similar = sum(1 for g in groups if 70 <= g.similarity < 90)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Duplicate Code — {Path(project).name}</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Mono:wght@400;500&family=Syne:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box;margin:0;padding:0; }}
body {{ background:#0a0a08;color:#e8e4dc;font-family:'Syne',sans-serif;min-height:100vh; }}
.topbar {{ background:#111110;border-bottom:1px solid #2a2a24;padding:.875rem 1.5rem;display:flex;align-items:center;gap:1rem; }}
.logo {{ font-family:'Instrument Serif',serif;font-size:15px;color:#c9a84c;font-style:italic; }}
.stats {{ display:flex;gap:2rem;padding:1.25rem 1.5rem;background:#111110;border-bottom:1px solid #2a2a24;flex-wrap:wrap; }}
.stat {{ display:flex;align-items:center;gap:8px;font-size:13px; }}
.stat-n {{ font-family:'Instrument Serif',serif;font-size:24px; }}
.content {{ max-width:900px;margin:0 auto;padding:2rem 1.5rem; }}
.search-bar {{ display:flex;gap:8px;margin-bottom:1.5rem; }}
input.search {{ font-size:13px;padding:8px 14px;border-radius:6px;border:1px solid #2a2a24;background:#111110;color:#e8e4dc;outline:none;flex:1; }}
input.search:focus {{ border-color:#c9a84c; }}
.group {{ background:#111110;border:1px solid #2a2a24;margin-bottom:2px;overflow:hidden; }}
.group-header {{ padding:1rem 1.25rem;cursor:pointer;display:flex;align-items:center;justify-content:space-between; }}
.group-header:hover {{ background:#1a1a17; }}
.group-title {{ font-size:14px;font-weight:500;color:#e8e4dc;font-family:'DM Mono',monospace; }}
.group-reason {{ font-size:12px;color:#6b6b5f;margin-top:3px; }}
.group-count {{ font-size:12px;color:#6b6b5f;white-space:nowrap; }}
.group-body {{ display:none;border-top:1px solid #2a2a24; }}
.group.open .group-body {{ display:block; }}
.fn-row {{ display:grid;grid-template-columns:200px 1fr 80px;gap:1rem;padding:.875rem 1.25rem;border-bottom:1px solid #1a1a17;align-items:center; }}
.fn-row:last-child {{ border-bottom:none; }}
.fn-name {{ font-family:'DM Mono',monospace;font-size:13px;color:#c9a84c; }}
.fn-file {{ font-size:12px;color:#74b9ff;font-family:monospace; }}
.fn-len {{ font-size:11px;color:#6b6b5f;text-align:right; }}
.sim-badge {{ font-family:'DM Mono',monospace;font-size:11px;padding:3px 10px;border-radius:99px;border:1px solid;font-weight:500;flex-shrink:0; }}
.empty {{ text-align:center;padding:4rem;font-size:15px;color:#4a4a40;font-style:italic; }}
::-webkit-scrollbar {{ width:6px; }} ::-webkit-scrollbar-track {{ background:#111110; }} ::-webkit-scrollbar-thumb {{ background:#2a2a24; }}
</style>
</head>
<body>
<div class="topbar">
  <span class="logo">☠ archaeologist-dupes</span>
  <span style="color:#2a2a24">|</span>
  <span style="font-size:12px;color:#74b9ff">{Path(project).name}</span>
</div>
<div class="stats">
  <div class="stat"><span class="stat-n" style="color:#e8e4dc">{total_fns}</span><span>functions scanned</span></div>
  <div class="stat"><span class="stat-n" style="color:#E24B4A">{exact}</span><span>exact duplicates</span></div>
  <div class="stat"><span class="stat-n" style="color:#EF9F27">{similar}</span><span>similar functions</span></div>
  <div class="stat"><span class="stat-n" style="color:#c9a84c">{len(groups)}</span><span>duplicate groups</span></div>
</div>
<div class="content">
  <div class="search-bar">
    <input class="search" type="text" placeholder="Search by function name or file..." oninput="doSearch(this.value)">
  </div>
  <div id="groups">
    {groups_html if groups_html else '<div class="empty">No duplicates found above the similarity threshold.</div>'}
  </div>
</div>
<script>
function toggleGroup(el) {{ el.classList.toggle('open'); }}
function doSearch(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.group').forEach(g => {{
    g.style.display = !q || g.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--min-similarity", default=70, help="Minimum similarity % (default: 70)")
@click.option("--limit", default=20, help="Max groups to show in terminal")
@click.option("--html", "open_html", is_flag=True, help="Open results as HTML in browser")
@click.option("--output", default=None, help="Save HTML to file")
@click.option("--lang", default=None, help="Filter by language")
def cli(path, min_similarity, limit, open_html, output, lang):
    """
    Find duplicate and near-duplicate functions in your codebase.

    Examples:

      archaeologist-dupes ./my-project

      archaeologist-dupes ./my-project --html

      archaeologist-dupes ./my-project --min-similarity 80

      archaeologist-dupes ./my-project --lang dart
    """
    abs_path = os.path.abspath(path)

    console.print(Panel.fit(
        f"[bold]☠ archaeologist-dupes[/bold]\n"
        f"[dim]Scanning [cyan]{abs_path}[/cyan][/dim]",
        border_style="dim"
    ))

    with console.status("[dim]Extracting function sources...[/dim]", spinner="dots"):
        functions = scan_functions(abs_path, lang)

    console.print(f"[dim]  Analyzing {len(functions)} functions for duplicates...[/dim]")

    with console.status("[dim]Comparing functions...[/dim]", spinner="dots"):
        groups = find_duplicates(functions, min_similarity)

    if not groups:
        console.print("\n[green]No duplicate functions found above the similarity threshold.[/green]\n")
        return

    exact = sum(1 for g in groups if g.similarity >= 90)
    similar = sum(1 for g in groups if 70 <= g.similarity < 90)

    console.print(f"\n  Found [red]{len(groups)}[/red] duplicate groups — "
                  f"[red]{exact}[/red] exact · [yellow]{similar}[/yellow] similar\n")

    for g in groups[:limit]:
        sim_color = "red" if g.similarity >= 90 else "yellow" if g.similarity >= 80 else "cyan"
        console.print(f"  [{sim_color}]{g.similarity}%[/{sim_color}] similarity — {g.reason}")
        for fn in g.functions:
            rel = os.path.relpath(fn.file, abs_path)
            console.print(f"    [cyan]{fn.name}[/cyan] [dim]{rel}:{fn.line} ({fn.length} lines)[/dim]")
        console.print()

    if len(groups) > limit:
        console.print(f"[dim]  ...and {len(groups)-limit} more groups. Use --html for the full report.[/dim]\n")

    console.print(f"[dim]  Tip: run with --html to open an interactive report[/dim]\n")

    if open_html or output:
        import webbrowser, tempfile
        html = build_dupes_html(groups, abs_path, len(functions))
        if output:
            out = os.path.abspath(output)
            with open(out, 'w', encoding='utf-8') as f:
                f.write(html)
            console.print(f"[green]✓ Report saved:[/green] {out}")
        else:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                             prefix='archaeologist_dupes_', encoding='utf-8') as f:
                f.write(html)
                tmp = f.name
            webbrowser.open(f'file://{tmp}')
            console.print(f"[green]✓ Duplicate report opened in browser![/green]\n")


if __name__ == "__main__":
    cli()
