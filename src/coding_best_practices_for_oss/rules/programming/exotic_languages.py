# rules/programming/missing_readme.py
import json
import logging

from coding_best_practices_for_oss.core.issue import Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.config import HELP_BASE_URL
from coding_best_practices_for_oss.rules.programming.too_many_languages import TooManyLanguagesRule

logger = logging.getLogger(__name__)

DESCRIPTION = """<p>To increase maintainability, it is advised to avoid using data formats and
programming languages lacking adoption, documentation, or regular fixes and release cycles.</p>
"""


class ExoticLanguagesRule(Rule):
    id = "LNG001"
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

        all_languages = [item["language"] for item in output["languages_summary"]]
        logger.debug("Formats and languages used in %s: %s", context.display_path, ", ".join(all_languages))
        
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

        logger.info("✅ No exotic languages used in %s", context.display_path)
        return []