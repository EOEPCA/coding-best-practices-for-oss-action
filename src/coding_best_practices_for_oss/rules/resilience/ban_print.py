# rules/programming/ban_print.py
#
# Do not use print()/pprint() in Python code
#
from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.log_tools import getLogger
from coding_best_practices_for_oss.utils.ruff_tools import exec_ruff as ruff, new_issue, violation_string


RULE_ID = "RES001"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Calls to "print()/pprint()" but be banned. The Python logging library must be used instead.</p>
"""

class BanPrintRule(Rule):
    id = RULE_ID
    name = "No print calls"
    description = DESCRIPTION
    default_severity = "MAJOR"
    category = "programming"
    dependencies = ["ruff"]  # ruff has rules to detect the use of print() and pprint()
    scope = PROJECT_SCOPE
    effort_minutes = 10
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        # Use "ruff" and restrict to rules "T201" for print() and "T203" for pprint()
        # Output the results in JSON
        # Exit code 1 is normal, not an error
        violations = ruff(context.path(), select="T20")
        issues = []
        if violations:
            # Keeping this "print()" call for testing purpose
            print(f"Keeping this 'print()' call for testing purpose")
            logger.info("❌ Found %s print()/pprint() usage(s):", len(violations))
            for v in violations:
                logger.info(violation_string(v))
                issues.append(new_issue(context, v))
        else:
            logger.info("✅ No print()/pprint() usage found.")
            # Return an info-level issue to inform the user about the test result
            issues = [
                context.issue("Usage of print()/pprint() not found", severity=Severity.INFO)
            ]
        return issues