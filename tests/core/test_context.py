import ast
from pathlib import Path

import pytest

from coding_best_practices_for_oss.core.context import (
    MAX_TEXT_FILE_SIZE,
    FileContext,
    RuleContext,
    matches_patterns,
)
from coding_best_practices_for_oss.core.issue import Severity

from tests.conftest import ProjectRule, PythonFileRule


class TestFileContext:
    def test_text_and_lines(self, make_context):
        context = make_context({"a.txt": "first\nsecond\n"})
        file = context.file_context("a.txt")
        assert file.text == "first\nsecond\n"
        assert file.lines == ["first", "second"]
        assert file.line_count == 2
        assert file.line(2) == "second"

    @pytest.mark.parametrize("number", [0, 3, -1])
    def test_line_out_of_range_is_empty(self, make_context, number):
        file = make_context({"a.txt": "one\ntwo\n"}).file_context("a.txt")
        assert file.line(number) == ""

    def test_a_binary_file_has_no_text(self, make_context):
        context = make_context()
        context.path("logo.png").write_bytes(b"\x89PNG\x00\xff")
        assert context.file_context("logo.png").text is None
        assert context.file_context("logo.png").lines == []

    def test_an_oversized_file_has_no_text(self, make_context):
        context = make_context({"big.py": "#" * (MAX_TEXT_FILE_SIZE + 1)})
        assert context.file_context("big.py").text is None

    def test_a_missing_file_has_no_text(self, make_context):
        assert make_context().file_context("nope.py").text is None

    def test_python_files_are_parsed(self, make_context):
        file = make_context({"a.py": "x = 1\n"}).file_context("a.py")
        assert isinstance(file.ast, ast.Module)
        assert file.syntax_error is None
        assert file.is_python

    def test_a_syntax_error_is_reported_instead_of_raised(self, make_context):
        file = make_context({"a.py": "def broken(\n"}).file_context("a.py")
        assert file.ast is None
        assert isinstance(file.syntax_error, SyntaxError)

    def test_a_non_python_file_is_not_parsed(self, make_context):
        file = make_context({"a.md": "# title\n"}).file_context("a.md")
        assert (file.ast, file.syntax_error, file.is_python) == (None, None, False)

    def test_location_converts_the_columns_of_an_ast_node(self, make_context):
        file = make_context({"a.py": "value = 1\n"}).file_context("a.py")
        node = file.ast.body[0].value  # the literal 1, at 0-based column 8
        location = file.location("a message", node=node)
        assert (location.start_line, location.start_column) == (1, 9)
        assert location.end_column == 10
        assert location.file_path == "a.py"


class TestFileWalking:
    def test_excluded_directories_are_not_walked(self, make_context):
        context = make_context(
            {
                "src/app.py": "",
                "node_modules/dep.py": "",
                ".git/config": "",
                "__pycache__/app.pyc": "",
                ".venv/lib/thing.py": "",
            }
        )
        assert [file.relative_path for file in context.iter_files()] == ["src/app.py"]

    def test_the_walk_is_deterministic_and_sorted(self, make_context):
        context = make_context({"b.py": "", "a.py": "", "sub/c.py": "", "sub/a.py": ""})
        assert [file.relative_path for file in context.iter_files()] == [
            "a.py",
            "b.py",
            "sub/a.py",
            "sub/c.py",
        ]

    @pytest.mark.parametrize("pattern", ["*.py", "src/*.py", "app.py"])
    def test_patterns_match_the_name_or_the_relative_path(self, make_context, pattern):
        context = make_context({"src/app.py": "", "src/notes.md": ""})
        assert [file.relative_path for file in context.iter_files(pattern)] == ["src/app.py"]

    def test_without_pattern_every_file_is_yielded(self, make_context):
        context = make_context({"a.py": "", "b.md": ""})
        assert len(context.files()) == 2

    def test_a_file_context_is_reused_across_rules(self, make_context):
        context = make_context({"a.py": "x = 1\n"})
        first = next(iter(context.iter_files()))
        # Same object, so the content read and the AST parsed once are shared.
        assert context.file_context("a.py") is first
        assert context.for_rule(PythonFileRule())._cache is context._cache

    def test_matches_patterns_without_pattern_accepts_everything(self):
        file = FileContext(path=Path("/tmp/a.py"), relative_path="a.py")
        assert matches_patterns(file, ()) is True


