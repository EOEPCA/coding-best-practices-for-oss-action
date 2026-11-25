# rules/documentation/python_docstrings_sem.py
#
# Python docstrings must be meaningful and consistent with the code (semantic check with AI).
# Missing and empty docstrings are reported by DOC005 (python_docstrings.py).
#
# The classes and functions are extracted with the AST, so that their names and locations
# never depend on the model. Only the ones with a non-empty docstring are sent to the model.
# Obvious placeholders ("TODO", "...", the name itself) are reported without querying the model.
#
import ast
import json
import re
from dataclasses import dataclass

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.ai_tools import query_model
from coding_best_practices_for_oss.utils.file_tools import find_python_files
from coding_best_practices_for_oss.utils.log_tools import getLogger


RULE_ID = "DOC006"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>The docstrings of Python classes, methods and functions must provide meaningful
information (not a placeholder nor a paraphrase of the name) and must not contradict the code
(parameters, return value, raised exceptions, behaviour).</p>
"""

DEFAULT_MAX_ITEMS = 20  # Classes and functions sent to the model per query
DEFAULT_MAX_LINES = 60  # Source lines sent to the model per class or function
DEFAULT_INCLUDE_PRIVATE = False  # Also check the docstrings of _private classes and functions

# Docstrings made only of these words (case-insensitive, punctuation ignored) are placeholders
PLACEHOLDER_RE = re.compile(
    r"^(todo|fixme|xxx|tbd|tbc|to\s*do|to\s*be\s*(done|completed|documented)|docstring|"
    r"description|summary|doc|documentation|n/?a|none|placeholder|\.\.\.|-+)?$",
    re.IGNORECASE,
)


@dataclass
class DocItem:
    relpath: str
    qualname: str
    kind: str  # "class", "method" or "function"
    line: int
    docstring: str
    source: str


class _DocItemCollector(ast.NodeVisitor):
    """Collect the classes and functions that have a non-empty docstring, with their qualified name."""

    def __init__(self, relpath: str, text: str, max_lines: int, include_private: bool):
        self.relpath = relpath
        self.text = text
        self.max_lines = max_lines
        self.include_private = include_private
        self.items: list[DocItem] = []
        self._stack: list[ast.AST] = []

    def _visit_def(self, node, kind: str):
        qualname = ".".join([n.name for n in self._stack] + [node.name])
        is_private = node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__"))
        docstring = ast.get_docstring(node)
        if docstring and docstring.strip() and (self.include_private or not is_private):
            self.items.append(
                DocItem(
                    relpath=self.relpath,
                    qualname=qualname,
                    kind=kind,
                    line=node.lineno,
                    docstring=docstring.strip(),
                    source=self._source(node),
                )
            )
        self._stack.append(node)
        self.generic_visit(node)
        self._stack.pop()

    def visit_ClassDef(self, node):
        self._visit_def(node, "class")

    def visit_FunctionDef(self, node):
        kind = "method" if self._stack and isinstance(self._stack[-1], ast.ClassDef) else "function"
        self._visit_def(node, kind)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _source(self, node) -> str:
        """Source sent to the model: full body for a function, header and method signatures for a class."""
        if isinstance(node, ast.ClassDef):
            lines = [self.text.splitlines()[node.lineno - 1]]
            lines.append(f'    """{ast.get_docstring(node)}"""')
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append("    " + self.text.splitlines()[child.lineno - 1].strip() + " ...")
            return "\n".join(lines)
        source = ast.get_source_segment(self.text, node, padded=True) or ""
        lines = source.splitlines()
        if len(lines) > self.max_lines:
            lines = lines[: self.max_lines] + [f"    # ... ({len(lines) - self.max_lines} more lines)"]
        return "\n".join(lines)


def is_placeholder(item: DocItem) -> bool:
    """Whether the docstring obviously carries no information."""
    text = re.sub(r"[\s.:;,!]+$", "", item.docstring.strip())
    if PLACEHOLDER_RE.match(text):
        return True
    # A docstring that only repeats the name, e.g. "get_value" or "Get value."
    name = item.qualname.rsplit(".", 1)[-1].strip("_").replace("_", " ").lower()
    return text.replace("_", " ").lower() == name


class PythonDocstringsSemanticRule(Rule):
    id = RULE_ID
    name = "Python docstrings must be correct and meaningful"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "documentation"
    dependencies = ["ai"]
    scope = PROJECT_SCOPE
    effort_minutes = 10
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)
    clean_code_attribute = "CLEAR"

    @staticmethod
    def _build_prompt(items: list[DocItem]) -> str:
        entries = []
        for index, item in enumerate(items):
            entries.append(
                f"### Item {index}: {item.kind} '{item.qualname}' ({item.relpath}:{item.line})\n"
                f"```python\n{item.source}\n```\n"
            )
        joined = "\n".join(entries)

        return f"""You are a senior Python reviewer. Each item below is a Python class, method or
        function, given with its docstring and its code (for classes, only the method signatures).
        Assess the docstring of each item against two criteria:

        - "meaningless": true if the docstring provides no useful information beyond the name
          and the signature, e.g. a placeholder, a paraphrase of the name ("Get value." for
          get_value), or a generic sentence that would fit any code. A short docstring that
          accurately states the purpose is NOT meaningless.
        - "contradicts": true only if the docstring states something that is clearly wrong
          for the code: parameters that do not exist or are missing, a wrong return value or
          type, wrong raised exceptions, or a behaviour that the code does not have.
          Missing details are NOT contradictions. When in doubt, answer false.

        Respond ONLY with a JSON object (no markdown fences, no preamble) in this exact shape,
        with exactly one entry per item:

        {{
        "items": [
            {{
            "index": <item number>,
            "meaningless": true | false,
            "contradicts": true | false,
            "explanation": "one short sentence, only if meaningless or contradicts is true"
            }}
        ]
        }}

        Items to analyze:

        {joined}
        """

    @staticmethod
    def _chunked(items: list, size: int):
        """Yield successive chunks of at most `size` items from `items`."""
        for i in range(0, len(items), size):
            yield items[i : i + size]

    def _collect(self, context) -> list[DocItem]:
        max_lines = context.rule_setting("max_lines", DEFAULT_MAX_LINES)
        include_private = context.rule_setting("include_private", DEFAULT_INCLUDE_PRIVATE)
        items = []
        for path in find_python_files(context.path()):
            relpath = context.relative(path)
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(text, filename=relpath)
            except SyntaxError as e:
                logger.warning("Skipping %s: %s", relpath, e)
                continue
            collector = _DocItemCollector(relpath, text, max_lines, include_private)
            collector.visit(tree)
            items.extend(collector.items)
        return items

    def _issue(self, context, item: DocItem, message: str, severity=None):
        return context.issue(message, file_path=item.relpath, line=item.line, severity=severity)

    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        max_items = context.rule_setting("max_items", DEFAULT_MAX_ITEMS)

        items = self._collect(context)
        if not items:
            logger.info("No documented Python classes or functions found in '%s'", context.display_path)
            return []
        logger.info("Found %s documented Python classes and functions", len(items))

        issues = []
        # Obvious placeholders do not need the model
        to_analyze = []
        for item in items:
            if is_placeholder(item):
                logger.info("❌ %s:%s: placeholder docstring in %s '%s'", item.relpath, item.line, item.kind, item.qualname)
                issues.append(
                    self._issue(context, item, f"Docstring of {item.kind} '{item.qualname}' is a placeholder: \"{item.docstring}\"")
                )
            else:
                to_analyze.append(item)

        chunk_id = 0
        for chunk in self._chunked(to_analyze, max_items):
            chunk_id += 1
            logger.info("Chunk number %s: sending %s item(s) to AI for analysis...", chunk_id, len(chunk))
            prompt = self._build_prompt(chunk)
            try:
                result = query_model(prompt)
                logger.debug("Chunk %s result: %s", chunk_id, json.dumps(result, indent=2))
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse model response as JSON: {e}")
                continue
            if not isinstance(result, dict) or not isinstance(result.get("items"), list):
                logger.error("Unexpected model response: %s", result)
                continue

            for entry in result["items"]:
                if not isinstance(entry, dict):
                    continue
                index = entry.get("index")
                if not isinstance(index, int) or not 0 <= index < len(chunk):
                    logger.warning("Ignoring model entry with an invalid index: %s", entry)
                    continue
                item = chunk[index]
                explanation = str(entry.get("explanation") or "").strip()
                suffix = f": {explanation}" if explanation else ""
                if entry.get("contradicts") is True:
                    logger.info("❌ %s:%s: docstring contradicts %s '%s'", item.relpath, item.line, item.kind, item.qualname)
                    issues.append(
                        self._issue(
                            context, item,
                            f"Docstring of {item.kind} '{item.qualname}' contradicts the code{suffix}",
                            severity=Severity.MAJOR,
                        )
                    )
                if entry.get("meaningless") is True:
                    logger.info("❌ %s:%s: meaningless docstring in %s '%s'", item.relpath, item.line, item.kind, item.qualname)
                    issues.append(
                        self._issue(context, item, f"Docstring of {item.kind} '{item.qualname}' is not meaningful{suffix}")
                    )

        if issues:
            return issues

        logger.info("✅ %s documented classes and functions have meaningful docstrings", len(items))
        # Return an info-level issue to inform the user about the test result
        return [
            context.issue(
                f"The docstrings of {len(items)} classes and functions are meaningful and consistent with the code",
                severity=Severity.INFO,
            )
        ]
