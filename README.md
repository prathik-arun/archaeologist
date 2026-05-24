# ☠ Dead Code Archaeologist

> Find unused functions. Delete them safely. Open a PR. All in one command.

Dead Code Archaeologist scans your codebase for dead functions using a multi-signal confidence engine — combining static call graph analysis with git history — then automatically deletes them on an isolated branch, runs your test suite, and opens a GitHub PR.

## Install

```bash
pip install deadcode-archaeologist
```

## Quick start

```bash
# Scan and see what's dead (no changes)
deadcode ./my-project --explain

# Generate a full interactive HTML report
deadcode-report ./my-project

# Preview what would be deleted (safe — no changes)
deadcode-clean ./my-project --dry-run

# Full auto-clean: delete → test → branch → PR
deadcode-clean ./my-project --min-confidence 85
```

## How it works

1. **AST scan** — tree-sitter parses every function definition and call across all supported languages
2. **Git analysis** — last commit date, author count, and commit frequency per file
3. **Confidence scoring** — 5 signals combine into a 0–100 score
4. **Surgical deletion** — functions removed by precise byte ranges, no broken syntax
5. **Tests run** — your test suite runs automatically before anything is committed
6. **PR opened** — a GitHub PR with full per-function documentation

## Supported languages

Python, Dart/Flutter, JavaScript, TypeScript, Go, Java, Rust, Kotlin, Ruby, Swift

## Commands

| Command | What it does |
|---------|-------------|
| `deadcode ./src --explain` | Scan and print ranked table |
| `deadcode ./src --json-output` | Output results as JSON |
| `deadcode-report ./src` | Generate HTML dashboard |
| `deadcode-clean ./src --dry-run` | Preview deletions, no changes |
| `deadcode-clean ./src --min-confidence 85` | Full auto-clean + PR |
| `deadcode-clean ./src --no-pr` | Clean without opening PR |
| `deadcode-clean ./src --lang dart` | Only clean Dart files |

## Confidence score

| Signal | Points |
|--------|--------|
| Zero callers in codebase | +45 |
| Git age (2+ years untouched) | +20 |
| Single author ever | +15 |
| Callers are themselves dead | +10 |
| Very few commits (≤2) | +10 |

## Verdicts

- **Safe to delete** (80–100) — multiple signals agree, auto-deleted by `deadcode-clean`
- **Review first** (50–79) — likely dead, verify manually before deleting
- **Needs runtime data** (40–49) — may be called dynamically, add coverage tracing first

## License

MIT