class TestProjectAccess:
    def test_find_file_ignores_the_case_and_follows_the_given_order(self, make_context):
        context = make_context({"readme.RST": "", "README.md": ""})
        assert context.find_file("README.md", "README.rst").name == "README.md"
        assert context.find_file("README.rst", "README.md").name == "readme.RST"

    def test_find_file_can_be_case_sensitive(self, make_context):
        context = make_context({"readme.md": ""})
        assert context.find_file("README.md", case_sensitive=True) is None

    def test_find_file_returns_none_when_missing(self, make_context):
        assert make_context().find_file("README.md") is None

    def test_find_file_ignores_directories(self, make_context):
        context = make_context({"README.md/keep.txt": ""})
        assert context.find_file("README.md") is None

    def test_relative_paths(self, make_context):
        context = make_context({"src/a.py": ""})
        assert context.relative("src/a.py") == "src/a.py"
        assert context.relative(context.path("src/a.py")) == "src/a.py"

    def test_a_path_outside_the_project_is_reported_as_is(self, make_context):
        context = make_context()
        assert context.relative("/etc/passwd") == "/etc/passwd"

    def test_read_text_of_a_missing_file(self, make_context):
        context = make_context({"a.txt": "content"})
        assert context.read_text("a.txt") == "content"
        assert context.read_text("missing.txt") is None

    def test_display_path_keeps_the_path_as_given(self, tmp_path, monkeypatch):
        (tmp_path / "proj").mkdir()
        monkeypatch.chdir(tmp_path)
        context = RuleContext(target_path="proj")
        assert context.display_path == "proj"
        assert context.target_path.is_absolute()
        assert context.for_rule(ProjectRule()).display_path == "proj"

    def test_metadata_from_the_github_environment(self, make_context, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "EOEPCA/demo")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        metadata = make_context().metadata
        assert metadata["project_name"] == "demo"
        assert metadata["repository_url"] == "https://github.com/EOEPCA/demo"
        assert metadata["default_branch"] == "main"

    def test_metadata_falls_back_on_the_git_config(self, make_context, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        context = make_context(
            {".git/config": '[remote "origin"]\n\turl = git@github.com:EOEPCA/demo.git\n'}
        )
        assert context.metadata["repository_url"] == "git@github.com:EOEPCA/demo.git"
        assert context.metadata["is_git_repository"] is True

    def test_metadata_without_any_source(self, make_context, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        metadata = make_context().metadata
        assert metadata["repository_url"] is None
        assert metadata["is_git_repository"] is False
        assert metadata["project_name"] == "proj"


class TestConfiguration:
    def test_rules_are_enabled_by_default(self, make_context):
        assert make_context().is_enabled(ProjectRule()) is True

    def test_a_rule_can_be_disabled(self, make_context):
        context = make_context(config={"rules": {"PRJ001": {"enabled": False}}})
        assert context.is_enabled(ProjectRule()) is False

    def test_a_category_can_be_disabled_whatever_its_case(self, make_context):
        context = make_context(config={"categories": {"DOCUMENTATION": {"enabled": False}}})
        assert context.is_enabled(ProjectRule()) is False

    def test_the_rule_and_category_must_be_enabled(self, make_context):
        context = make_context(
            config={
                "rules": {"PRJ001": {"enabled": True}},
                "categories": {"documentation": {"enabled": True}},
            }
        )
        assert context.is_enabled(ProjectRule()) is True
        context = make_context(
            config={
                "rules": {"PRJ001": {"enabled": True}},
                "categories": {"documentation": {"enabled": False}},
            }
        )
        assert context.is_enabled(ProjectRule()) is False
        context = make_context(
            config={
                "rules": {"PRJ001": {"enabled": False}},
                "categories": {"documentation": {"enabled": True}},
            }
        )
        assert context.is_enabled(ProjectRule()) is False

    def test_all_rule_dependencies_must_be_enabled(self, make_context):
        context = make_context(
            config={
                "rules": {"PRJ001": {"enabled": True}},
                "categories": {"documentation": {"enabled": True}},
                "dependencies": {"ai": {"enabled": False}}
            }
        )
        assert context.is_enabled(ProjectRule()) is False

    def test_severity_comes_from_the_rule_by_default(self, make_context):
        assert make_context().severity_for(ProjectRule()) is Severity.MAJOR

    def test_severity_can_be_overridden(self, make_context):
        context = make_context(config={"rules": {"PRJ001": {"severity": "blocker"}}})
        assert context.severity_for(ProjectRule()) is Severity.BLOCKER

    def test_rule_settings_are_exposed_to_the_bound_rule(self, make_context):
        context = make_context(
            config={"rules": {"PRJ001": {"max": 3}}}, rule=ProjectRule()
        )
        assert context.rule_settings == {"max": 3}

    def test_settings_of_an_unknown_rule_are_empty(self, make_context):
        assert make_context().settings_for(ProjectRule()) == {}


class TestIssueFactory:
    def test_a_project_issue_lands_on_the_anchor_file(self, make_context):
        context = make_context(rule=ProjectRule(), anchor_file="anchor.md")
        issue = context.issue("no README")
        assert issue.file_path == "anchor.md"
        assert issue.location.start_line is None
        assert (issue.rule_id, issue.message) == ("PRJ001", "no README")
        assert issue.severity is Severity.MAJOR
        assert issue.effort_minutes == 5
        assert issue.engine_id == "Test Engine"

    def test_a_file_issue_lands_on_the_bound_file(self, make_context):
        context = make_context({"src/a.py": "x = 1\n"}, rule=PythonFileRule())
        issue = context.for_file("src/a.py").issue("nope", line=1)
        assert (issue.file_path, issue.location.start_line) == ("src/a.py", 1)
        assert issue.impacts == PythonFileRule.impacts

    def test_the_severity_override_reaches_the_issue(self, make_context):
        context = make_context(
            config={"rules": {"PRJ001": {"severity": "INFO"}}}, rule=ProjectRule()
        )
        assert context.issue("m").severity is Severity.INFO

    def test_an_explicit_severity_wins(self, make_context):
        context = make_context(rule=ProjectRule())
        assert context.issue("m", severity="BLOCKER").severity is Severity.BLOCKER

    def test_an_explicit_file_path_can_be_given(self, make_context):
        context = make_context({"setup.cfg": ""}, rule=ProjectRule())
        assert context.issue("m", file_path="setup.cfg").file_path == "setup.cfg"

    def test_extra_keywords_become_sarif_properties(self, make_context):
        context = make_context(rule=ProjectRule())
        assert context.issue("m", checked="README.md").properties == {"checked": "README.md"}
