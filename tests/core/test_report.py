import json
import logging

import pytest

from coding_best_practices_for_oss import __version__
from coding_best_practices_for_oss.core.report import (
    FORMAT_GENERIC,
    FORMAT_SARIF,
    generate_report,
    plain_text,
    write_report,
)
from coding_best_practices_for_oss.core.runner import Runner

from tests.conftest import ProjectRule, PythonFileRule


@pytest.fixture
def result(make_project):
    """A run reporting one project issue and one file issue."""
    return Runner(
        make_project({"a.py": "x = 1\n"}),
        engine_id="Test Engine",
        rules=[ProjectRule(), PythonFileRule()],
    ).run()


class TestPlainText:
    def test_the_markup_is_stripped_and_the_entities_decoded(self):
        assert plain_text("<p>A <code>README.md</code> &amp; more</p>") == "A README.md & more"

    def test_an_empty_description_stays_empty(self):
        assert plain_text("") == ""


class TestGenericReport:
    def test_only_the_triggered_rules_are_described(self, result):
        report = generate_report(result, FORMAT_GENERIC, engine_id="Test Engine")
        assert [rule["id"] for rule in report["rules"]] == ["PY001", "PRJ001"]
        assert len(report["issues"]) == 2

    def test_the_rule_descriptor_fields(self, result):
        report = generate_report(result, FORMAT_GENERIC, engine_id="Test Engine")
        descriptor = next(rule for rule in report["rules"] if rule["id"] == "PRJ001")
        assert descriptor == {
            "id": "PRJ001",
            "name": "Project rule",
            "description": "",
            "engineId": "Test Engine",
            "cleanCodeAttribute": "CONVENTIONAL",
            "type": "CODE_SMELL",
            "severity": "MAJOR",
            "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
        }

    def test_the_enum_values_are_serialised_not_their_repr(self, result):
        # str(SomeStrEnum.X) is "SomeStrEnum.X", which would be invalid here.
        for rule in generate_report(result, FORMAT_GENERIC)["rules"]:
            assert "." not in rule["type"]
            assert "." not in rule["severity"]

    def test_a_severity_overridden_by_the_configuration_is_reported(self, make_project):
        result = Runner(
            make_project(),
            rules=[ProjectRule()],
            config={"rules": {"PRJ001": {"severity": "BLOCKER"}}},
        ).run()
        report = generate_report(result, FORMAT_GENERIC)
        assert report["rules"][0]["severity"] == "BLOCKER"
        assert report["rules"][0]["impacts"][0]["severity"] == "BLOCKER"

    def test_an_empty_run_produces_an_empty_report(self, make_project):
        result = Runner(make_project(), rules=[]).run()
        assert generate_report(result, FORMAT_GENERIC) == {"rules": [], "issues": []}


class TestSarifReport:
    def test_the_report_envelope(self, result):
        report = generate_report(result, FORMAT_SARIF)
        assert report["version"] == "2.1.0"
        assert report["$schema"].endswith("sarif-2.1.0.json")
        driver = report["runs"][0]["tool"]["driver"]
        assert driver["version"] == __version__
        assert [rule["id"] for rule in driver["rules"]] == ["PY001", "PRJ001"]
        assert len(report["runs"][0]["results"]) == 2

    def test_the_rule_descriptor_carries_the_category_as_a_tag(self, result):
        driver = generate_report(result, FORMAT_SARIF)["runs"][0]["tool"]["driver"]
        descriptor = next(rule for rule in driver["rules"] if rule["id"] == "PRJ001")
        assert descriptor["properties"]["tags"] == ["documentation"]
        assert descriptor["shortDescription"] == {"text": "Project rule"}

    def test_the_description_is_plain_text_and_markdown(self, make_project):
        class DocumentedRule(ProjectRule):
            id = "DOC001"
            description = "<p>Use a <code>README.md</code></p>"
            help_uri = "https://example.com/doc"

        result = Runner(make_project(), rules=[DocumentedRule()]).run()
        descriptor = generate_report(result, FORMAT_SARIF)["runs"][0]["tool"]["driver"]["rules"][0]
        assert descriptor["fullDescription"] == {"text": "Use a README.md"}
        assert descriptor["help"]["markdown"] == DocumentedRule.description
        assert descriptor["helpUri"] == "https://example.com/doc"

    def test_a_rule_without_description_has_no_description_fields(self, result):
        driver = generate_report(result, FORMAT_SARIF)["runs"][0]["tool"]["driver"]
        descriptor = next(rule for rule in driver["rules"] if rule["id"] == "PRJ001")
        assert "fullDescription" not in descriptor
    
    def test_rule_help_uri(self, result):
        driver = generate_report(result, FORMAT_SARIF)["runs"][0]["tool"]["driver"]
        descriptor = next(rule for rule in driver["rules"] if rule["id"] == "PRJ001")
        rule = ProjectRule()
        assert "helpUri" in descriptor
        assert descriptor["helpUri"].endswith(f"/rules/{rule.category}/{rule.id}")


class TestFormatSelection:
    @pytest.mark.parametrize("output_format", ["sarif", "SARIF", " Sarif "])
    def test_the_format_name_is_normalised(self, result, output_format):
        assert "runs" in generate_report(result, output_format)

    @pytest.mark.parametrize("output_format", ["saref", "", None, "xml"])
    def test_an_unknown_format_falls_back_on_the_generic_one(
        self, result, output_format, caplog
    ):
        with caplog.at_level(logging.WARNING):
            report = generate_report(result, output_format)
        assert "issues" in report
        assert "Unknown output format" in caplog.text


class TestWriteReport:
    def test_the_report_is_written_as_indented_json(self, tmp_path):
        path = write_report({"issues": []}, tmp_path / "report.json")
        assert json.loads(path.read_text()) == {"issues": []}
        assert path.read_text().endswith("\n")

    def test_missing_parent_folders_are_created(self, tmp_path):
        path = write_report({"issues": []}, tmp_path / "out" / "nested" / "report.json")
        assert path.is_file()

    def test_a_relative_path_works(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert write_report({"issues": []}, "report.json").is_file()
