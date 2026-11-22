"""
Git operations for resume version control.
Wraps GitPython for init, commit, revert, and history.
"""

from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError

from src.utils.logger import logger


class GitError(Exception):
    """Raised when a Git operation fails."""


def init_repo(repo_dir: Path) -> Repo:
    """Initialize a Git repository if it doesn't exist, or return existing one."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    try:
        repo = Repo(repo_dir)
        if not repo.bare:
            logger.info("Git repo already exists: %s", repo_dir)
            return repo
    except Exception:
        pass

    # Init new repo
    repo = Repo.init(repo_dir)
    logger.info("Git repo initialized: %s", repo_dir)

    # Create .gitignore
    gitignore = repo_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*.aux\n*.log\n*.out\n*.pdf\n")

    return repo


def commit(repo_dir: Path, message: str) -> str:
    """
    Stage all changes and commit.
    Returns the commit hash.
    """
    repo: Optional[Repo] = None
    try:
        repo = Repo(repo_dir)
        if repo.bare:
            raise GitError(f"Repository is bare: {repo_dir}")

        # Stage all
        repo.git.add(A=True)

        # Only commit if there are changes
        if not repo.is_dirty(untracked_files=True):
            logger.info("No changes to commit in %s", repo_dir)
            return ""

        commit_obj = repo.index.commit(message)
        short_hash = repo.git.rev_parse(commit_obj.hexsha, short=7)
        logger.info("Git commit: %s — %s", short_hash, message)
        return short_hash

    except GitCommandError as e:
        raise GitError(f"Git commit failed: {e}") from e
    finally:
        if repo is not None:
            repo.close()


def revert_last(repo_dir: Path) -> str:
    """
    Revert the most recent commit (soft reset, keep files).
    Returns the hash that was reverted.
    """
    repo: Optional[Repo] = None
    try:
        repo = Repo(repo_dir)
        if repo.head.is_valid():
            old_hash = repo.git.rev_parse("HEAD", short=7)
            repo.head.reset("HEAD~1", index=True, working_tree=True)
            logger.info("Git revert: rolled back %s", old_hash)
            return old_hash
        return ""
    except GitCommandError as e:
        raise GitError(f"Git revert failed: {e}") from e
    finally:
        if repo is not None:
            repo.close()


def get_history(repo_dir: Path, max_count: int = 10) -> list[dict]:
    """Get recent commit history."""
    repo: Optional[Repo] = None
    try:
        repo = Repo(repo_dir)
        commits = []
        for c in repo.iter_commits(max_count=max_count):
            commits.append({
                "hash": repo.git.rev_parse(c.hexsha, short=7),
                "message": c.message.strip(),
                "date": c.committed_datetime.strftime("%Y-%m-%d %H:%M"),
            })
        return commits
    except Exception:
        return []
    finally:
        if repo is not None:
            repo.close()


def is_git_available() -> bool:
    """Check if git is available in the system PATH."""
    import subprocess
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False
