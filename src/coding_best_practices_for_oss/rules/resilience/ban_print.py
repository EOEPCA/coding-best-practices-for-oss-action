# rules/programming/use_logging.py
#
# Log the errors, log the progress
#
import json
import logging
import os
import subprocess
import sys

from pathlib import Path

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.file_tools import find_text_files, extract_head
from coding_best_practices_for_oss.utils.ai_tools import query_model


logger = logging.getLogger(__name__)

DESCRIPTION = """<p>Calls to "print()/pprint()" but be banned. The Python logging library must be used instead.</p>
"""

class BanPrintRule(Rule):
    id = "RES001"
    name = "No print calls"
    description = DESCRIPTION
    default_severity = "MAJOR"
    category = "programming"
    dependencies = ["ruff"]  # ruff has rules to detect the use of print() and pprint()
    scope = PROJECT_SCOPE
    effort_minutes = 10
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)

    @staticmethod
    def _check_print_usage(project_path: str) -> dict:
        """
        Run Ruff against a project to detect usage of print() (and pprint()).

        Args:
            project_path (str): Path to the project/folder to check.

        Returns:
            dict: {
                "uses_print": bool,
                "violations": [
                    {"file": str, "line": int, "column": int, "code": str, "message": str},
                    ...
                ],
            }

        Raises:
            FileNotFoundError: if `ruff` isn't installed / not found on PATH.
            RuntimeError: if Ruff's output can't be parsed as JSON.
        """
        project_path = str(Path(project_path).resolve())

        try:
            result = subprocess.run(
                ["ruff", "check", "--select", "T20", "--output-format", "json", project_path],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as e:
            raise FileNotFoundError(
                "ruff executable not found. Install it with: pip install ruff --break-system-packages"
            ) from e

        # Ruff exits with code 1 when it finds violations — that's expected, not an error.
        # Only treat it as a real failure if there's no valid JSON in stdout at all.
        try:
            violations_raw = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse Ruff output as JSON: {result.stderr}") from e

        violations = [
            {
                "file": v["filename"],
                "line": v["location"]["row"],
                "column": v["location"]["column"],
                "code": v["code"],
                "message": v["message"],
            }
            for v in violations_raw
        ]

        return {
            "uses_print": len(violations) > 0,
            "violations": violations,
        }

    @staticmethod
    def _new_issue(context, v: dict = {}):
        return context.issue(
            v["message"],
            #severity=Severity.MINOR,
            line=v["line"],
            column=v["column"],
            file_path=v["file"],
        )

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        # Use "ruff" and restrict to rules "T201" for print() and "T203" for pprint()
        # Output the results in JSON
        # Exit code 1 is normal, not an error
        report = self._check_print_usage(context.path())
        issues = []
        if report["uses_print"]:
            # Keeping this "print()" call for testing purpose
            print(f"❌ Found {len(report['violations'])} print()/pprint() usage(s):")
            logging.info("❌ Found %s print()/pprint() usage(s):", len(report['violations']))
            for v in report["violations"]:
                logging.info("%s:%s:%s [ruff %s] %s", v['file'], v['line'], v['column'], v['code'], v['message'])
                issues.append(self._new_issue(context, v))
                logging.info("")
        else:
            logging.info("✅ No print()/pprint() usage found.")
            # Return an info-level issue to inform the user about the test result
            issues = [
                context.issue("Usage of print()/pprint() not found", severity=Severity.INFO)
            ]
        return issues