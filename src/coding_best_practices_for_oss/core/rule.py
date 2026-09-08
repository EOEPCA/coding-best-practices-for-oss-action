# Rule base class + auto-registration
# Each rule is a small, self-contained class implementing a common interface
from abc import ABC, abstractmethod

from coding_best_practices_for_oss.core.context import RuleContext, matches_patterns
from coding_best_practices_for_oss.core.issue import Impact, Issue, IssueType
from coding_best_practices_for_oss.config import HELP_BASE_URL

# A rule either looks at the project as a whole (is the README there?) or at
# one file at a time (does this module call eval?). The runner walks the files
# once and only hands them to the file scoped rules that declared interest.
PROJECT_SCOPE = "project"
FILE_SCOPE = "file"


class Rule(ABC):
    """Base class of every check.

    Class attributes describe the rule in the report; `check()` does the work.
    Everything a rule needs comes from its `RuleContext`: a rule must not read
    the filesystem nor the environment directly, so it stays unit testable.
    """

    id: str = ""
    name: str = ""
    description: str = ""  # rule documentation, HTML allowed
    default_severity: str = "MINOR"
    category: str = ""  # "security", "maintainability", etc.
    #help_uri: str = ""  # Generated using the help base URL, the rule catelogue and ID
    dependencies = []  # The dependencies that can be enabled or disabled in config

    scope: str = PROJECT_SCOPE
    # For file scoped rules, the files this rule wants to see, as fnmatch
    # patterns on the project relative path or the file name ("*.py",
    # "docs/*.md"). Empty means every file.
    file_patterns: tuple[str, ...] = ()

    # Defaults used when building issues, overridable per issue.
    issue_type: IssueType = IssueType.CODE_SMELL
    impacts: tuple[Impact, ...] = ()
    effort_minutes: int | None = None

    # Clean code attribute reported to SonarQube, depending on the rule type:
    # - Consistency: FORMATTED, CONVENTIONAL, IDENTIFIABLE
    # - Intentionality: CLEAR, LOGICAL, COMPLETE, EFFICIENT
    # - Adaptability: FOCUSED, DISTINCT, MODULAR, TESTED
    # - Responsibility: LAWFUL, TRUSTWORTHY, RESPECTFUL
    clean_code_attribute: str = "CONVENTIONAL"

    @abstractmethod
    def check(self, context: RuleContext) -> list[Issue]:
        """Run this rule against the given context, return any issues found."""

    @property
    def is_file_scoped(self) -> bool:
        return self.scope == FILE_SCOPE

    @property
    def help_uri(self) -> str:
        return f"{HELP_BASE_URL}/rules/{self.category}/{self.id}"

    def applies_to(self, file) -> bool:
        """Whether this file scoped rule wants to check `file`."""
        return matches_patterns(file, self.file_patterns)

    def __str__(self) -> str:  # pragma: no cover - logging helper
        return f"{self.id} '{self.name or type(self).__name__}'"
