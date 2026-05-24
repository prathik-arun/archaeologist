#!/usr/bin/env python3
"""Generate a browsable HTML report from dead code scan results."""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.scanner import scan_directory
from src.git_analyzer import analyze_git_history
from src.scorer import analyze

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dead Code Report — {project}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #1a1a1a; }}
  header {{ background: #1a1a1a; color: white; padding: 1.5rem 2rem; display: flex; align-items: center; gap: 2rem; flex-wrap: wrap; }}
  header h1 {{ font-size: 18px; font-weight: 500; }}
  .stats {{ display: flex; gap: 1.5rem; margin-left: auto; }}
  .stat {{ text-align: center; }}
  .stat-n {{ font-size: 22px; font-weight: 500; }}
  .stat-l {{ font-size: 11px; opacity: 0.6; margin-top: 2px; }}
  .stat-n.red {{ color: #ff6b6b; }}
  .stat-n.yellow {{ color: #ffd93d; }}
  .stat-n.blue {{ color: #74b9ff; }}
  .controls {{ background: white; border-bottom: 1px solid #e5e5e5; padding: 1rem 2rem; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }}
  .filter-btn {{ padding: 6px 14px; border-radius: 99px; border: 1px solid #ddd; background: white; cursor: pointer; font-size: 13px; color: #555; transition: all 0.15s; }}
  .filter-btn.active {{ background: #1a1a1a; color: white; border-color: #1a1a1a; }}
  .search {{ margin-left: auto; padding: 7px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 13px; width: 240px; }}
  .lang-filter {{ padding: 6px 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 13px; background: white; cursor: pointer; }}
  table {{ width: 100%; border-collapse: collapse; background: white; }}
  thead th {{ padding: 10px 16px; text-align: left; font-size: 12px; color: #888; font-weight: 500; border-bottom: 1px solid #e5e5e5; position: sticky; top: 0; background: white; z-index: 1; }}
  tbody tr {{ border-bottom: 1px solid #f0f0f0; transition: background 0.1s; }}
  tbody tr:hover {{ background: #fafafa; }}
  td {{ padding: 10px 16px; font-size: 13px; vertical-align: middle; }}
  .fn-name {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; color: #0066cc; }}
  .file-path {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; color: #888; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .conf-bar {{ display: flex; align-items: center; gap: 8px; }}
  .bar-track {{ width: 80px; height: 6px; background: #eee; border-radius: 3px; overflow: hidden; }}
  .bar-fill {{ height: 6px; border-radius: 3px; }}
  .bar-fill.high {{ background: #e74c3c; }}
  .bar-fill.mid {{ background: #f39c12; }}
  .bar-fill.low {{ background: #3498db; }}
  .conf-num {{ font-size: 12px; color: #888; min-width: 28px; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 99px; font-size: 11px; font-weight: 500; }}
  .badge.safe {{ background: #d4edda; color: #155724; }}
  .badge.review {{ background: #fff3cd; color: #856404; }}
  .badge.runtime {{ background: #cce5ff; color: #004085; }}
  .badge.lang {{ background: #f0f0f0; color: #555; }}
  .reasons {{ font-size: 11px; color: #999; margin-top: 3px; }}
  .empty {{ text-align: center; padding: 3rem; color: #999; font-size: 14px; }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  .table-wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Dead Code Archaeologist</h1>
    <div style="font-size:12px;opacity:0.5;margin-top:4px">{project}</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-n red">{safe}</div><div class="stat-l">safe to delete</div></div>
    <div class="stat"><div class="stat-n yellow">{review}</div><div class="stat-l">review first</div></div>
    <div class="stat"><div class="stat-n blue">{runtime}</div><div class="stat-l">needs runtime data</div></div>
    <div class="stat"><div class="stat-n">{total}</div><div class="stat-l">total functions</div></div>
  </div>
</header>

<div class="controls">
  <button class="filter-btn active" onclick="setFilter('all', this)">All ({all_count})</button>
  <button class="filter-btn" onclick="setFilter('safe', this)">Safe to delete ({safe})</button>
  <button class="filter-btn" onclick="setFilter('review', this)">Review first ({review})</button>
  <button class="filter-btn" onclick="setFilter('runtime', this)">Needs runtime ({runtime})</button>
  <select class="lang-filter" onchange="setLang(this.value)" id="lang-select">
    <option value="all">All languages</option>
    {lang_options}
  </select>
  <input class="search" type="text" placeholder="Search function or file..." oninput="setSearch(this.value)" id="search-box">
</div>

<div class="table-wrap">
<table id="results-table">
  <thead>
    <tr>
      <th>Confidence</th>
      <th>Function</th>
      <th>File</th>
      <th>Language</th>
      <th>Verdict</th>
      <th>Why</th>
    </tr>
  </thead>
  <tbody id="tbody">
  </tbody>
</table>
<div class="empty" id="empty-msg" style="display:none">No results match your filters.</div>
</div>

<script>
const rows = {rows_json};
let currentFilter = 'all';
let currentLang = 'all';
let currentSearch = '';

function barClass(score) {{
  if (score >= 80) return 'high';
  if (score >= 50) return 'mid';
  return 'low';
}}

function verdictKey(label) {{
  if (label === 'Safe to delete') return 'safe';
  if (label === 'Review first') return 'review';
  return 'runtime';
}}

function badgeClass(label) {{
  if (label === 'Safe to delete') return 'safe';
  if (label === 'Review first') return 'review';
  return 'runtime';
}}

function render() {{
  const tbody = document.getElementById('tbody');
  const filtered = rows.filter(r => {{
    if (currentFilter !== 'all' && verdictKey(r.label) !== currentFilter) return false;
    if (currentLang !== 'all' && r.language !== currentLang) return false;
    if (currentSearch) {{
      const q = currentSearch.toLowerCase();
      if (!r.name.toLowerCase().includes(q) && !r.file.toLowerCase().includes(q)) return false;
    }}
    return true;
  }});

  tbody.innerHTML = filtered.map(r => `
    <tr>
      <td>
        <div class="conf-bar">
          <div class="bar-track"><div class="bar-fill ${{barClass(r.confidence)}}" style="width:${{r.confidence}}%"></div></div>
          <span class="conf-num">${{r.confidence}}%</span>
        </div>
      </td>
      <td>
        <div class="fn-name">${{r.name}}</div>
      </td>
      <td>
        <div class="file-path" title="${{r.file}}">${{r.file}}:${{r.line}}</div>
      </td>
      <td><span class="badge lang">${{r.language}}</span></td>
      <td><span class="badge ${{badgeClass(r.label)}}">${{r.label}}</span></td>
      <td><div class="reasons">${{r.reasons.join(' &middot; ')}}</div></td>
    </tr>
  `).join('');

  document.getElementById('empty-msg').style.display = filtered.length === 0 ? 'block' : 'none';
  document.querySelector('.table-wrap table').style.display = filtered.length === 0 ? 'none' : '';
}}

function setFilter(f, btn) {{
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}}

function setLang(l) {{ currentLang = l; render(); }}
function setSearch(s) {{ currentSearch = s; render(); }}

render();
</script>
</body>
</html>"""


def generate_report(target_path: str, output_file: str = "dead_code_report.html", no_git: bool = False):
    print(f"Scanning {target_path}...")
    scan_result = scan_directory(target_path)
    total_funcs = sum(len(v) for v in scan_result.definitions.values())
    print(f"Found {total_funcs} functions across {len(scan_result.calls)} files")

    git_info_map = {}
    if not no_git:
        print("Analyzing git history...")
        git_info_map = analyze_git_history(target_path, list(scan_result.calls.keys()))

    print("Scoring...")
    candidates = analyze(scan_result, git_info_map, min_confidence=40)

    safe = [c for c in candidates if c.label == "Safe to delete"]
    review = [c for c in candidates if c.label == "Review first"]
    runtime = [c for c in candidates if c.label == "Needs runtime data"]

    langs = sorted({c.language for c in candidates})
    lang_options = "\n    ".join(f'<option value="{l}">{l.capitalize()}</option>' for l in langs)

    rows = []
    for c in candidates:
        rel_file = os.path.relpath(c.file, target_path)
        rows.append({
            "name": c.name,
            "file": rel_file,
            "line": c.line,
            "language": c.language,
            "confidence": c.confidence,
            "label": c.label,
            "reasons": c.reasons,
        })

    html = HTML_TEMPLATE.format(
        project=os.path.abspath(target_path),
        safe=len(safe),
        review=len(review),
        runtime=len(runtime),
        total=total_funcs,
        all_count=len(candidates),
        lang_options=lang_options,
        rows_json=json.dumps(rows),
    )

    with open(output_file, "w") as f:
        f.write(html)

    print(f"\nReport saved to: {os.path.abspath(output_file)}")
    print(f"Open it in your browser: open {os.path.abspath(output_file)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate HTML dead code report")
    parser.add_argument("path", help="Project path to scan")
    parser.add_argument("--output", default="dead_code_report.html", help="Output HTML file")
    parser.add_argument("--no-git", action="store_true", help="Skip git analysis")
    args = parser.parse_args()
    generate_report(args.path, args.output, args.no_git)
