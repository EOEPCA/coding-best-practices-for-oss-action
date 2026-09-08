import logging

from cachetools import cached
from pathlib import Path

from coding_best_practices_for_oss.config import (
    SKIP_DIR_NAMES,
    SKIP_FILE_NAMES,
    SKIP_FILE_EXTENSIONS,
    BINARY_FILE_EXTENSIONS,
    MAX_FILE_SIZE_FOR_SNIFF,
)


logger = logging.getLogger(__name__)

@cached(cache={})
def is_binary(path: Path) -> bool:
    """Heuristic: treat a file as binary if it contains a NUL byte, or fails UTF-8 decoding."""
    try:
        chunk = path.open("rb").read(MAX_FILE_SIZE_FOR_SNIFF)
    except (OSError, PermissionError):
        return True

    if b"\x00" in chunk:
        return True

    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True

    return False


def find_text_files(root: Path):
    """Yield all non-binary file paths under root, recursively, skipping known noise dirs."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if any(part in SKIP_FILE_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_FILE_EXTENSIONS:
            continue
        if path.suffix.lower() in BINARY_FILE_EXTENSIONS:
            continue
        if is_binary(path):
            logger.debug("Path is binary: %s", path)
            continue
        logger.debug("Path is text: %s", path)
        yield path

@cached(cache={})
def extract_head(path: Path, n_lines: int) -> str:
    """Return the first n_lines of a text file, best-effort."""
    lines = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= n_lines:
                    break
                lines.append(line.rstrip("\n"))
    except (OSError, PermissionError) as e:
        return f"<could not read file: {e}>"
    return "\n".join(lines)
