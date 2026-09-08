# rules/programming/missing_readme.py
import json
import logging
import os
import sys

from coding_best_practices_for_oss.core.issue import Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.file_tools import find_text_files, extract_head
from coding_best_practices_for_oss.utils.ml_tools import query_model


logger = logging.getLogger(__name__)

DESCRIPTION = """<p>To increase maintainability, it is advised to avoid using too many different
programming languages and data formats in the same project.</p>
"""


class TooManyLanguagesRule(Rule):
    id = "LNG002"
    name = "Too Many Languages"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "programming"
    dependencies = ["ai"]
    scope = PROJECT_SCOPE
    effort_minutes = 600
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)

    @staticmethod
    def _build_prompt(file_heads: list[tuple[str, str]]) -> str:
        """file_heads: list of (relative_path, head_text) tuples."""
        entries = []
        for rel_path, head in file_heads:
            entries.append(f"### File: {rel_path}\n```\n{head}\n```\n")
        joined = "\n".join(entries)

        #You are analyzing a codebase, not the structure or the purpose of the files.

        return f"""You are analyzing a codebase. For each file below (identified by its
        relative path and the first few lines of its content), identify the
        programming language or the markup language it is written in.

        Then, across all files, produce a deduplicated list of the distinct
        languages detected, each with a popularity classification:
        - "popular": widely used, large ecosystem (e.g. Shell, Python, JavaScript, Java, Go, C++, JSON, JSON Schema, YAML, TOML)
        - "moderate": established but smaller community (e.g. Rust, Kotlin, Scala, R)
        - "exotic": niche, domain-specific, or rarely used outside specific contexts
            (e.g. Zig, Nim, INTERCAL, a custom DSL, esoteric languages)
        
        In languages_summary, indicate the type to each language:
        - "markup": usually only contain text or data (e.g. Markdown, RestructuredText, HTML)
        - "code": usually contains source code
        - "configuration": usually contains structured data (e.g. JSON, JSON Schema, YAML, TOML)

        Do not combine multiple languages when they are identified in the same file.
        Use multiple entries in that case.

        Respond ONLY with a JSON object (no markdown fences, no preamble) in this
        exact shape:

        {{
        "files": [
            {{
            "path": "relative/path/to/file",
            "language": "detected language name",
            "confidence": "high" | "medium" | "low"
            }}
        ],
        "languages_summary": [
            {{
            "language": "language name",
            "popularity": "popular" | "moderate" | "exotic",
            "file_count": <number of files detected as this language>,
            "type": "markup" | "code" | "configuration",
            }}
        ]
        }}

        If a file's language cannot be determined (e.g. plain text, config format
        with no clear language, empty file), set "language" to "unknown" and
        "confidence" to "low", and do not include "unknown" in languages_summary.

        Files to analyze:

        {joined}
        """

    def _main(self, context):
        logger.debug("%s - Scanning %s ...", self.id, context.display_path)
        max_files = context.rule_setting("max_files", 20)
        lines = context.rule_setting("lines", 5)
        file_paths = list(find_text_files(context.path()))
        if not file_paths:
            logger.info("No non-binary files of interest found.")
            return []
        if len(file_paths) > max_files:
            logger.info(f"Found {len(file_paths)} files; will scan them in chucks with --max-files={max_files}")
            file_paths = file_paths[: max_files]

        file_heads = []
        for path in file_paths:
            rel_path = str(path.relative_to(context.path()))
            head = extract_head(path, lines)
            if head.strip():  # skip empty files
                file_heads.append((rel_path, head))

        logger.debug(f"Extracted heads from {len(file_heads)} file(s) — sending to AI for analysis...\n")

        prompt = TooManyLanguagesRule._build_prompt(file_heads)
        try:
            result = query_model(prompt)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[ERROR] Could not parse model response as JSON: {e}", file=sys.stderr)

        return []

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        # A None value means the corresponding severity is not used
        warning_threshold = context.rule_setting("warning_threshold", 10)
        error_threshold = context.rule_setting("error_threshold", None)
        critical_threshold = context.rule_setting("critical_threshold", None)
        
        output = self._main(context)
        logger.debug("Result: %s", json.dumps(output, indent=2))
        # Stop here if no files of interest have been found
        if output == [] or output is None:
            return []

        #language_count = sum(item["file_count"] for item in output["languages_summary"])
        language_count = len(output["languages_summary"])
        logger.info("Detected %s different languages used in '%s'", language_count, context.display_path)

        # Check thresholds for decreasing severities
        if critical_threshold and language_count >= critical_threshold:
            logger.info(
                "❌ Languages count: %s > %s. Critical threshold reached in '%s'",
                language_count,
                critical_threshold,
                context.display_path,
            )
            return [
                context.issue(
                    f"Critical: Too many languages used in folder '{context.display_path}'"
                    f" ({language_count} > {critical_threshold})"
                )
            ]
        if error_threshold and language_count >= error_threshold:
            logger.info(
                "❌ Languages count: %s > %s. Error threshold reached in '%s'",
                language_count,
                error_threshold,
                context.display_path,
            )
            return [
                context.issue(
                    f"Error: Too many languages used in folder '{context.display_path}'"
                    f" ({language_count} > {error_threshold})"
                )
            ]
        if warning_threshold and language_count >= warning_threshold:
            logger.info(
                "❌ Languages count: %s > %s. Warning threshold reached in '%s'",
                language_count,
                warning_threshold,
                context.display_path,
            )
            return [
                context.issue(
                    f"Warning: Too many languages used in folder '{context.display_path}'"
                    f" ({language_count} > {warning_threshold})"
                )
            ]

        logger.info(
            "✅ %s: Identified %s different languages in '%s' (fine)",
            self.name,
            language_count,
            context.display_path,
        )
        return []
