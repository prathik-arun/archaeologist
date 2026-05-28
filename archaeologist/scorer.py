from dataclasses import dataclass, field
from typing import Optional
from .scanner import FunctionDef, ScanResult
from .git_analyzer import FileGitInfo


@dataclass
class DeadCodeCandidate:
    name: str
    file: str
    line: int
    language: str
    confidence: int           # 0-100, higher = more likely dead
    label: str                # "Safe to delete" / "Review first" / "Needs runtime data"
    reasons: list[str]        # human-readable explanation
    callers_found: int
    days_since_touched: Optional[int]
    author_count: int
    is_test: bool
    decorators: list[str]


def score_candidate(
    func: FunctionDef,
    call_count: int,
    git_info: Optional[FileGitInfo],
    all_dead_files: set[str],
) -> int:
    score = 0

    # Signal 1: call graph reachability (0-45 pts)
    if call_count == 0:
        score += 45
    elif call_count == 1:
        score += 20
    elif call_count <= 3:
        score += 8

    # Signal 2: git age (0-20 pts)
    if git_info and git_info.days_since_touched is not None:
        days = git_info.days_since_touched
        if days > 730:    # 2+ years
            score += 20
        elif days > 365:  # 1-2 years
            score += 15
        elif days > 180:  # 6-12 months
            score += 10
        elif days > 90:   # 3-6 months
            score += 5

    # Signal 3: single author (0-15 pts)
    if git_info:
        if git_info.author_count == 1:
            score += 15
        elif git_info.author_count == 2:
            score += 7

    # Signal 4: test coverage absent — proxy: it's not in a test file (0-15 pts)
    if not func.is_test:
        score += 8
    # If very few commits, probably throwaway code
    if git_info and git_info.commit_count <= 2:
        score += 7

    # Signal 5: callers are themselves dead (0-10 pts)
    if func.file in all_dead_files and call_count > 0:
        score += 10

    # Penalty: private methods (starting with _ in Dart/Python) are often
    # called within the same file via callbacks — reduce confidence
    if func.name.startswith("_") and func.language in ("dart", "python"):
        score = max(0, score - 20)

    # Penalty: if function name contains common active-code patterns
    active_patterns = ("error", "exception", "callback", "listener", "handler",
                       "observer", "delegate", "route", "navigate", "screen")
    if any(p in func.name.lower() for p in active_patterns):
        score = max(0, score - 10)

    return min(score, 100)


def build_reasons(
    func: FunctionDef,
    call_count: int,
    git_info: Optional[FileGitInfo],
) -> list[str]:
    reasons = []

    if call_count == 0:
        reasons.append("No callers found in codebase")
    elif call_count == 1:
        reasons.append(f"Only 1 caller found")
    else:
        reasons.append(f"{call_count} callers found")

    if git_info and git_info.days_since_touched is not None:
        days = git_info.days_since_touched
        if days > 60:
            years = days // 365
            months = (days % 365) // 30
            if years > 0:
                reasons.append(f"Last touched {years}yr {months}mo ago")
            else:
                reasons.append(f"Last touched {months} months ago")
        else:
            reasons.append(f"Last touched {days} days ago")

        if git_info.author_count == 1:
            reasons.append("Only 1 author ever")
        else:
            reasons.append(f"{git_info.author_count} authors")

        if git_info.commit_count <= 2:
            reasons.append(f"Only {git_info.commit_count} commit(s)")

    if func.decorators:
        reasons.append(f"Decorated: @{', @'.join(func.decorators[:2])}")

    return reasons


def label_from_score(score: int, func: FunctionDef) -> str:
    if func.decorators:
        dec_set = {d.split(".")[-1].lower() for d in func.decorators}
        risky = {"route", "get", "post", "put", "delete", "patch", "task", "signal", "receiver"}
        if dec_set & risky:
            return "Needs runtime data"

    if score >= 80:
        return "Safe to delete"
    elif score >= 50:
        return "Review first"
    else:
        return "Needs runtime data"


def analyze(
    scan_result: ScanResult,
    git_info_map: dict[str, FileGitInfo],
    min_confidence: int = 40,
) -> list[DeadCodeCandidate]:
    candidates: list[DeadCodeCandidate] = []

    # Count how many times each function name is called across the whole codebase
    # Build a map: func_name -> set of files that define it
    defined_in: dict[str, set] = {}
    for name, defs in scan_result.definitions.items():
        for d in defs:
            defined_in.setdefault(name, set()).add(d.file)

    # Only count calls from files that don't define that function (exclude self-reference)
    call_counts: dict[str, int] = {}
    for calling_file, called_names in scan_result.calls.items():
        for name in called_names:
            # Skip qualified markers - these are tracking metadata not real calls
            if name.startswith("__qualified__"):
                continue
            # skip if this is the same file that defines the function
            if calling_file in defined_in.get(name, set()):
                continue
            call_counts[name] = call_counts.get(name, 0) + 1

    # Now apply qualification penalty: if a name only appears as X.name
    # (property/enum access) across all files, reduce its call count
    # because those aren't function calls to the function we defined
    for func_name in list(call_counts.keys()):
        qualified_key = f"__qualified__{func_name}"
        # Count how many files have ONLY qualified usage vs standalone usage
        standalone_count = 0
        qualified_only_count = 0
        for calling_file, called_names in scan_result.calls.items():
            if calling_file in defined_in.get(func_name, set()):
                continue
            has_standalone = func_name in called_names
            has_qualified = qualified_key in called_names
            if has_standalone:
                standalone_count += 1
            elif has_qualified:
                qualified_only_count += 1
        # If all usages are qualified (X.name pattern), they're likely
        # enum values or properties, not function calls
        if standalone_count == 0 and qualified_only_count > 0:
            call_counts[func_name] = 0

    # Files where every function in the file is uncalled — used for recursive dead scoring
    dead_files: set[str] = set()

    for name, defs in scan_result.definitions.items():
        for func in defs:
            if func.is_entry_point or func.is_test:
                continue
            count = call_counts.get(name, 0)
            if count == 0:
                dead_files.add(func.file)

    for name, defs in scan_result.definitions.items():
        for func in defs:
            if func.is_entry_point or func.is_test:
                continue

            call_count = call_counts.get(name, 0)
            git_info = git_info_map.get(func.file)

            score = score_candidate(func, call_count, git_info, dead_files)

            if score < min_confidence:
                continue

            reasons = build_reasons(func, call_count, git_info)
            lbl = label_from_score(score, func)

            candidates.append(DeadCodeCandidate(
                name=name,
                file=func.file,
                line=func.line,
                language=func.language,
                confidence=score,
                label=lbl,
                reasons=reasons,
                callers_found=call_count,
                days_since_touched=git_info.days_since_touched if git_info else None,
                author_count=git_info.author_count if git_info else 1,
                is_test=func.is_test,
                decorators=func.decorators,
            ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates
