# rules/documentation/python_docstrings.py
#
# Python classes and functions must have a docstring (syntactic check with ruff).
# The semantic check of the docstrings content is done by DOC006 (python_docstrings_sem.py).
#
from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.log_tools import getLogger
from coding_best_practices_for_oss.utils.ruff_tools import exec_ruff as ruff, new_issue, violation_string


RULE_ID = "DOC005"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Public Python classes, methods and functions must be documented with a docstring,
i.e. a triple-quoted string immediately following their declaration. Empty docstrings do not count.</p>
"""

# Ruff (pydocstyle) checks applied by default:
# - D101: Missing docstring in public class
# - D102: Missing docstring in public method
# - D103: Missing docstring in public function
# - D106: Missing docstring in public nested class
# - D419: Docstring is empty
# Not applied by default, but may be added with the "select" rule setting:
# - D100: Missing docstring in public module
# - D104: Missing docstring in public package (__init__.py)
# - D105: Missing docstring in magic method (__repr__, __eq__, ...)
# - D107: Missing docstring in __init__ (commonly documented in the class docstring)
# Ruff never reports private (_name) nor nested functions.
DEFAULT_SELECT = ["D101", "D102", "D103", "D106", "D419"]


class PythonDocstringsRule(Rule):
    id = RULE_ID
    name = "Python classes and functions must have a docstring"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "documentation"
    dependencies = ["ruff"]  # ruff implements the pydocstyle "D" rules
    scope = PROJECT_SCOPE
    effort_minutes = 5
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)
    clean_code_attribute = "COMPLETE"

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        select = context.rule_setting("select", DEFAULT_SELECT)
        # Exit code 1 is normal when violations are found, not an error
        violations = ruff(context.path(), select=select)
        issues = []
        if violations:
            logger.info("❌ Found %s missing or empty docstring(s):", len(violations))
            for v in violations:
                logger.info(violation_string(v))
                issues.append(new_issue(context, v))
        else:
            logger.info("✅ No missing or empty docstrings found.")
            # Return an info-level issue to inform the user about the test result
            issues = [
                context.issue("All public classes and functions have a docstring", severity=Severity.INFO)
            ]
        return issues
