# RuleContext: file content, AST, metadata passed to each rule
#
# Rules must not touch the filesystem (nor os.getenv) themselves: everything
# they need is reachable from the context they receive. That keeps rules trivial
# to unit test (build a context on a fixture folder) and lets the runner cache
# expensive work - reading a file, parsing an AST - across all rules.
#
# Two levels of context, sharing the same caches:
#   - RuleContext  : the project being checked (project scoped rules)
#   - FileContext  : one file of that project, exposed as `context.file`
from __future__ import annotations

import ast
import configparser
import fnmatch
import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Iterator, Mapping

from coding_best_practices_for_oss.core.issue import (
    Impact,
    Issue,
    IssueType,
    Location,
    Severity,
)

# Directories that are never worth walking into.
DEFAULT_EXCLUDED_DIRS: tuple[str, ...] = (
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".eggs",
    "*.egg-info",
    "build",
    "dist",
    "site-packages",
    ".idea",
    ".vscode",
)

# Files above this size are treated as non-text (no content, no AST).
MAX_TEXT_FILE_SIZE = 2 * 1024 * 1024


def matches_patterns(file: "FileContext", patterns: tuple[str, ...] | list[str]) -> bool:
    """Whether a file matches any fnmatch pattern, by path or by name.

    So that both "docs/*.md" (project relative path) and "*.py" (file name)
    behave as expected. No pattern means "every file".
    """
    if not patterns:
        return True
    return any(
        fnmatch.fnmatch(file.relative_path, pattern) or fnmatch.fnmatch(file.name, pattern)
        for pattern in patterns
    )


@dataclass
class FileContext:
    """One file of the checked project, with lazily loaded content and AST."""

    path: Path  # absolute path on disk
    relative_path: str  # relative to the project root, POSIX separators

    @cached_property
    def text(self) -> str | None:
        """File content, or None if it is binary, too large or unreadable."""
        try:
            if self.path.stat().st_size > MAX_TEXT_FILE_SIZE:
                return None
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    @cached_property
    def lines(self) -> list[str]:
        """Content split in lines, without line endings. Empty if not text."""
        return (self.text or "").splitlines()

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    @property
    def is_python(self) -> bool:
        return self.suffix in {".py", ".pyi"}

    @cached_property
    def _parsed(self) -> tuple[ast.Module | None, SyntaxError | None]:
        if not self.is_python or self.text is None:
            return None, None
        try:
            return ast.parse(self.text, filename=str(self.path)), None
        except SyntaxError as error:
            return None, error

    @property
    def ast(self) -> ast.Module | None:
        """Parsed module for Python files, None otherwise or on syntax error."""
        return self._parsed[0]

    @property
    def syntax_error(self) -> SyntaxError | None:
        """The syntax error met while parsing, if any (rules may report it)."""
        return self._parsed[1]

    def line(self, number: int) -> str:
        """1-based line access, empty string when out of range."""
        if 1 <= number <= len(self.lines):
            return self.lines[number - 1]
        return ""

    def location(
        self,
        message: str | None = None,
        *,
        node: ast.AST | None = None,
        line: int | None = None,
        end_line: int | None = None,
        column: int | None = None,
        end_column: int | None = None,
    ) -> Location:
        """Build a `Location` in this file, optionally from an AST node."""
        if node is not None:
            line = line if line is not None else getattr(node, "lineno", None)
            end_line = end_line if end_line is not None else getattr(node, "end_lineno", None)
            if column is None and getattr(node, "col_offset", None) is not None:
                column = node.col_offset + 1  # ast columns are 0-based
            if end_column is None and getattr(node, "end_col_offset", None) is not None:
                end_column = node.end_col_offset + 1
        return Location(
            file_path=self.relative_path,
            message=message,
            start_line=line,
            end_line=end_line,
            start_column=column,
            end_column=end_column,
        )

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return self.relative_path


