# orchestrates: walk files -> run applicable rules -> collect issues
#
# The runner owns the whole checking pass and nothing else: it does not read
# the environment (the CLI passes the inputs in) and it does not write the
# report (the reporter turns a RunResult into JSON). One walk of the project
# feeds every file scoped rule, so each file is read and parsed at most once.
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from coding_best_practices_for_oss.core.context import DEFAULT_EXCLUDED_DIRS, RuleContext
from coding_best_practices_for_oss.core.issue import Issue
from coding_best_practices_for_oss.core.registry import instantiate_rules
from coding_best_practices_for_oss.core.rule import Rule

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Outcome of a run, everything the reporter and the CLI need."""

    issues: list[Issue] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)  # rules that actually ran
    disabled: list[str] = field(default_factory=list)  # rule ids, from the config
    errors: list[str] = field(default_factory=list)  # rules that raised
    files_checked: int = 0
    duration: float = 0.0

    @property
    def rules_by_id(self) -> dict[str, Rule]:
        return {rule.id: rule for rule in self.rules}

    @property
    def triggered_rules(self) -> list[Rule]:
        """Rules that reported at least one issue, in report order.

        Both report formats only describe the rules they reference.
        """
        reported = dict.fromkeys(issue.rule_id for issue in self.issues)
        by_id = self.rules_by_id
        return [by_id[rule_id] for rule_id in reported if rule_id in by_id]

    def summary(self) -> str:
        return (
            f"{len(self.issues)} issue(s) found by {len(self.rules)} rule(s) "
            f"on {self.files_checked} file(s) in {self.duration:.2f}s"
        )


class Runner:
    """Runs the rules against a project."""

    def __init__(
        self,
        target_path: str | Path,
        *,
        anchor_file: str = "coding-best-practices-issues.md",
        engine_id: str = "",
        config: Mapping[str, Any] | None = None,
        rules: Sequence[Rule] | None = None,
        excluded_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS,
        create_anchor_file: bool = True,
    ) -> None:
        self.context = RuleContext(
            target_path=target_path,
            anchor_file=anchor_file,
            engine_id=engine_id,
            config=config or {},
            excluded_dirs=excluded_dirs,
        )
        # None means "auto-discover", an explicit (possibly empty) sequence is
        # honoured as-is, which is what the tests use.
        self.rules = list(rules) if rules is not None else instantiate_rules()
        self.create_anchor_file = create_anchor_file

    @property
    def target_path(self) -> Path:
        return self.context.target_path

    def run(self) -> RunResult:
        """Check the project and collect the issues found."""
        if not self.target_path.is_dir():
            raise NotADirectoryError(f"{self.target_path} is not a valid directory.")

        started = time.perf_counter()
        result = RunResult()

        enabled = self._enabled_rules(result)
        result.rules = enabled
        project_rules = [rule for rule in enabled if not rule.is_file_scoped]
        file_rules = [rule for rule in enabled if rule.is_file_scoped]
        logger.info(
            "Checking %s with %d project rule(s) and %d file rule(s)",
            self.target_path,
            len(project_rules),
            len(file_rules),
        )

        for rule in project_rules:
            result.issues += self._check(rule, self.context.for_rule(rule), result)

        # Single walk: the file contents and ASTs cached in the context are
        # shared by every rule looking at the same file.
        for file in self.context.iter_files():
            result.files_checked += 1
            for rule in file_rules:
                if not rule.applies_to(file):
                    continue
                context = self.context.for_rule(rule).for_file(file)
                result.issues += self._check(rule, context, result)

        result.issues = _deduplicate(result.issues)
        result.duration = time.perf_counter() - started

        if self.create_anchor_file:
            self._ensure_anchor_file(result.issues)

        logger.info("Done: %s", result.summary())
        return result

    def _enabled_rules(self, result: RunResult) -> list[Rule]:
        """Rules kept after applying the `rules:`/`categories:` configuration."""
        enabled = []
        for rule in self.rules:
            if self.context.is_enabled(rule):
                enabled.append(rule)
            else:
                logger.info("%s is disabled by the configuration", rule)
                result.disabled.append(rule.id)
        return enabled

    def _check(self, rule: Rule, context: RuleContext, result: RunResult) -> list[Issue]:
        """Run one rule, keeping a failing rule from aborting the run."""
        try:
            issues = rule.check(context)
        except Exception as error:
            location = f" on {context.file}" if context.file else ""
            message = f"{rule} failed{location}: {error}"
            logger.error(message)
            logger.debug("Traceback for %s", rule, exc_info=True)
            result.errors.append(message)
            return []
        return self._validate(rule, issues, result)

    @staticmethod
    def _validate(rule: Rule, issues: Iterable[Issue] | None, result: RunResult) -> list[Issue]:
        """Accept None, a single issue or an iterable of issues."""
        if issues is None:
            return []
        if isinstance(issues, Issue):
            return [issues]

        validated = []
        for issue in issues:
            if isinstance(issue, Issue):
                validated.append(issue)
            else:
                # Typically a rule still returning the report dictionaries the
                # validator used before: it must build Issue objects instead.
                message = f"{rule} returned {type(issue).__name__}, expected an Issue."
                logger.error(message)
                result.errors.append(message)
        return validated

    def _ensure_anchor_file(self, issues: Sequence[Issue]) -> None:
        """Create the anchor file if issues point at it and it is missing.

        Issues with no file to point at (a missing README, a licensing
        problem...) are anchored on that file, which the report importers
        require to exist. Nothing is created when no issue needs it.
        """
        anchor = self.context.anchor_file
        if not any(issue.file_path == anchor for issue in issues):
            return
        path = self.context.path(anchor)
        if path.exists():
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            logger.info("Created default anchor file %s", path)
        except OSError as error:
            logger.warning("Could not create the anchor file %s: %s", path, error)


def run(target_path: str | Path, **kwargs: Any) -> RunResult:
    """Convenience wrapper around `Runner(...).run()`."""
    return Runner(target_path, **kwargs).run()


def _deduplicate(issues: Iterable[Issue]) -> list[Issue]:
    """Sort issues and drop exact duplicates, for reproducible reports."""
    unique: dict[tuple[Any, ...], Issue] = {}
    for issue in issues:
        unique.setdefault(issue.sort_key, issue)
    return [unique[key] for key in sorted(unique)]
