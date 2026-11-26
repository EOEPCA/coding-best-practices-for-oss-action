import subprocess
from dataclasses import dataclass
from pathlib import Path

from coding_best_practices_for_oss.utils.log_tools import getLogger


logger = getLogger(__name__)

# Hash reported by "git blame" for the lines that are not committed yet
UNCOMMITTED = "0" * 40


class GitError(Exception):
    """A git command failed."""


@dataclass
class BlameLine:
    commit: str  # full hash, UNCOMMITTED for local changes
    author_time: int  # Unix timestamp of the authoring of the commit

    @property
    def is_committed(self) -> bool:
        return self.commit != UNCOMMITTED


def _git(cwd: str | Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False,
        )
    except OSError as e:
        raise GitError(f"git could not be executed: {e}") from e
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {args[0]} failed with code {result.returncode}")
    return result.stdout


def is_git_work_tree(path: str | Path) -> bool:
    """Whether `path` is inside a git working tree."""
    try:
        return _git(path, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except GitError:
        return False


def is_shallow_repository(path: str | Path) -> bool:
    """Whether the repository containing `path` is a shallow clone (partial history)."""
    return _git(path, "rev-parse", "--is-shallow-repository").strip() == "true"


def tracked_files(path: str | Path) -> set[str]:
    """Paths of the files tracked by git under `path`, relative to `path` (POSIX separators)."""
    output = _git(path, "ls-files", "-z", "--", ".")
    return {name for name in output.split("\0") if name}


def blame(path: str | Path, relative_file: str) -> dict[int, BlameLine]:
    """Origin of every line of a file of the working tree, keyed by line number (1-based).

    Whitespace changes are ignored and lines moved or copied from other files are
    followed (-w -M -C), so that reformatting or moving code does not reset the dates.

    Raises:
        GitError: if the file is not tracked, or git fails.
    """
    output = _git(path, "blame", "-w", "-M", "-C", "--line-porcelain", "--", relative_file)
    lines: dict[int, BlameLine] = {}
    commit, final_line, author_time = None, None, 0
    for line in output.splitlines():
        if line.startswith("\t"):
            # Content line: closes the current entry
            if commit is not None and final_line is not None:
                lines[final_line] = BlameLine(commit, author_time)
            commit, final_line, author_time = None, None, 0
        elif commit is None:
            # Header: <commit> <original line> <final line> [<group size>]
            parts = line.split()
            commit, final_line = parts[0], int(parts[2])
        elif line.startswith("author-time "):
            author_time = int(line.split()[1])
    return lines
