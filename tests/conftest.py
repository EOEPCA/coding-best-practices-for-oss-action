# Shared fixtures: building throwaway projects and contexts to check rules on.
from pathlib import Path
from typing import Any, Mapping

import pytest

from coding_best_practices_for_oss.core.context import RuleContext
from coding_best_practices_for_oss.core.issue import Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import FILE_SCOPE, Rule


@pytest.fixture
def make_project(tmp_path):
    """Create a project tree from a {relative path: content} mapping."""

    def _make_project(files: Mapping[str, str] | None = None, name: str = "proj") -> Path:
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        for relative_path, content in (files or {}).items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    return _make_project


@pytest.fixture
def make_context(make_project):
    """Build a `RuleContext` on a throwaway project."""

    def _make_context(
        files: Mapping[str, str] | None = None,
        *,
        config: Mapping[str, Any] | None = None,
        rule: Rule | None = None,
        engine_id: str = "Test Engine",
        **kwargs: Any,
    ) -> RuleContext:
        context = RuleContext(
            target_path=make_project(files),
            engine_id=engine_id,
            config=config or {},
            **kwargs,
        )
        return context.for_rule(rule) if rule else context

    return _make_context


class ProjectRule(Rule):
    """Reports one issue on the anchor file, unconditionally."""

    id = "PRJ001"
    name = "Project rule"
    category = "documentation"
    dependencies = ["python3", "ai"]
    default_severity = "MAJOR"
    effort_minutes = 5

    def check(self, context):
        return [context.issue("project issue")]


class PythonFileRule(Rule):
    """Reports one issue per line of every Python file."""

    id = "PY001"
    name = "Python file rule"
    category = "style"
    default_severity = "MINOR"
    scope = FILE_SCOPE
    file_patterns = ("*.py",)
    impacts = (Impact(SoftwareQuality.RELIABILITY, ImpactSeverity.LOW),)

    def check(self, context):
        return [
            context.issue(f"line {number}", line=number)
            for number, _ in enumerate(context.file.lines, start=1)
        ]


class CrashingRule(Rule):
    id = "BOOM001"
    name = "Crashing rule"
    category = "security"
    scope = FILE_SCOPE

    def check(self, context):
        raise RuntimeError("kaboom")
