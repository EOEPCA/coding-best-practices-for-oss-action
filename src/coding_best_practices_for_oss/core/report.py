# Turns a RunResult into the JSON report the action publishes.
#
# These formats are supported:
#   - "text":    Human readable plain text format
#   - "generic": SonarQube generic issue import format
#   - "sarif":   SARIF 2.1.0 (validator: https://sarifweb.azurewebsites.net/Validation)
#
# In both formats the report describes only the rules that reported an issue,
# and the rule descriptions come from the Rule classes themselves, so adding a
# rule never means editing this module.
import html
import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any, Sequence, Union

from coding_best_practices_for_oss import __version__
from coding_best_practices_for_oss.core.issue import Issue
from coding_best_practices_for_oss.core.rule import Rule
from coding_best_practices_for_oss.core.runner import RunResult

logger = logging.getLogger(__name__)

FORMAT_TEXT = "text"
FORMAT_GENERIC = "generic"
FORMAT_SARIF = "sarif"
SUPPORTED_FORMATS = (FORMAT_TEXT, FORMAT_GENERIC, FORMAT_SARIF)

TOOL_NAME = "CodingBestPracticesValidator"
TOOL_INFORMATION_URI = "https://github.com/EOEPCA/coding-best-practices-for-oss"

SARIF_SCHEMA = "https://www.schemastore.org/schemas/json/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

Report = Union[dict[str, Any], str]


def plain_text(text: str) -> str:
    """Strip the HTML markup of a rule description.

    Rule descriptions are HTML because that is what SonarQube renders, while
    SARIF description fields are plain text.
    """
    return _WHITESPACE.sub(" ", html.unescape(_HTML_TAG.sub(" ", text or ""))).strip()


def generate_report(
    result: RunResult,
    output_format: str = FORMAT_GENERIC,
    *,
    engine_id: str = "",
) -> dict[str, Any]:
    """Build the report in the requested format (generic if unknown)."""
    normalised = (output_format or "").strip().lower()
    if normalised not in SUPPORTED_FORMATS:
        logger.warning(
            "Unknown output format %r, falling back to %r. Supported formats: %s.",
            output_format,
            FORMAT_GENERIC,
            ", ".join(SUPPORTED_FORMATS),
        )
        normalised = FORMAT_GENERIC

    if normalised == FORMAT_SARIF:
        return generate_sarif_report(result)
    if normalised == FORMAT_TEXT:
        return generate_text_report(result)
    return generate_generic_report(result, engine_id=engine_id)


def write_report(report: Report, output_file: str | Path) -> Path:
    """Write the report, creating parent folders if needed.
 
    Dict reports (generic, sarif) are written as indented JSON; string
    reports (text) are written as-is.
    """
    path = Path(output_file)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(report, str):
        path.write_text(report if report.endswith("\n") else report + "\n", encoding="utf-8")
        return path

    with path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return path


# -- SonarQube generic issue import format ----------------------------------


def generate_generic_report(result: RunResult, *, engine_id: str = "") -> dict[str, Any]:
    issues_by_rule = _issues_by_rule(result.issues)
    rules = [
        _generic_rule(rule, issues_by_rule.get(rule.id, ()), engine_id)
        for rule in result.triggered_rules
    ]
    return {
        "rules": rules,
        "issues": [issue.to_generic(engine_id, result.display_path) for issue in result.issues],
    }


def _generic_rule(rule: Rule, issues: Sequence[Issue], engine_id: str) -> dict[str, Any]:
    """Rule descriptor, using the severity/impacts the issues were raised with.

    Severity and impacts are read back from the issues so that a severity
    overridden in the configuration file is reflected in the report.
    """
    sample = issues[0] if issues else None
    severity = sample.severity if sample else rule.default_severity
    issue_type = sample.issue_type if sample else rule.issue_type
    impacts = sample.impacts if sample else rule.impacts

    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "engineId": (sample.engine_id if sample and sample.engine_id else engine_id),
        "cleanCodeAttribute": rule.clean_code_attribute,
        "type": _value(issue_type),
        "severity": _value(severity),
        "impacts": [impact.to_generic() for impact in impacts],
    }


