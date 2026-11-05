# rules/documentation/shell_script_comments.py
import re
from pathlib import Path

from coding_best_practices_for_oss.core.issue import Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.file_tools import find_shell_scripts
from coding_best_practices_for_oss.utils.log_tools import getLogger

RULE_ID = "DOC003"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Shell scripts should include a comment at the top (after an optional shebang)</p>
"""

SHEBANG_RE = re.compile(r"^#!.*")

FILE_PATTERNS = ["*.sh", "*.bash", "*.csh", "*.tcsh", "*.ash", "*.zsh", "*.ksh", "*.dash", "*.fish"]


def starts_with_shebang_then_comment(file_path: str | Path) -> bool:
    """
    Check whether a shell script starts with an optional shebang line,
    followed by blank lines, followed by at least one mandatory comment
    line. Anything after that (the actual script body) is not checked.

    Args:
        file_path (str | Path): Path to the script file.

    Returns:
        bool: True if the file matches: [shebang]? blank* comment+ ...
            False if there's no comment line before the first real
            statement (or the file is empty / has nothing but blanks
            with no comment at all).
    """
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    # Optional shebang — only recognized on line 1
    if lines and SHEBANG_RE.match(lines[0]):
        index = 1
    # Skip any blank lines
    while index < len(lines) and lines[index].strip() == "":
        index += 1
    # The next non-blank line must be a comment
    if index >= len(lines):
        return False  # nothing but shebang/blanks — no mandatory comment found
    return lines[index].strip().startswith("#")


class ShellScriptMissingTopCommentRule(Rule):
    id = RULE_ID
    name = "Shell Script Missing Top Comment"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "documentation"
    scope = PROJECT_SCOPE
    effort_minutes = 60
    impacts = (Impact(SoftwareQuality.RELIABILITY, ImpactSeverity.LOW),)

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        issues = []
        shell_script_found = False
        for filepath in find_shell_scripts(context.path()):
            shell_script_found = True
            relpath = context.relative(filepath)
            if starts_with_shebang_then_comment(filepath):
                logger.info("✅ Shell script includes a comment at the top: %s", relpath)
            else:
                logger.info("❌ Shell script does not include a comment at the top: %s", relpath)
                issues.extend(
                    [context.issue(
                        f"Shell script '{relpath}' does not include a comment at the top.",
                        #severity=Severity.MINOR, Use default severity
                        line=1,
                        column=1,
                        file_path=relpath,
                    )]
                )

        if not shell_script_found:
            logger.info("ℹ️ No shell scripts found in the analysed folders")
        return issues