@dataclass
class RuleContext:
    """Everything a rule is allowed to know about the project being checked.

    Created once by the runner, then narrowed with `for_rule()` / `for_file()`;
    the derived contexts share the caches of the original one.
    """
    target_path: Path
    anchor_file: str = "coding-best-practices-issues.md"
    engine_id: str = ""
    config: Mapping[str, Any] = field(default_factory=dict)
    excluded_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS
    file: FileContext | None = None
    rule: Any = None  # the Rule this context is bound to, see for_rule()
    # The path as the user spelled it, to be used in issue messages: the
    # resolved one is an implementation detail (/github/workspace/... in the
    # action) that has no meaning for whoever reads the report.
    display_path: str = ""
    # Shared between the root context and every context derived from it.
    _cache: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.display_path = self.display_path or str(self.target_path)
        self.target_path = Path(self.target_path).resolve()

    # -- narrowing -----------------------------------------------------------

    def for_rule(self, rule: Any) -> "RuleContext":
        """Context bound to `rule`, so `issue()` can fill in its metadata."""
        return self._derive(rule=rule)

    def for_file(self, file: "FileContext | str | Path") -> "RuleContext":
        """Context bound to a file, reachable by the rule as `context.file`."""
        if not isinstance(file, FileContext):
            file = self.file_context(file)
        return self._derive(file=file)

    def _derive(self, **changes: Any) -> "RuleContext":
        derived = RuleContext(
            target_path=self.target_path,
            anchor_file=self.anchor_file,
            engine_id=self.engine_id,
            config=self.config,
            excluded_dirs=self.excluded_dirs,
            file=self.file,
            rule=self.rule,
            display_path=self.display_path,
            _cache=self._cache,  # caches are deliberately shared
        )
        for name, value in changes.items():
            setattr(derived, name, value)
        return derived

    # -- filesystem access ---------------------------------------------------

    def path(self, relative_path: str | Path = "") -> Path:
        """Absolute path of a project relative path."""
        return self.target_path / Path(relative_path)

    def relative(self, path: str | Path) -> str:
        """Project relative POSIX path of an absolute (or relative) path."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.target_path / candidate
        try:
            return candidate.resolve().relative_to(self.target_path).as_posix()
        except ValueError:
            # Outside of the project: report it as-is rather than crashing.
            return candidate.as_posix()

    def exists(self, relative_path: str | Path) -> bool:
        return self.path(relative_path).exists()

    def is_file(self, relative_path: str | Path) -> bool:
        return self.path(relative_path).is_file()

    def is_dir(self, relative_path: str | Path) -> bool:
        return self.path(relative_path).is_dir()

    def read_text(self, relative_path: str | Path) -> str | None:
        """Content of a project file, or None when missing/binary."""
        if not self.is_file(relative_path):
            return None
        return self.file_context(relative_path).text

    def file_context(self, relative_path: str | Path) -> FileContext:
        """`FileContext` for a project file, cached across rules."""
        relative = self.relative(relative_path)
        cache: dict[str, FileContext] = self._cache.setdefault("files", {})
        if relative not in cache:
            cache[relative] = FileContext(path=self.path(relative), relative_path=relative)
        return cache[relative]

    def find_file(self, *names: str, case_sensitive: bool = False) -> FileContext | None:
        """First existing file among `names` at the project root.

        Lets a rule accept the usual spelling variants, e.g.
        `context.find_file("README.md", "README.rst", "README")`.
        """
        wanted = list(names) if case_sensitive else [name.lower() for name in names]
        entries = {
            entry.name if case_sensitive else entry.name.lower(): entry.name
            for entry in self._root_entries
            if entry.is_file()
        }
        for name in wanted:
            if name in entries:
                return self.file_context(entries[name])
        return None

    def iter_files(
        self,
        *patterns: str,
        include_excluded_dirs: bool = False,
    ) -> Iterator[FileContext]:
        """Walk the project files, deepest-stable and alphabetically ordered.

        `patterns` are `fnmatch` patterns matched against the project relative
        path and against the file name, so both "*.py" and "docs/*.md" work.
        Without pattern, every file is yielded.
        """
        for directory, dir_names, file_names in os.walk(self.target_path):
            if not include_excluded_dirs:
                dir_names[:] = [name for name in dir_names if not self._is_excluded_dir(name)]
            dir_names.sort()
            for file_name in sorted(file_names):
                file = self.file_context(Path(directory) / file_name)
                if matches_patterns(file, patterns):
                    yield file

    def files(self, *patterns: str) -> list[FileContext]:
        """Eager `iter_files()`, handy in tests and for len()/indexing."""
        return list(self.iter_files(*patterns))

    def python_files(self) -> Iterator[FileContext]:
        yield from self.iter_files("*.py")

    def _is_excluded_dir(self, name: str) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in self.excluded_dirs)

    @property
    def _root_entries(self) -> list[Path]:
        if "root_entries" not in self._cache:
            try:
                self._cache["root_entries"] = sorted(self.target_path.iterdir())
            except OSError:
                self._cache["root_entries"] = []
        return self._cache["root_entries"]

    # -- project metadata ----------------------------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        """Project level facts rules may need, resolved once and cached.

        Read from the environment (the action runs in GitHub Actions) with a
        fallback on the local `.git` directory, so that the same rules work when
        the validator runs outside of a workflow.
        """
        if "metadata" not in self._cache:
            self._cache["metadata"] = self._collect_metadata()
        return self._cache["metadata"]

    def _collect_metadata(self) -> dict[str, Any]:
        repository = os.getenv("GITHUB_REPOSITORY")
        if repository:
            server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")
            repository_url = f"{server_url}/{repository}"
        else:
            repository_url = self._git_remote_url()
        return {
            "project_name": repository.split("/")[-1] if repository else self.target_path.name,
            "repository": repository,
            "repository_url": repository_url,
            "default_branch": os.getenv("GITHUB_BASE_REF") or os.getenv("GITHUB_REF_NAME"),
            "is_git_repository": self.is_dir(".git"),
        }

    def _git_remote_url(self) -> str | None:
        """Origin URL read from `.git/config` (no subprocess, no git needed)."""
        git_config = self.path(".git/config")
        if not git_config.is_file():
            return None
        parser = configparser.ConfigParser(strict=False)
        try:
            parser.read(git_config, encoding="utf-8")
        except (OSError, configparser.Error):
            return None
        return parser.get('remote "origin"', "url", fallback=None)

    # -- configuration -------------------------------------------------------

    @property
    def rule_settings(self) -> Mapping[str, Any]:
        """Settings of the bound rule, from the `rules:` configuration block."""
        return self.settings_for(self.rule)

    def settings_for(self, rule: Any) -> Mapping[str, Any]:
        rule_id = getattr(rule, "id", None)
        if not rule_id:
            return {}
        settings = (self.config.get("rules") or {}).get(rule_id) or {}
        return settings if isinstance(settings, Mapping) else {}

    def is_enabled(self, rule: Any) -> bool:
        """Whether a rule should run: rule, category, and dependency settings must ALL allow it."""
        # Checking if the rule is enabled
        settings = self.settings_for(rule)
        if not bool(settings.get("enabled", True)):
            return False
        # Checking if the rule category is enabled
        category = str(getattr(rule, "category", "") or "").lower()
        categories = {
            str(name).lower(): value for name, value in (self.config.get("categories") or {}).items()
        }
        category_settings = categories.get(category) or {}
        category_enabled = (
            bool(category_settings.get("enabled", True))
            if isinstance(category_settings, Mapping)
            else True
        )
        if not category_enabled:
            return False
        # Checking if all the rule dependencies are enabled/available
        dependencies = getattr(rule, "dependencies", None) or []
        configured_dependencies = {
            str(name).lower(): value for name, value in (self.config.get("dependencies") or {}).items()
        }
        for dependency in dependencies:
            dependency_settings = configured_dependencies.get(str(dependency).lower())
            if isinstance(dependency_settings, Mapping) and not bool(dependency_settings.get("enabled", True)):
                return False
        return True

    def severity_for(self, rule: Any) -> Severity:
        """Configured severity for a rule, else its `default_severity`."""
        settings = self.settings_for(rule)
        raw = settings.get("severity") or getattr(rule, "default_severity", None)
        return Severity.parse(raw) if raw else Severity.MINOR

    def rule_setting(self, key: str, default: Any) -> Any:
        return self.rule_settings.get(key, default)

    # -- issue reporting -----------------------------------------------------

    def issue(
        self,
        message: str,
        *,
        location: Location | None = None,
        file_path: str | Path | None = None,
        node: ast.AST | None = None,
        line: int | None = None,
        end_line: int | None = None,
        column: int | None = None,
        end_column: int | None = None,
        severity: Severity | str | None = None,
        issue_type: IssueType | None = None,
        impacts: tuple[Impact, ...] = (),
        effort_minutes: int | None = None,
        secondary_locations: tuple[Location, ...] = (),
        rule_id: str | None = None,
        **properties: Any,
    ) -> Issue:
        """Build an `Issue` for the bound rule.

        The location defaults to the bound file, and to the anchor file for
        project level findings which have no file to point at.
        """
        rule = self.rule
        if location is None:
            location = self._default_location(
                message=message,
                file_path=file_path,
                node=node,
                line=line,
                end_line=end_line,
                column=column,
                end_column=end_column,
            )
        return Issue(
            rule_id=rule_id or getattr(rule, "id", ""),
            message=message,
            location=location,
            severity=Severity.parse(severity) if severity else self.severity_for(rule),
            issue_type=issue_type or getattr(rule, "issue_type", IssueType.CODE_SMELL),
            impacts=impacts or tuple(getattr(rule, "impacts", ()) or ()),
            secondary_locations=secondary_locations,
            effort_minutes=(
                effort_minutes
                if effort_minutes is not None
                else getattr(rule, "effort_minutes", None)
            ),
            engine_id=self.engine_id or None,
            properties=properties,
        )

    def _default_location(
        self,
        *,
        message: str,
        file_path: str | Path | None,
        node: ast.AST | None,
        line: int | None,
        end_line: int | None,
        column: int | None,
        end_column: int | None,
    ) -> Location:
        target = self.file_context(file_path) if file_path is not None else self.file
        if target is None:
            # Nothing to anchor the issue on: use the anchor file, which the
            # runner makes sure exists so that reports can be imported.
            return Location(file_path=self.anchor_file, message=message)
        return target.location(
            message=message,
            node=node,
            line=line,
            end_line=end_line,
            column=column,
            end_column=end_column,
        )

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        bound = f" file={self.file}" if self.file else ""
        return f"<RuleContext {self.target_path}{bound}>"