def _value(value: Any) -> str:
    """Enum value or plain string: `str(SomeStrEnum.X)` is not the value."""
    return value.value if isinstance(value, Enum) else str(value)


# -- SARIF 2.1.0 -------------------------------------------------------------


def generate_sarif_report(result: RunResult) -> dict[str, Any]:
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": TOOL_NAME,
                        "version": __version__,
                        "informationUri": TOOL_INFORMATION_URI,
                        "rules": [_sarif_rule(rule) for rule in result.triggered_rules],
                    }
                },
                "results": [issue.to_sarif(result.display_path) for issue in result.issues],
            }
        ],
    }


def _sarif_rule(rule: Rule) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "id": rule.id,
        "name": rule.name or type(rule).__name__,
        "shortDescription": {"text": rule.name},
        "properties": {"tags": [rule.category] if rule.category else []},
    }
    description = plain_text(rule.description)
    if description:
        descriptor["fullDescription"] = {"text": description}
        descriptor["help"] = {"text": description, "markdown": rule.description}
    if rule.help_uri:
        descriptor["helpUri"] = rule.help_uri
    return descriptor


# -- Plain text ---------------------------------------------------------


def generate_text_report(result: RunResult) -> str:
    """Human-readable rendering, grouped by rule.
 
    Works directly from `result.issues` (Issue objects) rather than the
    generic dict, since Issue.to_generic() returns only a location fragment
    (message/filePath/textRange) and carries no ruleId of its own.
    """
    issues_by_rule = _issues_by_rule(result.issues)
 
    lines: list[str] = []
    title = f"{TOOL_NAME} report"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    lines.append(f"Issues found: {len(result.issues)}")
 
    if result.issues:
        counts: dict[str, int] = {}
        for rule in result.triggered_rules:
            rule_issues = issues_by_rule.get(rule.id, ())
            if not rule_issues:
                continue
            severity = _value(rule_issues[0].severity)
            counts[severity] = counts.get(severity, 0) + len(rule_issues)
        for severity, count in sorted(counts.items()):
            lines.append(f"  {severity}: {count}")
    lines.append("")
 
    if not result.issues:
        lines.append("No issues found.")
        return "\n".join(lines) + "\n"
 
    for rule in result.triggered_rules:
        rule_issues = issues_by_rule.get(rule.id, ())
        if not rule_issues:
            continue
 
        severity = _value(rule_issues[0].severity)
 
        lines.append("-" * 70)
        lines.append(f"[{rule.id}] {rule.name} ({severity})")
 
        description = plain_text(rule.description)
        if description:
            lines.append(f"  {description}")
        lines.append("")
 
        for issue in rule_issues:
            location = issue.to_generic(target_path=result.display_path)
            location = location.get("primaryLocation", location)
            position = location.get("filePath", "(no file path)")
 
            text_range = location.get("textRange") or {}
            if "startLine" in text_range:
                position += f":{text_range['startLine']}"
                if "startColumn" in text_range:
                    # text_range() stores 0-based columns (SonarQube
                    # convention); show 1-based here to match what editors
                    # and terminals normally display.
                    position += f":{text_range['startColumn'] + 1}"
 
            # If position is the default anchor file, there is no point to output it
            message = location.get("message", "")
            if position == result.anchor_file:
                if message:
                    lines.append(f"  - {message}")
            else:
                lines.append(f"  - {position}")
                if message:
                    lines.append(f"    {message}")
        lines.append("")
 
    return "\n".join(lines) + "\n"
 

    # def _text_rule(rule: Rule) -> str:
    #     pass
    
    # def _text_issue(issue: Issue) -> str:
    #     pass


# -----------------------------------------------------------------------


def _issues_by_rule(issues: Sequence[Issue]) -> dict[str, list[Issue]]:
    grouped: dict[str, list[Issue]] = {}
    for issue in issues:
        grouped.setdefault(issue.rule_id, []).append(issue)
    return grouped
