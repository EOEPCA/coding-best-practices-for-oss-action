# rules/programming/handle_exceptions.py
#
# Handle Exceptions Gracefully
#
from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.log_tools import getLogger
from coding_best_practices_for_oss.utils.ruff_tools import exec_ruff as ruff, new_issue, violation_string


RULE_ID = "RES003"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Handle exceptions gracefully:</p>
- No blind exceptions: BLE001 (flake8-blind-except)
- Silent error suppression: S110 (try-except-pass)
- Ignoring errors in loops: S112 (try-except-continue)
- Unqualified except blocks: E722 (bare-except)
- Broken finally blocks: B012 (jump-statement-in-finally, from flake8-bugbear)
"""

class HandleExceptionsRule(Rule):
    id = RULE_ID
    name = "Handle exceptions gracefully"
    description = DESCRIPTION
    default_severity = "MAJOR"
    category = "programming"
    dependencies = ["ruff"]  # ruff has rules to detect this: BLE, S110, S112, E722, B012
    scope = PROJECT_SCOPE
    effort_minutes = 10
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)

    def check(self, context):
        logger.debug("Execution context: %s", context.rule_settings)
        # Use "ruff" and restrict to specific rules
        violations = ruff(context.path(), select=["BLE", "S110", "S112", "E722", "B012"])
        issues = []
        if violations:
            logger.info("❌ Found %s mishandled exceptions:", len(violations))
            for v in violations:
                logger.info(violation_string(v))
                issues.append(new_issue(context, v))
        else:
            logger.info("✅ All exceptions handled gracefully.")
            # Return an info-level issue to inform the user about the test result
            issues = [
                context.issue("All exceptions handled gracefully.", severity=Severity.INFO)
            ]
        return issues