import os
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


@dataclass
class FileGitInfo:
    last_commit_date: Optional[datetime]
    author_count: int
    commit_count: int
    days_since_touched: Optional[int]


def get_repo(path: str) -> Optional[object]:
    if not GIT_AVAILABLE:
        return None
    try:
        return git.Repo(path, search_parent_directories=True)
    except Exception:
        return None


def analyze_git_history(root_dir: str, filepaths: list[str]) -> dict[str, FileGitInfo]:
    results: dict[str, FileGitInfo] = {}
    repo = get_repo(root_dir)

    if repo is None:
        for fp in filepaths:
            results[fp] = FileGitInfo(None, 1, 0, None)
        return results

    repo_root = repo.working_dir
    now = datetime.now(timezone.utc)

    for filepath in filepaths:
        try:
            rel_path = os.path.relpath(filepath, repo_root)
            commits = list(repo.iter_commits(paths=rel_path, max_count=200))

            if not commits:
                results[filepath] = FileGitInfo(None, 1, 0, None)
                continue

            last_commit = commits[0]
            last_date = last_commit.committed_datetime
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone.utc)

            authors = {c.author.email for c in commits if c.author and c.author.email}
            days_ago = (now - last_date).days

            results[filepath] = FileGitInfo(
                last_commit_date=last_date,
                author_count=max(1, len(authors)),
                commit_count=len(commits),
                days_since_touched=days_ago,
            )

        except Exception:
            results[filepath] = FileGitInfo(None, 1, 0, None)

    return results
