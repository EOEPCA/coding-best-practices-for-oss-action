# rules/programming/use_logging.py
#
# Log the errors, log the progress
#
import json
import logging

from pathlib import Path

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.ruff_tools import exec_ruff as ruff


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
        #report = self._check_print_usage(context.path())
        violations = ruff(context.path(), select="T20")
        issues = []
        if violations:
            # Keeping this "print()" call for testing purpose
            print(f"❌ Found {len(violations)} print()/pprint() usage(s):")
            logging.info("❌ Found %s print()/pprint() usage(s):", len(violations))
            for v in violations:
                logging.info("%s:%s:%s [ruff %s] %s", v['file'], v['line'], v['column'], v['code'], v['message'])
                issues.append(self._new_issue(context, v))
        else:
            logging.info("✅ No print()/pprint() usage found.")
            # Return an info-level issue to inform the user about the test result
            issues = [
                context.issue("Usage of print()/pprint() not found", severity=Severity.INFO)
            ]
        return issues