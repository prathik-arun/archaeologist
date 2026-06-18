# ☠ Archaeologist

**Codebase intelligence toolkit.** Five tools to understand, clean, and improve your codebase — all from one install.

```bash
pip3 install archaeologist
```

> Tested on 44 open source projects across 9 languages — zero false positives at 80%+ confidence.

---

## GitHub Action — Automated Weekly Reports

Add one file to your repo and get a codebase report every Monday as a GitHub Issue:

```yaml
# .github/workflows/archaeologist.yml
name: Archaeologist Codebase Report
on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday 9am
  workflow_dispatch:

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      issues: write
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: prathik-arun/archaeologist-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

**[→ View on GitHub Marketplace](https://github.com/marketplace/actions/archaeologist-codebase-intelligence)**

---

## Five CLI Tools

### ⬡ Codebase Graph
Interactive browser map of your architecture. Files grouped by folder, colored by health, connected by real call relationships.

```bash
archaeologist-graph ./my-project
archaeologist-graph ./my-project --output graph.html
```

---

### ◎ Change Impact Analyzer
Before changing any file, see its blast radius — every caller, every importer, test coverage, and a 0–100 risk score.

```bash
archaeologist-impact ./my-project --all --html
archaeologist-impact ./my-project [your-file] --html
```

---

### ◈ Complexity Scorer
Scores every function on cyclomatic complexity. Ranked worst-first.

```bash
archaeologist-complexity ./my-project --html
archaeologist-complexity ./my-project --min-score 15
```

---

### ⧉ Duplicate Detector
Finds copy-paste code and near-identical functions across your codebase.

```bash
archaeologist-dupes ./my-project --html
```

---

### ☠ Dead Code Finder
Finds unused functions using call graph + git history. Auto-deletes on an isolated branch, runs your tests, opens a PR.

```bash
deadcode ./my-project --explain
deadcode-report ./my-project
deadcode-clean ./my-project --dry-run --min-confidence 85
deadcode-clean ./my-project --min-confidence 85
```

---

## How Dead Code Scoring Works

Each flagged function gets a 0–100 confidence score:

| Signal | Points | How it works |
|--------|--------|-------------|
| Call graph | 45 | Zero inbound calls from non-test code |
| Git age | 20 | File untouched for 2+ years |
| Author count | 15 | Single author ever committed to this file |
| Recursive dead | 10 | All callers are themselves flagged |
| Commit count | 10 | Only 1–2 total commits ever |

---

## Languages

| Language | Status |
|----------|--------|
| Python | ✅ Production tested |
| Dart / Flutter | ✅ Production tested |
| JavaScript | ✅ Production tested |
| TypeScript | ✅ Production tested |
| Go | β Beta |
| Java | β Beta |
| Kotlin | β Beta |
| Ruby | β Beta |
| Rust | β Beta |
| Swift | β Beta |

---

## Tested On

Flask · Django · FastAPI · Requests · Scrapy · Rails · Sinatra · Express · Axios · Vue · Zod · Socket.io · Gin · Fiber · Zap · JUnit5 · Retrofit · RxKotlin · Alamofire · Moya · Vapor · Actix · Serde · and more.

---

## Requirements

- Python 3.11+
- Git (for git history analysis)
- Mac or Linux (Windows support coming soon)

## License

MIT — free to use, modify, and distribute.

Website: https://prathik-arun.github.io/archaeologist
GitHub Action: https://github.com/marketplace/actions/archaeologist-codebase-intelligence
