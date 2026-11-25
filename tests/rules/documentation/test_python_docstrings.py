import pytest

from coding_best_practices_for_oss.core.issue import Severity
from coding_best_practices_for_oss.rules.documentation import python_docstrings_sem
from coding_best_practices_for_oss.rules.documentation.python_docstrings import PythonDocstringsRule
from coding_best_practices_for_oss.rules.documentation.python_docstrings_sem import (
    PythonDocstringsSemanticRule,
)

SOURCE = '''\
def nodoc(x):
    return x


def empty(x):
    """ """
    return x


def todo(x):
    """TODO"""
    return x


def get_value(x):
    """Get value."""
    return x


def _private(x):
    return x


def add(a, b):
    """Return the product of a and b."""
    return a + b


class Foo:
    def method(self):
        pass
'''


@pytest.fixture
def check(make_context):
    def _check(rule, files, config=None):
        return rule.check(make_context(files, rule=rule, config=config))

    return _check


class TestPythonDocstringsRule:
    def test_missing_and_empty_docstrings(self, check):
        issues = check(PythonDocstringsRule(), {"mod.py": SOURCE})
        found = {(i.file_path, i.location.start_line) for i in issues}
        # nodoc, empty (reported on its docstring line), Foo, Foo.method; _private is ignored
        assert found == {("mod.py", 1), ("mod.py", 6), ("mod.py", 29), ("mod.py", 30)}
        assert all(i.rule_id == "DOC005" for i in issues)

    def test_info_issue_when_everything_is_documented(self, check):
        issues = check(PythonDocstringsRule(), {"mod.py": 'def f():\n    """Do f."""\n'})
        assert len(issues) == 1
        assert issues[0].severity is Severity.INFO


class TestPythonDocstringsSemanticRule:
    def test_placeholders_and_model_findings(self, check, monkeypatch):
        prompts = []

        def fake_query_model(prompt):
            prompts.append(prompt)
            # Only "add" is sent to the model: "todo" and "get_value" are placeholders
            return {"items": [{"index": 0, "meaningless": False, "contradicts": True,
                               "explanation": "the code returns the sum"}]}

        monkeypatch.setattr(python_docstrings_sem, "query_model", fake_query_model)
        issues = check(PythonDocstringsSemanticRule(), {"mod.py": SOURCE})

        assert len(prompts) == 1
        assert "'add'" in prompts[0] and "'todo'" not in prompts[0]
        messages = {i.location.start_line: (i.message, i.severity) for i in issues}
        assert set(messages) == {10, 15, 24}
        assert "placeholder" in messages[10][0]
        assert "placeholder" in messages[15][0]
        assert "contradicts the code: the code returns the sum" in messages[24][0]
        assert messages[24][1] is Severity.MAJOR

    def test_no_documented_code_does_not_query_the_model(self, check, monkeypatch):
        monkeypatch.setattr(python_docstrings_sem, "query_model", pytest.fail)
        assert check(PythonDocstringsSemanticRule(), {"mod.py": "x = 1\n"}) == []

    def test_invalid_model_entries_are_ignored(self, check, monkeypatch):
        monkeypatch.setattr(
            python_docstrings_sem, "query_model",
            lambda prompt: {"items": [{"index": 7, "meaningless": True}, "junk"]},
        )
        issues = check(PythonDocstringsSemanticRule(), {"mod.py": 'def f():\n    """Compute f."""\n'})
        assert len(issues) == 1
        assert issues[0].severity is Severity.INFO
