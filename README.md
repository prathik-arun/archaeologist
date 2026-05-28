# ☠ Archaeologist

**Codebase intelligence toolkit.** Five tools to understand, clean, and improve your codebase — all from one install.

```bash
pip3 install archaeologist
```

---

## Five Tools

### ☠ Unused Code Finder
Find functions nobody calls. Combines static analysis with git history into a confidence score. Auto-deletes on an isolated branch, runs your tests, and opens a GitHub PR.

```bash
deadcode ./my-project --explain
deadcode-report ./my-project --output report.html
deadcode-clean ./my-project --dry-run --min-confidence 85
deadcode-clean ./my-project --min-confidence 85
```

### ⬡ Codebase Graph
Interactive browser-based map of your architecture. Files grouped by folder, colored by health. See which files are clean, which have dead code, and which are completely unused.

```bash
archaeologist-graph ./my-project
archaeologist-graph ./my-project --output graph.html
```

### ◎ Change Impact Analyzer
Before changing any file, see what could break — every caller, every importer, test coverage, and a 0–100 blast radius score.

```bash
archaeologist-impact ./my-project user_service.dart
archaeologist-impact ./my-project user_service.dart --html
```

### ◈ Complexity Scorer
Scores every function on cyclomatic complexity — decision branches, nesting depth, and length. Ranks worst-first so you know what to refactor.

```bash
archaeologist-complexity ./my-project
archaeologist-complexity ./my-project --html --min-score 15
```

### ⧉ Duplicate Detector
Finds copy-paste code and near-identical functions. Detects same names in different files, exact body copies, and high-similarity implementations.

```bash
archaeologist-dupes ./my-project
archaeologist-dupes ./my-project --html
```

---

## Languages

**Production tested:** Python, Dart/Flutter, JavaScript, TypeScript

**Beta (may have false positives):** Go, Java, Kotlin, Ruby, Rust, Swift

---

## How the Unused Code Finder Works

1. **Parse** — Tree-sitter builds an AST for every file, extracting all function definitions and calls
2. **Git analysis** — Last commit date, author count, and commit frequency per file
3. **Score** — Five signals combine into a 0–100 confidence score
4. **Delete** — Functions removed by precise AST byte ranges — no broken syntax
5. **Test** — Your test suite runs automatically. If tests fail, everything rolls back
6. **PR** — A GitHub PR opens with full documentation of every change

### Confidence Score Signals

| Signal | Points | How it works |
|--------|--------|-------------|
| Call graph | 45 | Zero callers = full 45pts |
| Git age | 20 | 2+ years untouched = 20pts |
| Author count | 15 | Single author = 15pts |
| Recursive dead | 10 | All callers are also dead = 10pts |
| Commit count | 10 | Only 1–2 commits ever = 10pts |

### Verdicts

- **80–100: Safe to remove** — Multiple signals agree. Auto-clean targets these by default.
- **50–79: Review first** — Likely unused. Verify manually before removing.
- **40–49: Needs runtime data** — Static analysis uncertain. May be called via reflection.

---

## Git Flow (Auto-clean)

Your main branch is never touched. Everything happens on an isolated branch:

1. New branch created — e.g. `cleanup-2026-05-28`
2. Functions removed surgically by AST byte ranges
3. Your test suite runs automatically
4. If tests pass — branch committed
5. GitHub PR opened with full documentation
6. If tests fail — branch deleted, nothing changes

To review and merge:
```bash
git checkout cleanup-2026-05-28
git diff main cleanup-2026-05-28
git checkout main && git merge cleanup-2026-05-28
```

To roll back:
```bash
git branch -D cleanup-2026-05-28
```

---

## Requirements

- Python 3.11+
- Git (for git history analysis)
- GitHub token (optional, for auto-PR feature)

## License

MIT — free to use, modify, and distribute.
