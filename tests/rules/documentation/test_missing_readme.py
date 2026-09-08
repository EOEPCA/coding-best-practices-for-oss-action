import pytest

from coding_best_practices_for_oss.core.context import RuleContext
from coding_best_practices_for_oss.core.issue import (
    Impact,
    ImpactSeverity,
    Severity,
    SoftwareQuality,
)
from coding_best_practices_for_oss.rules.documentation.missing_readme import MissingReadmeRule


@pytest.fixture
def rule():
    return MissingReadmeRule()


@pytest.fixture
def check(make_context, rule):
    def _check(files=None, **kwargs):
        return rule.check(make_context(files, rule=rule, **kwargs))

    return _check


class TestMissingReadmeRule:
    @pytest.mark.parametrize(
        "name", ["README.md", "README.rst", "README.txt", "README", "readme.md", "ReadMe.MD"]
    )
    def test_no_issue_when_a_readme_is_there(self, check, name):
        assert check({name: "# Demo\n"}) == []

    def test_an_issue_is_reported_when_the_readme_is_missing(self, check):
        issues = check({"src/app.py": "x = 1\n"}, anchor_file="anchor.md")
        assert len(issues) == 1

        issue = issues[0]
        assert issue.rule_id == "DOC001"
        assert issue.severity is Severity.MINOR
        assert issue.effort_minutes == 60
        # No source file to blame: the issue points at the anchor file.
        assert issue.file_path == "anchor.md"
        assert issue.location.start_line is None
        assert "README (md, rst, txt) file missing" in issue.message

    def test_the_message_uses_the_path_as_given(self, rule, make_project, monkeypatch):
        project = make_project()
        monkeypatch.chdir(project.parent)
        # The resolved path (/github/workspace/... in the action) must not leak.
        context = RuleContext(target_path=project.name).for_rule(rule)
        assert f"'{project.name}'" in rule.check(context)[0].message

    def test_a_readme_directory_does_not_count(self, check):
        assert len(check({"README.md/notes.txt": ""})) == 1

    def test_the_reported_impact(self, check):
        assert check()[0].impacts == (
            Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),
        )

    def test_the_rule_is_project_scoped(self, rule):
        assert rule.is_file_scoped is False
        assert rule.category == "documentation"
