# rules/programming/too_many_languages.py
import json
import os
import sys

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.file_tools import find_text_files, extract_head
from coding_best_practices_for_oss.utils.ai_tools import query_model
from coding_best_practices_for_oss.utils.log_tools import getLogger


RULE_ID = "LNG002"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>To increase maintainability, it is advised to avoid using too many different
programming languages and data formats in the same project.</p>
"""

DEFAULT_MAX_FILES = 20
DEFAULT_LINES_TO_EXTRACT = 5

# Priority order for categorical fields when merging language summaries
POPULARITY_PRIORITY = {"popular": 3, "moderate": 2, "exotic": 1}
TYPE_PRIORITY = {"code": 3, "markup": 2, "configuration": 1}


class TooManyLanguagesRule(Rule):
    id = RULE_ID
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
        for relpath, head in file_heads:
            entries.append(f"### File: {relpath}\n```\n{head}\n```\n")
        joined = "\n".join(entries)

        #You are analyzing a codebase, not the structure or the purpose of the files.

        return f"""You are analyzing a codebase. For each file below (identified by its
        relative path and the first few lines of its content), identify the
        programming language or the markup language it is written in.

        Then, across all files, produce a deduplicated list of the distinct
        languages detected, each with a popularity classification:
        - "popular": widely used, large ecosystem (e.g. Text, Shell, Python, JavaScript, Java, Go, C++, JSON, JSON Schema, YAML, TOML)
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

    @staticmethod
    def _merge_results(res1: dict[str, list], res2: dict[str, list]) -> dict[str, list]:
        """Merges two analysis results.
        - Concatenates unique 'files' based on ('path', 'language') composite values.
        - Merges 'languages_summary' by 'language' values, summing file counts.
        """
        # Merge and deduplicate 'files' by (path, language) values
        files_by_key: dict[tuple[str, str], dict[str, object]] = {}

        for file_entry in res1.get("files", []) + res2.get("files", []):
            if not isinstance(file_entry, dict):
                continue
            composite_key = (file_entry.get("path"), file_entry.get("language"))
            if composite_key not in files_by_key:
                files_by_key[composite_key] = file_entry

        # Merge and deduplicate 'languages_summary' by language values
        merged_languages: dict[str, dict[str, object]] = {}

        for lang_entry in res1.get("languages_summary", []) + res2.get("languages_summary", []):
            if not isinstance(lang_entry, dict):
                continue
            lang = lang_entry.get("language")
            if not isinstance(lang, str):
                continue
            if lang not in merged_languages:
                # Shallow copy entry so original dicts aren't mutated
                merged_languages[lang] = dict(lang_entry)
            else:
                existing = merged_languages[lang]

                # Sum file counts safely
                existing_count = existing.get("file_count", 0)
                new_count = lang_entry.get("file_count", 0)
                c1 = existing_count if isinstance(existing_count, int) else 0
                c2 = new_count if isinstance(new_count, int) else 0
                existing["file_count"] = c1 + c2

                # Preserve highest priority popularity
                ex_pop = str(existing.get("popularity", ""))
                new_pop = str(lang_entry.get("popularity", ""))
                if POPULARITY_PRIORITY.get(new_pop, 0) > POPULARITY_PRIORITY.get(
                    ex_pop, 0
                ):
                    existing["popularity"] = new_pop

                # Preserve highest priority type (code > markup > configuration)
                ex_type = str(existing.get("type", ""))
                new_type = str(lang_entry.get("type", ""))
                if TYPE_PRIORITY.get(new_type, 0) > TYPE_PRIORITY.get(ex_type, 0):
                    existing["type"] = new_type

        return {
            "files": list(files_by_key.values()),
            "languages_summary": list(merged_languages.values()),
        }

    @staticmethod
    def _chunked(items: list, size: int):
        """Yield successive chunks of at most `size` items from `items`."""
        for i in range(0, len(items), size):
            yield items[i : i + size]

    def _main(self, context):
        logger.debug("%s - Scanning %s ...", self.id, context.display_path)
        max_files = context.rule_setting("max_files", DEFAULT_MAX_FILES)
        lines = context.rule_setting("lines", DEFAULT_LINES_TO_EXTRACT)
        file_paths = list(find_text_files(context.path()))
        if not file_paths:
            logger.info("No non-binary files of interest found.")
            return []
        logger.info(f"Found {len(file_paths)} non-binary files")
        if len(file_paths) > max_files:
            logger.info(f"Scanning them in chunks with --max-files={max_files}")

        chunk_id = 1
        results = {"files": [], "languages_summary": []}
        for chunk in TooManyLanguagesRule._chunked(file_paths, max_files):
            logger.info("Chunk number %s", chunk_id)
            chunk_id += 1
            file_heads = []
            for path in chunk:
                relpath = context.relative(path)
                head = extract_head(path, lines)
                if head.strip():  # skip empty files
                    file_heads.append((relpath, head))
            if not file_heads:
                continue
            logger.debug(
                f"Extracted heads from {len(file_heads)} file(s) — sending to AI for analysis..."
            )
            prompt = TooManyLanguagesRule._build_prompt(file_heads)
            try:
                chunk_result = query_model(prompt)
                logger.debug("Chunk %s result: %s", chunk_id, chunk_result)
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse model response as JSON: {e}")
                continue
            results = TooManyLanguagesRule._merge_results(results, chunk_result)
        
        logger.debug("Merged results: %s", results)
        return results

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        # A None value means the corresponding severity is not used
        warning_threshold = context.rule_setting("warning_threshold", 10)
        error_threshold = context.rule_setting("error_threshold", None)
        critical_threshold = context.rule_setting("critical_threshold", None)
        
        output = self._main(context)
        logger.debug("Result: %s", json.dumps(output, indent=2))
        # Stop here if no files of interest have been found
        if output == {} or output is None:
            return []

        languages = [item["language"] for item in output["languages_summary"]]
        language_count = len(languages)
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
                    f" ({language_count} > {critical_threshold}): {', '.join(languages)}",
                    severity=Severity.CRITICAL,
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
                    f" ({language_count} > {error_threshold}): {', '.join(languages)}",
                    severity=Severity.MAJOR,
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
                    f" ({language_count} > {warning_threshold}): {', '.join(languages)}",
                    severity=Severity.MINOR,
                )
            ]

        logger.info(
            "✅ %s: Identified %s different languages in '%s' (fine): %s",
            self.name,
            language_count,
            context.display_path,
            ', '.join(languages),
        )
        # Return an info-level issue to inform the user about the test result
        return [
            context.issue(
                f"Languages used below the warning threshold ({warning_threshold}): {', '.join(languages)}",
                severity=Severity.INFO,
            )
        ]
