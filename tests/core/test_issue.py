import pytest

from coding_best_practices_for_oss.core.issue import (
    Impact,
    ImpactSeverity,
    Issue,
    IssueType,
    Location,
    Severity,
    SoftwareQuality,
)


class TestSeverity:
    @pytest.mark.parametrize("value", ["MINOR", "minor", " Minor ", Severity.MINOR])
    def test_parse_accepts_enums_and_any_casing(self, value):
        assert Severity.parse(value) is Severity.MINOR

    def test_parse_rejects_an_unknown_severity(self):
        with pytest.raises(ValueError, match="Unknown severity"):
            Severity.parse("WHATEVER")

    @pytest.mark.parametrize(
        ("severity", "level"),
        [
            (Severity.INFO, "note"),
            (Severity.MINOR, "warning"),
            (Severity.MAJOR, "warning"),
            (Severity.CRITICAL, "error"),
            (Severity.BLOCKER, "error"),
        ],
    )
    def test_sarif_level(self, severity, level):
        assert severity.sarif_level == level


class TestLocation:
    def test_columns_are_zero_based_in_the_generic_format(self):
        location = Location("a.py", start_line=2, end_line=3, start_column=5, end_column=9)
        assert location.text_range() == {
            "startLine": 2,
            "endLine": 3,
            "startColumn": 4,
            "endColumn": 8,
        }

    def test_columns_stay_one_based_in_sarif(self):
        location = Location("a.py", start_line=2, start_column=5)
        assert location.region() == {"startLine": 2, "startColumn": 5}

    def test_a_location_without_line_has_no_range(self):
        location = Location("anchor.md")
        assert location.text_range() is None
        assert location.region() is None
        assert "textRange" not in location.to_generic()
        assert "region" not in location.to_sarif()["physicalLocation"]

    def test_the_first_column_does_not_become_negative(self):
        assert Location("a.py", start_line=1, start_column=0).text_range()["startColumn"] == 0


class TestIssue:
    def test_the_impact_defaults_to_the_type_and_severity(self):
        issue = Issue("R1", "m", Location("a.py"), Severity.CRITICAL, IssueType.VULNERABILITY)
        assert issue.impacts == (Impact(SoftwareQuality.SECURITY, ImpactSeverity.HIGH),)

    def test_an_explicit_impact_is_kept(self):
        impact = Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.BLOCKER)
        assert Issue("R1", "m", Location("a.py"), impacts=[impact]).impacts == (impact,)

    def test_a_string_severity_is_parsed(self):
        assert Issue("R1", "m", Location("a.py"), severity="critical").severity is Severity.CRITICAL

    def test_to_generic(self):
        issue = Issue(
            "R1",
            "message",
            Location("src/a.py", start_line=3),
            effort_minutes=15,
            secondary_locations=[Location("src/b.py", message="see also", start_line=1)],
        )
        assert issue.to_generic("Engine") == {
            "ruleId": "R1",
            "engineId": "Engine",
            "primaryLocation": {
                "message": "message",
                "filePath": "src/a.py",
                "textRange": {"startLine": 3},
            },
            "effortMinutes": 15,
            "secondaryLocations": [
                {
                    "message": "see also",
                    "filePath": "src/b.py",
                    "textRange": {"startLine": 1},
                }
            ],
        }

    def test_to_generic_omits_an_unset_effort(self):
        assert "effortMinutes" not in Issue("R1", "m", Location("a.py")).to_generic()

    def test_the_issue_engine_id_wins_over_the_default_one(self):
        issue = Issue("R1", "m", Location("a.py"), engine_id="Mine")
        assert issue.to_generic("Default")["engineId"] == "Mine"

    def test_to_sarif(self):
        issue = Issue("R1", "message", Location("src/a.py", start_line=3, start_column=2))
        assert issue.to_sarif() == {
            "ruleId": "R1",
            "level": "warning",
            "message": {"text": "message"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "src/a.py"},
                        "region": {"startLine": 3, "startColumn": 2},
                    }
                }
            ],
        }

    def test_to_sarif_keeps_a_location_message_that_differs(self):
        issue = Issue("R1", "message", Location("a.py", message="something else"))
        assert issue.to_sarif()["locations"][0]["message"] == {"text": "something else"}

    def test_issues_sort_by_file_then_position(self):
        issues = [
            Issue("R1", "m", Location("b.py", start_line=1)),
            Issue("R1", "m", Location("a.py", start_line=9)),
            Issue("R1", "m", Location("a.py", start_line=2)),
        ]
        ordered = sorted(issues, key=lambda issue: issue.sort_key)
        assert [(i.file_path, i.location.start_line) for i in ordered] == [
            ("a.py", 2),
            ("a.py", 9),
            ("b.py", 1),
        ]
