# ☠ Archaeologist

**Codebase intelligence toolkit.** Five tools to understand, clean, and improve your codebase — all from one install.

```bash
pip3 install archaeologist
```

> Tested on 44 open source projects across 9 languages — zero false positives at 80%+ confidence.

---

## Five Tools

### ⬡ Codebase Graph
Interactive browser map of your architecture. Files grouped by folder, colored by health, connected by real call relationships.

```bash
archaeologist-graph ./my-project
archaeologist-graph ./my-project --output graph.html   # save to share
```

**Colors:** 🟣 Entry point · 🟢 Clean · 🟡 Has dead code · 🔴 All unused

---

### ◎ Change Impact Analyzer
Before changing any file, see its blast radius — every caller, every importer, test coverage, and a 0–100 risk score.

```bash
archaeologist-impact ./my-project --all --html         # rank ALL files by blast radius
archaeologist-impact ./my-project [your-file] --html   # analyze a specific file
```

**Risk scores:** HIGH (70–100) · MEDIUM (40–69) · LOW (0–39)

---

### ◈ Complexity Scorer
Scores every function on cyclomatic complexity. Ranked worst-first.

```bash
archaeologist-complexity ./my-project --html
archaeologist-complexity ./my-project --min-score 15   # only show complex functions
```

**Labels:** Very Complex (30+) · Complex (15–29) · Moderate (8–14) · Simple (0–7)

---

### ⧉ Duplicate Detector
Finds copy-paste code and near-identical functions across your codebase.

```bash
archaeologist-dupes ./my-project --html
```

**Detects:** Same name in different files · Exact body copies · Near-identical bodies (85%+ similarity)

---

### ☠ Dead Code Finder
Finds unused functions using call graph + git history. Auto-deletes on an isolated branch, runs your tests, opens a PR.

```bash
deadcode ./my-project --explain
deadcode-report ./my-project                           # interactive HTML dashboard
deadcode-clean ./my-project --dry-run --min-confidence 85
deadcode-clean ./my-project --min-confidence 85
```

---

## How Dead Code Scoring Works

Static analysis alone has too many false positives. Archaeologist adds **git history** as a second signal.

Each flagged function gets a 0–100 confidence score:

| Signal | Points | How it works |
|--------|--------|-------------|
| Call graph | 45 | Zero inbound calls from non-test code |
| Git age | 20 | File untouched for 2+ years |
| Author count | 15 | Single author ever committed to this file |
| Recursive dead | 10 | All callers are themselves flagged |
| Commit count | 10 | Only 1–2 total commits ever |

**Verdicts:**
- **80–100: Safe to delete** — Multiple signals agree
- **50–79: Review first** — Likely unused, verify manually
- **40–49: Needs runtime data** — May be called via reflection or dependency injection

---

## Git Flow (Auto-clean)

Your main branch is **never touched**. Everything happens on an isolated branch:

1. New branch created — e.g. `cleanup-2026-06-01`
2. Functions removed by precise AST byte ranges — no broken syntax
3. Your test suite runs automatically
4. Tests pass → PR opened · Tests fail → branch deleted, nothing changes

```bash
# Review the changes
git checkout cleanup-2026-06-01
git diff main cleanup-2026-06-01

# Merge if happy
git checkout main && git merge cleanup-2026-06-01

# Roll back instantly
git branch -D cleanup-2026-06-01
```

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
- GitHub token (optional, for auto-PR feature)

## License

MIT — free to use, modify, and distribute.

Website: https://prathik-arun.github.io/archaeologist
