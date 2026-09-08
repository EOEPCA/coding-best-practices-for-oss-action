# rules/documentation/missing_readme.py
import logging

from coding_best_practices_for_oss.core.issue import Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.config import HELP_BASE_URL

logger = logging.getLogger(__name__)

DESCRIPTION = """<p>A <code>README</code> file (md, rst, txt) should be included for project documentation and overview.</p>
<p>Software documentation should contain, even briefly, the following information:</p>
<ul>
<li><b>Dependencies and needs</b>, possibly also programmatically (e.g. <code>requirements.txt</code> file, <code>Dockerfile</code>, etc.)</li>
<li><b>Installation/deployment instructions</b>, e.g. command to compile, build, create virtual environment ...</li>
<li><b>How to run the software</b>, including examples</li>
<li><b>Input data</b>, what is needed and how to access or create it</li>
<li><b>Expected output</b>, and how to open/read/understand it</li>
</ul>
"""


class MissingReadmeRule(Rule):
    id = "DOC001"
    name = "Missing Documentation"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "documentation"
    scope = PROJECT_SCOPE
    effort_minutes = 60
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)

    # Accepted spellings, in order of preference.
    readme_names = ("README.md", "README.rst", "README.txt", "README")

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        readme = context.find_file(*self.readme_names)
        if readme:
            logger.info("✅ %s found in folder %s", readme.name, context.display_path)
            return []

        logger.info("❌ README (md, rst, txt) file missing in folder %s", context.display_path)
        # No file to point at: the issue lands on the anchor file.
        return [context.issue(f"README (md, rst, txt) file missing in the '{context.display_path}' folder.")]
