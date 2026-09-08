import logging

import pytest

from coding_best_practices_for_oss.core.issue import Issue, Location
from coding_best_practices_for_oss.core.rule import FILE_SCOPE, Rule
from coding_best_practices_for_oss.core.runner import Runner, run

from tests.conftest import CrashingRule, ProjectRule, PythonFileRule


@pytest.fixture
def make_runner(make_project):
    def _make_runner(files=None, rules=(), *, config=None, **kwargs):
        return Runner(
            make_project(files),
            engine_id="Test Engine",
            config=config or {},
            rules=list(rules),
            **kwargs,
        )

    return _make_runner


class TestRun:
    def test_an_invalid_directory_is_reported(self, tmp_path):
        with pytest.raises(NotADirectoryError, match="not a valid directory"):
            run(tmp_path / "nope")

    def test_project_and_file_rules_both_run(self, make_runner):
        runner = make_runner({"a.py": "x = 1\n"}, [ProjectRule(), PythonFileRule()])
        result = runner.run()
        assert [issue.rule_id for issue in result.issues] == ["PY001", "PRJ001"]
        assert result.files_checked == 1

    def test_issues_are_sorted_and_deduplicated(self, make_runner):
        class DuplicatingRule(Rule):
            id = "DUP001"

            def check(self, context):
                return [context.issue("same"), context.issue("same")]

        result = make_runner(rules=[DuplicatingRule()]).run()
        assert len(result.issues) == 1

    def test_a_file_rule_only_sees_the_files_it_asked_for(self, make_runner):
        seen = []

        class MarkdownRule(Rule):
            id = "MD001"
            scope = FILE_SCOPE
            file_patterns = ("*.md",)

            def check(self, context):
                seen.append(context.file.relative_path)
                return []

        make_runner({"a.md": "", "b.py": "", "docs/c.md": ""}, [MarkdownRule()]).run()
        assert seen == ["a.md", "docs/c.md"]

    def test_every_rule_shares_the_same_file_context(self, make_runner):
        seen = []

        class RecordingRule(Rule):
            scope = FILE_SCOPE

            def check(self, context):
                seen.append(context.file)
                return []

        class FirstRule(RecordingRule):
            id = "ONE"

        class SecondRule(RecordingRule):
            id = "TWO"

        make_runner({"a.py": "x = 1\n"}, [FirstRule(), SecondRule()]).run()
        # Same object: the file is read and parsed once for both rules.
        assert len(seen) == 2 and seen[0] is seen[1]

    def test_a_disabled_rule_does_not_run(self, make_runner):
        runner = make_runner(
            rules=[ProjectRule()], config={"rules": {"PRJ001": {"enabled": False}}}
        )
        result = runner.run()
        assert result.issues == []
        assert result.disabled == ["PRJ001"]
        assert result.rules == []

    def test_the_engine_id_reaches_the_issues(self, make_runner):
        result = make_runner(rules=[ProjectRule()]).run()
        assert result.issues[0].engine_id == "Test Engine"

    def test_the_summary_reports_the_counts(self, make_runner):
        result = make_runner({"a.py": "x = 1\n"}, [ProjectRule(), PythonFileRule()]).run()
        assert "2 issue(s) found by 2 rule(s) on 1 file(s)" in result.summary()

    def test_rules_are_discovered_when_none_is_given(self, make_project):
        result = Runner(make_project()).run()
        assert [issue.rule_id for issue in result.issues] == ["DOC001"]


class TestFailingRules:
    def test_a_crashing_rule_does_not_stop_the_run(self, make_runner, caplog):
        runner = make_runner({"a.py": "x = 1\n"}, [CrashingRule(), PythonFileRule()])
        with caplog.at_level(logging.ERROR):
            result = runner.run()
        assert [issue.rule_id for issue in result.issues] == ["PY001"]
        assert len(result.errors) == 1
        assert "kaboom" in result.errors[0] and "a.py" in result.errors[0]

    def test_a_rule_returning_something_else_than_issues_is_reported(self, make_runner, caplog):
        class LegacyRule(Rule):
            id = "OLD001"

            def check(self, context):
                return [{"ruleId": "OLD001"}]  # the pre-refactor report dict

        with caplog.at_level(logging.ERROR):
            result = make_runner(rules=[LegacyRule()]).run()
        assert result.issues == []
        assert "expected an Issue" in result.errors[0]

    @pytest.mark.parametrize("returned", [None, "single"])
    def test_none_and_a_single_issue_are_accepted(self, make_runner, returned):
        class LenientRule(Rule):
            id = "LEN001"

            def check(self, context):
                return None if returned is None else context.issue("one")

        result = make_runner(rules=[LenientRule()]).run()
        assert len(result.issues) == (0 if returned is None else 1)


class TestAnchorFile:
    def test_the_anchor_file_is_created_when_an_issue_needs_it(self, make_runner):
        runner = make_runner(rules=[ProjectRule()], anchor_file="anchor.md")
        runner.run()
        assert runner.context.path("anchor.md").is_file()

    def test_no_anchor_file_is_created_when_no_issue_needs_it(self, make_runner):
        runner = make_runner({"a.py": "x = 1\n"}, [PythonFileRule()], anchor_file="anchor.md")
        runner.run()
        assert not runner.context.path("anchor.md").exists()

    def test_the_anchor_file_creation_can_be_turned_off(self, make_runner):
        runner = make_runner(
            rules=[ProjectRule()], anchor_file="anchor.md", create_anchor_file=False
        )
        runner.run()
        assert not runner.context.path("anchor.md").exists()

    def test_an_existing_anchor_file_is_left_alone(self, make_runner):
        runner = make_runner({"anchor.md": "notes"}, [ProjectRule()], anchor_file="anchor.md")
        runner.run()
        assert runner.context.path("anchor.md").read_text() == "notes"


class TestRunResult:
    def test_only_the_rules_that_reported_an_issue_are_triggered(self, make_runner):
        class SilentRule(Rule):
            id = "QUIET001"

            def check(self, context):
                return []

        result = make_runner(rules=[ProjectRule(), SilentRule()]).run()
        assert [rule.id for rule in result.triggered_rules] == ["PRJ001"]

    def test_triggered_rules_ignores_unknown_rule_ids(self, make_runner):
        result = make_runner(rules=[ProjectRule()]).run()
        result.issues.append(Issue("GHOST", "m", Location("a.py")))
        assert [rule.id for rule in result.triggered_rules] == ["PRJ001"]
