import os
import shutil
import subprocess

import pytest

from coding_best_practices_for_oss.core.context import RuleContext
from coding_best_practices_for_oss.core.issue import Severity
from coding_best_practices_for_oss.rules.maintainability.stale_todo import StaleTodoRule, marker_regex

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

DAY = 86400
NOW = 1_800_000_000  # Fixed "now" for the ages


def git(root, *args, days_ago=None):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    if days_ago is not None:
        date = f"@{NOW - days_ago * DAY} +0000"
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=root, env=env, check=True, capture_output=True,
    )


def commit(root, files, days_ago):
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", f"{days_ago} days ago", days_ago=days_ago)


@pytest.fixture
def repo(make_project):
    root = make_project()
    git(root, "init", "-q")
    return root


@pytest.fixture
def check(monkeypatch):
    rule = StaleTodoRule()
    monkeypatch.setattr(StaleTodoRule, "now", staticmethod(lambda: NOW))

    def _check(root, config=None):
        return rule.check(RuleContext(target_path=root, config=config or {}).for_rule(rule))

    return _check


class TestMarkerRegex:
    @pytest.mark.parametrize("line", [
        "x = 1  # TODO fix", "// FIXME: later", "/* XXX */", " * TODO in a block", "-- TODO sql",
        "<!-- TODO html -->", "# see TODO below",
    ])
    def test_markers_in_comments(self, line):
        assert marker_regex(["TODO", "FIXME", "XXX"]).search(line)

    @pytest.mark.parametrize("line", ["TODO = 1", "todo_list = []", "# a todo in lowercase", "# TODOS", '# placeholders ("TODO", "...")', "# the `FIXME` marker"])
    def test_not_markers(self, line):
        assert not marker_regex(["TODO", "FIXME", "XXX"]).search(line)


class TestStaleTodoRule:
    def test_ages_and_severities(self, repo, check):
        commit(repo, {"a.py": "# TODO very old\nx = 1\n"}, days_ago=400)
        commit(repo, {"b.sh": "#!/bin/sh\n# FIXME old\n"}, days_ago=200)
        commit(repo, {"c.js": "// TODO recent\n"}, days_ago=10)
        issues = check(repo)

        found = {(i.file_path, i.location.start_line): i for i in issues}
        assert set(found) == {("a.py", 1), ("b.sh", 2)}
        assert found[("a.py", 1)].severity is Severity.MAJOR
        assert found[("b.sh", 2)].severity is Severity.MINOR
        assert "present for 400 days" in found[("a.py", 1)].message
        assert "TODO very old" in found[("a.py", 1)].message

    def test_the_age_is_the_last_change_of_the_line(self, repo, check):
        commit(repo, {"a.py": "# TODO first\nx = 1\n"}, days_ago=400)
        # Changing an other line keeps the age, changing the comment resets it
        commit(repo, {"a.py": "# TODO first\nx = 2\n# TODO second\n"}, days_ago=300)
        commit(repo, {"a.py": "# TODO first, reworded\nx = 2\n# TODO second\n"}, days_ago=5)
        issues = check(repo)
        assert [(i.location.start_line, i.severity) for i in issues] == [(3, Severity.MINOR)]

    def test_uncommitted_and_untracked_comments_are_new(self, repo, check):
        commit(repo, {"a.py": "x = 1\n"}, days_ago=400)
        (repo / "a.py").write_text("# TODO local change\nx = 1\n")
        (repo / "new.py").write_text("# TODO untracked\n")
        issues = check(repo)
        assert [i.severity for i in issues] == [Severity.INFO]
        # The untracked file is not scanned
        assert "(1 found)" in issues[0].message

    def test_thresholds_and_markers_are_configurable(self, repo, check):
        commit(repo, {"a.py": "# TODO a\n# NOTE b\n"}, days_ago=40)
        config = {"rules": {"MNT001": {"markers": ["NOTE"], "warning_threshold": 30, "error_threshold": None}}}
        issues = check(repo, config)
        assert [(i.location.start_line, i.severity) for i in issues] == [(2, Severity.MINOR)]

    def test_thresholds_given_as_strings(self, repo, check):
        # e.g. "critical_threshold: None" in YAML is the string "None", not null
        commit(repo, {"a.py": "# TODO a\n"}, days_ago=400)
        config = {"rules": {"MNT001": {"warning_threshold": "30", "error_threshold": "1000",
                                       "critical_threshold": "None"}}}
        issues = check(repo, config)
        assert [i.severity for i in issues] == [Severity.MINOR]

    def test_not_a_git_repository(self, make_project, check):
        root = make_project({"a.py": "# TODO\n"}, name="nogit")
        issues = check(root)
        assert len(issues) == 1 and issues[0].severity is Severity.INFO
        assert "not in a git repository" in issues[0].message

    def test_shallow_clone(self, repo, check, tmp_path):
        commit(repo, {"a.py": "# TODO old\n"}, days_ago=400)
        commit(repo, {"b.py": "x = 1\n"}, days_ago=1)
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(clone))
        issues = check(clone)
        assert len(issues) == 1 and issues[0].severity is Severity.INFO
        assert "fetch-depth: 0" in issues[0].message
