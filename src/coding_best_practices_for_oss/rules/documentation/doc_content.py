# rules/documentation/doc_content.py
#
# The project documentation must cover the essential topics (dependencies, installation,
# execution, examples, inputs, outputs). The documentation files are sent to the AI model,
# which tells which files cover which topic; one issue is reported per missing topic.
#
import json
from fnmatch import fnmatch

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.ai_tools import query_model
from coding_best_practices_for_oss.utils.log_tools import getLogger


RULE_ID = "DOC002"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Software documentation should contain, even briefly, the following information:</p>
<ul>
<li><b>Dependencies and needs</b>, possibly also programmatically (e.g. <code>requirements.txt</code> file, <code>Dockerfile</code>, etc.)</li>
<li><b>Installation/deployment instructions</b>, e.g. command to compile, build, create virtual environment ...</li>
<li><b>How to run the software</b>, including examples</li>
<li><b>Input data</b>, what is needed and how to access or create it</li>
<li><b>Expected output</b>, and how to open/read/understand it</li>
</ul>
"""

# Topics the documentation must cover: key -> (label used in issues, definition given to the model)
TOPICS = {
    "dependencies": (
        "dependencies and needs",
        "the software, libraries, services, hardware or accounts required to install or run the software",
    ),
    "installation": (
        "installation/deployment instructions",
        "the steps or commands to install, build, compile, deploy, or set up the environment (e.g. virtual environment, container)",
    ),
    "execution": (
        "how to run the software",
        "the command, entry point, API or user interface used to run or call the software, with its options",
    ),
    "examples": (
        "usage examples",
        "at least one concrete example of running or calling the software (command line, code snippet, request ...)",
    ),
    "inputs": (
        "input data",
        "the input data, files, parameters or configuration the software needs, and how to obtain or create them",
    ),
    "outputs": (
        "expected output",
        "what the software produces (files, results, reports, return values, side effects) and how to read or use it",
    ),
}

# Files declaring the dependencies programmatically: their presence covers the "dependencies" topic
DEPENDENCY_FILE_PATTERNS = (
    "requirements*.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "environment.yml",
    "environment.yaml", "conda.yml", "Dockerfile", "Containerfile", "docker-compose.yml",
    "docker-compose.yaml", "package.json", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "Gemfile", "composer.json", "DESCRIPTION", "renv.lock", "CMakeLists.txt",
)

DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".adoc", ".asciidoc"}
# Text files that are not documentation, even with a documentation extension
NOT_DOC_PATTERNS = (
    "requirements*.txt", "constraints*.txt", "LICENSE*", "LICENCE*", "COPYING*", "NOTICE*",
    "CMakeLists.txt", "coding-best-practices-report*",
)
README_NAMES = ("README.md", "README.rst", "README.txt", "README")

DEFAULT_MAX_FILES = 8  # Documentation files sent to the model per query
DEFAULT_MAX_TOTAL_FILES = 40  # Documentation files analyzed in total (READMEs and docs/ first)
DEFAULT_MAX_CHARS = 8000  # Characters sent per documentation file


class DocumentationContentRule(Rule):
    id = RULE_ID
    name = "Documentation Content"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "documentation"
    dependencies = ["ai"]
    scope = PROJECT_SCOPE
    effort_minutes = 60
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)
    clean_code_attribute = "COMPLETE"

    @staticmethod
    def _build_prompt(docs: list[tuple[str, str]], topics: list[str]) -> str:
        """docs: list of (relative_path, text) tuples."""
        entries = []
        for relpath, text in docs:
            entries.append(f"### File: {relpath}\n```\n{text}\n```\n")
        joined = "\n".join(entries)
        topic_lines = "\n".join(f'        - "{key}": {TOPICS[key][1]}.' for key in topics)
        shape = ",\n".join(f'            "{key}": ["relative/path/of/files/covering/{key}"]' for key in topics)

        return f"""You are reviewing the documentation of a software project. Below are
        documentation files, each identified by its relative path. For each topic in the
        list, identify the files that actually provide that information.

        Topics:
{topic_lines}

        A file covers a topic only if it gives the information itself, even briefly. A heading
        with no content, a "TODO", or a mere link to another place does not cover a topic.
        Only use the relative paths given below. Use an empty list when no file covers a topic.

        Respond ONLY with a JSON object (no markdown fences, no preamble) in this exact shape:

        {{
        "topics": {{
{shape}
            }}
        }}

        Files to analyze:

        {joined}
        """

    @staticmethod
    def _chunked(items: list, size: int):
        """Yield successive chunks of at most `size` items from `items`."""
        for i in range(0, len(items), size):
            yield items[i : i + size]

    @staticmethod
    def _is_doc_file(file, anchor_file: str) -> bool:
        if file.relative_path == anchor_file:
            return False
        if any(fnmatch(file.name, pattern) for pattern in NOT_DOC_PATTERNS):
            return False
        return file.suffix in DOC_EXTENSIONS or file.name.upper().startswith("README")

    @staticmethod
    def _priority(file) -> tuple:
        """Sort key: root README first, then other READMEs, then docs/ folders, then the rest."""
        parts = file.relative_path.lower().split("/")
        is_readme = file.name.upper().startswith("README")
        in_docs = any(part in ("doc", "docs", "documentation", "wiki") for part in parts[:-1])
        return (not (is_readme and len(parts) == 1), not is_readme, not in_docs, len(parts), file.relative_path)

    def _doc_files(self, context, max_total_files: int) -> list:
        files = [f for f in context.iter_files() if self._is_doc_file(f, context.anchor_file) and (f.text or "").strip()]
        files.sort(key=self._priority)
        if len(files) > max_total_files:
            logger.info("Analyzing the first %s of %s documentation files", max_total_files, len(files))
            files = files[:max_total_files]
        return files

    @staticmethod
    def _dependency_files(context) -> list[str]:
        return [
            f.relative_path for f in context.iter_files()
            if any(fnmatch(f.name, pattern) for pattern in DEPENDENCY_FILE_PATTERNS)
        ]

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        max_files = context.rule_setting("max_files", DEFAULT_MAX_FILES)
        max_total_files = context.rule_setting("max_total_files", DEFAULT_MAX_TOTAL_FILES)
        max_chars = context.rule_setting("max_chars", DEFAULT_MAX_CHARS)
        topics = [t for t in context.rule_setting("topics", list(TOPICS)) if t in TOPICS]

        doc_files = self._doc_files(context, max_total_files)
        if doc_files:
            logger.info("Found %s documentation files", len(doc_files))
        else:
            # No model query: every topic not covered by a dependency file is reported missing
            logger.info("❌ No documentation files found in '%s'", context.display_path)

        covered: dict[str, set[str]] = {topic: set() for topic in topics}

        # Dependencies may be declared programmatically instead of in the documentation
        if "dependencies" in covered:
            dependency_files = self._dependency_files(context)
            if dependency_files:
                logger.info("Dependencies declared in: %s", ", ".join(dependency_files))
                covered["dependencies"].update(dependency_files)

        to_ask = [t for t in topics if not covered[t]]
        chunk_id = 0
        for chunk in self._chunked(doc_files, max_files):
            if not to_ask:
                break
            chunk_id += 1
            docs = []
            for f in chunk:
                text = f.text
                if len(text) > max_chars:
                    text = text[:max_chars] + f"\n[... {len(f.text) - max_chars} more characters]"
                docs.append((f.relative_path, text))
            logger.info("Chunk number %s: sending %s documentation file(s) to AI for analysis...", chunk_id, len(docs))
            try:
                result = query_model(self._build_prompt(docs, to_ask))
                logger.debug("Chunk %s result: %s", chunk_id, json.dumps(result, indent=2))
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse model response as JSON: {e}")
                continue
            found = result.get("topics") if isinstance(result, dict) else None
            if not isinstance(found, dict):
                logger.error("Unexpected model response: %s", result)
                continue
            sent_paths = {relpath for relpath, _ in docs}
            for topic in to_ask:
                paths = found.get(topic)
                if isinstance(paths, list):
                    # Ignore paths the model made up
                    covered[topic].update(p for p in paths if p in sent_paths)
            to_ask = [t for t in to_ask if not covered[t]]

        # Missing topics are reported on the main README, or on the anchor file
        readme = context.find_file(*README_NAMES)
        readme_path = readme.relative_path if readme else None

        issues = []
        for topic in topics:
            label = TOPICS[topic][0]
            if covered[topic]:
                logger.info("✅ Documentation covers %s: %s", label, ", ".join(sorted(covered[topic])))
            else:
                logger.info("❌ Documentation does not cover %s", label)
                issues.append(
                    context.issue(
                        f"The documentation does not describe the {label}: {TOPICS[topic][1]}.",
                        file_path=readme_path,
                    )
                )
        if issues:
            return issues

        # Return an info-level issue to inform the user about the test result
        return [
            context.issue(
                f"The documentation covers: {', '.join(TOPICS[t][0] for t in topics)}",
                severity=Severity.INFO,
            )
        ]
