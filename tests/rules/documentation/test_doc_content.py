import pytest

from coding_best_practices_for_oss.core.issue import Severity
from coding_best_practices_for_oss.rules.documentation import doc_content
from coding_best_practices_for_oss.rules.documentation.doc_content import TOPICS, DocumentationContentRule


@pytest.fixture
def rule():
    return DocumentationContentRule()


@pytest.fixture
def check(make_context, rule):
    def _check(files, config=None):
        return rule.check(make_context(files, rule=rule, config=config))

    return _check


def fake_model(answers, prompts=None):
    """A query_model replacement returning the given {topic: [paths]} answers."""

    def _query(prompt):
        if prompts is not None:
            prompts.append(prompt)
        return {"topics": answers}

    return _query


class TestDocumentationContentRule:
    def test_no_documentation_reports_every_topic_without_querying_the_model(self, check, monkeypatch):
        monkeypatch.setattr(doc_content, "query_model", pytest.fail)
        issues = check({"app.py": "x = 1\n"})
        assert len(issues) == len(TOPICS)
        assert all(i.file_path == "coding-best-practices-issues.md" for i in issues)

    def test_no_documentation_but_a_dependency_file(self, check, monkeypatch):
        monkeypatch.setattr(doc_content, "query_model", pytest.fail)
        issues = check({"app.py": "x = 1\n", "pyproject.toml": "[project]\n"})
        assert len(issues) == len(TOPICS) - 1
        assert not any(TOPICS["dependencies"][0] in i.message for i in issues)

    def test_one_issue_per_missing_topic_on_the_readme(self, check, monkeypatch):
        prompts = []
        answers = {"installation": ["README.md"], "execution": ["docs/usage.md"], "examples": ["docs/usage.md"]}
        monkeypatch.setattr(doc_content, "query_model", fake_model(answers, prompts))
        issues = check({
            "README.md": "# Demo\n",
            "docs/usage.md": "Run `demo`.\n",
            "requirements.txt": "requests\n",
            "LICENSE.txt": "MIT\n",
        })

        # requirements.txt covers the dependencies: the model is not asked about them
        assert '"dependencies"' not in prompts[0]
        # LICENSE.txt and requirements.txt are not documentation
        assert "LICENSE.txt" not in prompts[0] and "### File: requirements.txt" not in prompts[0]
        # The root README is sent first
        assert prompts[0].index("README.md") < prompts[0].index("docs/usage.md")

        assert len(issues) == 2
        assert all(i.file_path == "README.md" for i in issues)
        messages = " ".join(i.message for i in issues)
        assert TOPICS["inputs"][0] in messages and TOPICS["outputs"][0] in messages

    def test_paths_made_up_by_the_model_are_ignored(self, check, monkeypatch):
        answers = {topic: ["NOT_SENT.md"] for topic in TOPICS}
        monkeypatch.setattr(doc_content, "query_model", fake_model(answers))
        issues = check({"README.md": "# Demo\n"})
        assert len(issues) == len(TOPICS)

    def test_info_issue_when_everything_is_covered(self, check, monkeypatch):
        answers = {topic: ["README.md"] for topic in TOPICS}
        monkeypatch.setattr(doc_content, "query_model", fake_model(answers))
        issues = check({"README.md": "# Demo\n"})
        assert len(issues) == 1
        assert issues[0].severity is Severity.INFO

    def test_topics_are_merged_across_chunks(self, check, monkeypatch):
        prompts = []

        def query(prompt):
            prompts.append(prompt)
            path = "README.md" if len(prompts) == 1 else "docs/more.md"
            topics = ["installation", "execution", "examples"] if len(prompts) == 1 else ["dependencies", "inputs", "outputs"]
            return {"topics": {t: [path] for t in topics}}

        monkeypatch.setattr(doc_content, "query_model", query)
        config = {"rules": {"DOC002": {"max_files": 1}}}
        issues = check({"README.md": "# Demo\n", "docs/more.md": "More\n"}, config=config)
        assert len(prompts) == 2
        # Only the topics still missing are asked in the second chunk
        assert '"installation"' not in prompts[1]
        assert [i.severity for i in issues] == [Severity.INFO]

    def test_the_anchor_file_is_used_without_readme(self, check, monkeypatch):
        monkeypatch.setattr(doc_content, "query_model", fake_model({}))
        issues = check({"docs/guide.md": "Guide\n"})
        assert len(issues) == len(TOPICS)
        assert all(i.file_path == "coding-best-practices-issues.md" for i in issues)
