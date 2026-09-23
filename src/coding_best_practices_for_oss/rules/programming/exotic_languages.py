# rules/programming/exotic_languages.py
import json

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.config import HELP_BASE_URL
from coding_best_practices_for_oss.rules.programming.too_many_languages import TooManyLanguagesRule
from coding_best_practices_for_oss.utils.log_tools import getLogger


RULE_ID = "LNG001"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>To increase maintainability, it is advised to avoid using data formats and
programming languages lacking adoption, documentation, or regular fixes and release cycles.</p>
"""


class ExoticLanguagesRule(Rule):
    id = RULE_ID
    name = "Exotic Languages"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "programming"
    dependencies = ["ai"]
    scope = PROJECT_SCOPE
    effort_minutes = 600
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)


    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        # Use AI to detect the language of the programming files
        # The same prompt is used by several rules
        output = TooManyLanguagesRule._main(self, context)
        logger.debug("Result: %s", json.dumps(output, indent=2))
        # Stop here if no files of interest have been found
        if output == [] or output is None:
            return []

        languages = [item["language"] for item in output["languages_summary"]]
        logger.debug("Formats and languages used in %s: %s", context.display_path, ", ".join(languages))
        
        exotic_languages = [
            item["language"] for item in output["languages_summary"] if item["popularity"] == "exotic"
        ]
        if exotic_languages and len(exotic_languages) > 0:
            logger.info(
                "❌ Exotic languages used in %s: %s", context.display_path, ", ".join(exotic_languages)
            )
            return [
                context.issue(
                    f"Exotic programming languages used in '{context.display_path}': {', '.join(exotic_languages)}"
                )
            ]

        lang_list = [f"{item['language']} ({item['popularity']})" for item in output["languages_summary"]]
        logger.info("✅ No exotic languages used in %s: %s", context.display_path, ', '.join(lang_list))
        # Return an info-level issue to inform the user about the test result
        return [
            context.issue(
                f"No exotic languages used: {', '.join(lang_list)}",
                severity=Severity.INFO,
            )
        ]