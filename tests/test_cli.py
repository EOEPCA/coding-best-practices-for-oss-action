import json
import logging

import pytest

from coding_best_practices_for_oss.cli import (
    GitHubActionsFormatter,
    build_parser,
    configure_logging,
    main,
)


@pytest.fixture
def project(make_project):
    """A project without README, so that DOC001 reports one issue."""
    return make_project({"src/app.py": "x = 1\n"})


def run_cli(project, report, *extra):
    """Run the CLI on a project, return (exit code, parsed report)."""
    code = main(
        ["--path-to-check", str(project), "--output-file", str(report), *extra]
    )
    return code, json.loads(report.read_text()) if report.is_file() else None


class TestMain:
    def test_the_generic_report_is_written(self, project, tmp_path):
        code, report = run_cli(project, tmp_path / "report.json")
        assert code == 0
        assert [issue["ruleId"] for issue in report["issues"]] == ["DOC001"]
        assert report["rules"][0]["engineId"] == "Coding BP for OSS Validator"

    def test_the_sarif_report_is_written(self, project, tmp_path):
        code, report = run_cli(project, tmp_path / "report.json", "--output-format", "sarif")
        assert code == 0
        assert report["version"] == "2.1.0"
        assert report["runs"][0]["results"][0]["ruleId"] == "DOC001"

    def test_an_unknown_format_still_produces_a_report(self, project, tmp_path):
        code, report = run_cli(project, tmp_path / "report.json", "--output-format", "saref")
        assert code == 0
        assert "issues" in report

    def test_an_invalid_directory_exits_with_one(self, tmp_path):
        assert main(["--path-to-check", str(tmp_path / "nope")]) == 1

    def test_an_unwritable_report_exits_with_one(self, project, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")
        assert main(
            ["--path-to-check", str(project), "--output-file", str(blocker / "report.json")]
        ) == 1

    def test_the_anchor_file_is_created_in_the_checked_project(self, project, tmp_path):
        run_cli(project, tmp_path / "report.json", "--default-anchor-file", "issues.md")
        assert (project / "issues.md").is_file()

    def test_the_configuration_file_is_applied(self, project, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("rules:\n  DOC001:\n    enabled: false\n")
        code, report = run_cli(project, tmp_path / "report.json", "--config-file", str(config))
        assert code == 0
        assert report == {"rules": [], "issues": []}

    def test_a_missing_configuration_file_is_ignored(self, project, tmp_path, caplog):
        code, report = run_cli(
            project, tmp_path / "report.json", "--config-file", str(tmp_path / "nope.yaml")
        )
        assert code == 0 and report["issues"]

    def test_fail_on_issues_exits_with_two(self, project, tmp_path):
        code, _ = run_cli(project, tmp_path / "report.json", "--fail-on-issues")
        assert code == 2

    def test_fail_on_issues_exits_with_zero_on_a_clean_project(self, make_project, tmp_path):
        clean = make_project({"README.md": "# Demo\n"})
        code, report = run_cli(clean, tmp_path / "report.json", "--fail-on-issues")
        assert code == 0
        assert report["issues"] == []


class TestParser:
    def test_the_defaults_come_from_the_action_inputs(self, monkeypatch):
        # config is read at import time, so patch the module the CLI uses.
        from coding_best_practices_for_oss import cli

        monkeypatch.setattr(cli.config, "PATH_TO_CHECK", "/somewhere")
        args = cli.build_parser().parse_args([])
        assert args.path_to_check == "/somewhere"

    def test_the_flags_override_the_defaults(self):
        args = build_parser().parse_args(["--path-to-check", "here", "--verbose"])
        assert (args.path_to_check, args.verbose) == ("here", True)

    def test_issues_do_not_fail_the_run_by_default(self):
        assert build_parser().parse_args([]).fail_on_issues is False


class TestLogging:
    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (logging.ERROR, "::error::boom"),
            (logging.WARNING, "::warning::boom"),
            (logging.INFO, "boom"),
            (logging.DEBUG, "boom"),
        ],
    )
    def test_the_workflow_commands_are_emitted_by_level(self, level, expected):
        record = logging.LogRecord("test", level, "cli.py", 1, "boom", None, None)
        assert GitHubActionsFormatter().format(record) == expected

    def test_the_message_arguments_are_interpolated(self):
        record = logging.LogRecord("test", logging.ERROR, "cli.py", 1, "a %s", ("b",), None)
        assert GitHubActionsFormatter().format(record) == "::error::a b"

    def test_the_annotations_are_only_used_in_github_actions(self, capsys):
        configure_logging(github_actions=False)
        logging.getLogger("test").warning("plain")
        assert "::warning::" not in capsys.readouterr().out

        configure_logging(github_actions=True)
        logging.getLogger("test").warning("annotated")
        assert "::warning::annotated" in capsys.readouterr().out

    def test_configuring_twice_does_not_duplicate_the_output(self, capsys):
        configure_logging(github_actions=False)
        configure_logging(github_actions=False)
        logging.getLogger("test").info("once")
        assert capsys.readouterr().out.count("once") == 1

    def test_verbose_enables_the_debug_level(self):
        configure_logging(verbose=True, github_actions=False)
        assert logging.getLogger().level == logging.DEBUG
