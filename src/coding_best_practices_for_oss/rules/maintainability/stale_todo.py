# rules/maintainability/stale_todo.py
#
# TODO/FIXME comments must not stay in the code for too long.
# The age of each comment is the authoring date of the commit that last changed its line ("git blame").
#
import re
import time
from datetime import datetime, timezone

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.git_tools import (
    GitError, blame, is_git_work_tree, is_shallow_repository, tracked_files,
)
from coding_best_practices_for_oss.utils.log_tools import getLogger


RULE_ID = "MNT001"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Comments such as <code>TODO</code> or <code>FIXME</code> mark work left undone.
They must be resolved, or turned into tracked issues, instead of staying in the code for months.</p>
<p>The age of a comment is the date of the commit that last changed its line. The git history must be
complete: in GitHub Actions, use <code>actions/checkout</code> with <code>fetch-depth: 0</code>.</p>
"""

DEFAULT_MARKERS = ["TODO", "FIXME", "XXX", "HACK"]
DEFAULT_WARNING_THRESHOLD = 180  # days
DEFAULT_ERROR_THRESHOLD = 365  # days
DEFAULT_CRITICAL_THRESHOLD = None  # days
MAX_TEXT_LENGTH = 80

# Comment starters of the most common languages: # // /* * -- ; % <!-- REM
COMMENT_START = r"(?:#|//|/\*|\*|--|;|%|<!--|\bREM\b)"

SECONDS_PER_DAY = 86400


def marker_regex(markers: list[str]) -> re.Pattern:
    """Match a marker (case-sensitive, as a whole word, not quoted) placed in a comment."""
    names = "|".join(re.escape(m) for m in markers)
    return re.compile(rf"{COMMENT_START}.*?(?<![\"'`])\b({names})\b(?![\"'`])(.*)$")


class StaleTodoRule(Rule):
    id = RULE_ID
    name = "Stale TODO comments"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "maintainability"
    dependencies = ["git"]
    scope = PROJECT_SCOPE
    effort_minutes = 30
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.LOW),)
    clean_code_attribute = "COMPLETE"

    # Clock used to compute the ages, replaceable in tests
    now = staticmethod(time.time)

    @staticmethod
    def _find_markers(context, regex: re.Pattern, tracked: set[str]) -> dict[str, list[tuple[int, str, str]]]:
        """{relative path: [(line number, marker, text)]} for every tracked text file."""
        found = {}
        for file in context.iter_files():
            # Untracked files (logs, reports, new files) cannot hold stale comments
            if file.relative_path not in tracked or file.text is None:
                continue
            for number, line in enumerate(file.lines, start=1):
                match = regex.search(line)
                if match:
                    text = f"{match.group(1)}{match.group(2)}".strip().rstrip("*/->").strip()
                    if len(text) > MAX_TEXT_LENGTH:
                        text = text[: MAX_TEXT_LENGTH - 3] + "..."
                    found.setdefault(file.relative_path, []).append((number, match.group(1), text))
        return found

    @staticmethod
    def _threshold(context, key: str, default: int | None) -> int | None:
        """Threshold in days, or None if not used (null, "None", "", 0 or negative)."""
        value = context.rule_setting(key, default)
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in ("", "none", "null", "~"):
                return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            logger.warning("Invalid value for '%s': %r (number of days expected), using %s", key, value, default)
            return default
        return days if days > 0 else None

    @staticmethod
    def _severity(age_days: int, warning, error, critical) -> Severity | None:
        if critical and age_days >= critical:
            return Severity.CRITICAL
        if error and age_days >= error:
            return Severity.MAJOR
        if warning and age_days >= warning:
            return Severity.MINOR
        return None

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        markers = context.rule_setting("markers", DEFAULT_MARKERS)
        # A None (or 0) value means the corresponding severity is not used
        warning = self._threshold(context, "warning_threshold", DEFAULT_WARNING_THRESHOLD)
        error = self._threshold(context, "error_threshold", DEFAULT_ERROR_THRESHOLD)
        critical = self._threshold(context, "critical_threshold", DEFAULT_CRITICAL_THRESHOLD)

        root = context.path()
        if not is_git_work_tree(root):
            logger.warning("'%s' is not in a git repository: the TODO comments cannot be dated", context.display_path)
            return [
                context.issue(
                    "The age of the TODO comments cannot be checked: the project is not in a git repository.",
                    severity=Severity.INFO,
                )
            ]
        if is_shallow_repository(root):
            logger.warning("Shallow git clone: the TODO comments cannot be dated")
            return [
                context.issue(
                    "The age of the TODO comments cannot be checked: the git history is incomplete (shallow clone). "
                    "In GitHub Actions, use actions/checkout with 'fetch-depth: 0'.",
                    severity=Severity.INFO,
                )
            ]

        found = self._find_markers(context, marker_regex(markers), tracked_files(root))
        count = sum(len(v) for v in found.values())
        logger.info("Found %s %s comment(s) in %s file(s)", count, "/".join(markers), len(found))

        now = self.now()
        issues = []
        for relpath, entries in found.items():
            try:
                origins = blame(root, relpath)
            except GitError as e:
                logger.warning("Cannot get the history of %s (%s comment(s) not checked): %s", relpath, len(entries), e)
                continue
            for line, marker, text in entries:
                origin = origins.get(line)
                if origin is None:
                    logger.debug("⚠️ %s:%s: %s comment has no git history, skipped", relpath, line, marker)
                    continue
                if not origin.is_committed:
                    logger.debug("✅ %s:%s: %s comment is not committed yet (new)", relpath, line, marker)
                    continue
                age_days = int((now - origin.author_time) // SECONDS_PER_DAY)
                severity = self._severity(age_days, warning, error, critical)
                if severity is None:
                    logger.debug("✅ %s:%s: %s comment is %s days old", relpath, line, marker, age_days)
                    continue
                since = datetime.fromtimestamp(origin.author_time, tz=timezone.utc).strftime("%Y-%m-%d")
                logger.info("❌ %s:%s: %s comment is %s days old", relpath, line, marker, age_days)
                issues.append(
                    context.issue(
                        f"{marker} comment present for {age_days} days (since {since}, commit {origin.commit[:7]}): {text}",
                        file_path=relpath,
                        line=line,
                        severity=severity,
                    )
                )

        if issues:
            return issues
        logger.info("✅ No %s comment older than %s days", "/".join(markers), warning)
        # Return an info-level issue to inform the user about the test result
        return [
            context.issue(
                f"No {'/'.join(markers)} comment older than {warning} days ({count} found)",
                severity=Severity.INFO,
            )
        ]
