#!/usr/bin/env python3.11
import os
import json
import logging
import sys

from pathlib import Path


# Custom Formatter to bridge Python Logging with GitHub Workflow Commands
class GitHubActionsFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.ERROR:
            return f"::error file=main.py::{record.getMessage()}"
        if record.levelno == logging.WARNING:
            return f"::warning file=main.py::{record.getMessage()}"
        return record.getMessage()

# Setup logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(GitHubActionsFormatter())
logger.addHandler(handler)coding_best_practices_issues


ENGINE_ID = "Coding BP for OSS Validator"

PATH_TO_CHECK = os.getenv("INPUT_PATH-TO-CHECK", ".")
OUTPUT_FILE = os.getenv("INPUT_OUTPUT-FILE", "coding-best-practices-report.json")
OUTPUT_FORMAT = os.getenv("INPUT_OUTPUT-FORMAT", "generic")
WORKSPACE = os.getenv("GITHUB_WORKSPACE", "/github/workspace")
DEFAULT_ANCHOR_FILE = "coding-best-practices-issues"

RULES_SARIF = {
    "CBP001": {
        "id": "CBP001",
        "shortDescription": {
            "text": "Missing Documentation",
        },
        "fullDescription": {
            "text": "The README.md file is mandatory for project documentation and overview.",
        },
        "properties": {
            "tags": ["maintainability"],
        },
        "helpUri": "https://example.com/docs/governance",
    },
}

RULE_CBP001_DESC = """<p>A <code>README.md</code> file should be included for project documentation and overview.</p>
<p>Software documentation should contain, even briefly, the following information:</p>
<ul>
<li><b>Dependencies and needs</b>, possibly also programmatically (e.g. <code>requirements.txt</code> file, <code>Dockerfile</code>, etc.)</li>
<li><b>Installation/deployment instructions</b>, e.g. command to compile, build, create virtual environment ...</li>
<li><b>How to run the software</b>, including examples</li>
<li><b>Input data</b>, what is needed and how to access or create it</li>
<li><b>Expected output</b>, and how to open/read/understand it</li>
</ul>
"""

# Possible cleanCodeAttribute values, depending on the rule/issue type:
# - Consistency: FORMATTED, CONVENTIONAL, IDENTIFIABLE
# - Intentionality: CLEAR, LOGICAL, COMPLETE, EFFICIENT
# - Adaptability: FOCUSED, DISTINCT, MODULAR, TESTED
# - Responsibility: LAWFUL, TRUSTWORTHY, RESPECTFUL

RULES_GENERIC = {
    "CBP001": {
        "id": "CBP001",
        "name": "Missing Documentation",
        "description": RULE_CBP001_DESC,
        "engineId": ENGINE_ID,
        "cleanCodeAttribute": "CONVENTIONAL",
        "type": "CODE_SMELL",
        "severity": "MINOR",
        "impacts": [
          {
            "softwareQuality": "MAINTAINABILITY",
            "severity": "MEDIUM"
          },
        ],
    },
}


def check_readme_file(target_path):
    # Ensure target_path is absolute for logic but we use "/" for the SARIF URI
    readme_path = os.path.join(target_path, "README.md")

    # Check if README file exists
    if os.path.isfile(readme_path):
        logger.info(f"✅ README.md found in folder {target_path}.")
        return []

    logger.info(f"❌ README.md missing in folder {target_path}.")
    return [{
        "ruleId": "CBP001",
        "engineId": ENGINE_ID,
        "effortMinutes": 60,
        "primaryLocation": {
            "message": f"README.md file missing in the '{target_path}' folder.",
            "filePath": DEFAULT_ANCHOR_FILE,
        },
    }]

    return [{
        "ruleId": "CBP001",
        "level": "warning",
        "message": {
            "text": f"README.md file missing in the '{target_path}' folder."
        },
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": target_path,
                        "description": {
                            "text": "Target folder"
                        }
                    }
                }
            }
        ]
    }]


def generate_sarif_report(issues=[]):
    # Create the rules array using the IDs found in the issues
    unique_ids = dict.fromkeys(i["ruleId"] for i in issues if isinstance(i, dict))
    rules_list = [RULES_SARIF[rid] for rid in unique_ids if rid in RULES_SARIF]
    logger.debug("Rules: %s", rules_list)

    # Online SARIF report validator: https://sarifweb.azurewebsites.net/Validation
    report = {
        "$schema": "https://www.schemastore.org/schemas/json/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodingBestPracticesValidator",
                        "version": "0.1.0",
                        "informationUri": "https://example.com/validator",
                        "rules": rules_list
                    }
                },
                "results": issues
            }
        ]
    }
    return report


def generate_generic_report(issues=[]):
    # Create the rules array using the IDs found in the issues
    unique_ids = dict.fromkeys(i["ruleId"] for i in issues if isinstance(i, dict))
    rules_list = [RULES_GENERIC[rid] for rid in unique_ids if rid in RULES_GENERIC]
    logger.debug("Rules: %s", rules_list)

    return {
        "rules": rules_list,
        "issues": issues,
    }

def run_checks():
    issues = []
    issues.extend(check_readme_file(PATH_TO_CHECK))
    return issues


def run_validator():
    if not os.path.isdir(PATH_TO_CHECK):
        logger.error("Error: %s is not a valid directory.", PATH_TO_CHECK)
        sys.exit(1)

    if not os.path.exists(DEFAULT_ANCHOR_FILE):
        logger.info("Creating default anchor file %s", DEFAULT_ANCHOR_FILE)
        Path(DEFAULT_ANCHOR_FILE).touch()

    issues = run_checks()

    if OUTPUT_FORMAT.lower() == "saref":
        report = generate_sarif_report(issues)
    else:
        report = generate_generic_report(issues)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Successfully saved: %s", OUTPUT_FILE)


if __name__ == "__main__":
    run_validator()