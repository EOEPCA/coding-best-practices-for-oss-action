# rules/documentation/python_script_help.py
"""
Analyze a Python script (via AST, no execution) to determine:

1. Whether it looks like a CLI script — has a `main()` function and/or an
   `if __name__ == "__main__":` guard.
2. If so, whether it supports a `--help` flag, detected via:
   - argparse.ArgumentParser(...) without add_help=False (argparse adds
     --help automatically by default)
   - click's @click.command / @click.group without add_help_option=False
     (click also adds --help automatically by default)
   - a manual/fallback case: the literal string "--help" appears anywhere
     in the source (e.g. hand-rolled sys.argv parsing)

Usage:
    result = analyze_cli_help_support("my_script.py")
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.file_tools import find_python_files
from coding_best_practices_for_oss.utils.log_tools import getLogger


RULE_ID = "DOC004"

logger = getLogger(__name__, RULE_ID)

DESCRIPTION = """<p>Python scripts meant to be executed on the command line should have a “--help” option.</p>
"""


@dataclass
class CliHelpAnalysis:
    file: str
    has_main_function: bool = False
    has_name_main_guard: bool = False
    is_cli_script: bool = False  # main_function OR name_main_guard
    uses_argparse: bool = False
    argparse_help_disabled: bool = False  # add_help=False found anywhere
    uses_click: bool = False
    click_help_disabled: bool = False  # add_help_option=False found anywhere
    manual_help_string_found: bool = False  # literal "--help" found in source

    @property
    def has_help_support(self) -> bool:
        if not self.is_cli_script:
            return False  # not applicable — not a CLI script at all
        if self.uses_argparse and not self.argparse_help_disabled:
            return True
        if self.uses_click and not self.click_help_disabled:
            return True
        if self.manual_help_string_found:
            return True
        return False

    @property
    def issues(self) -> list[str]:
        problems = []
        if not self.is_cli_script:
            return problems  # nothing to flag if it's not a CLI script
        if self.uses_argparse and self.argparse_help_disabled:
            problems.append("argparse.ArgumentParser was created with add_help=False, disabling --help.")
        if self.uses_click and self.click_help_disabled:
            problems.append("A click command was defined with add_help_option=False, disabling --help.")
        if not self.has_help_support and not problems:
            problems.append(
                "Python script appears to be a CLI entry point but no --help support was detected "
                "(no argparse/click usage, and no manual '--help' handling found)."
            )
        return problems


class _CliHelpVisitor(ast.NodeVisitor):
    def __init__(self):
        self.has_main_function = False
        self.has_name_main_guard = False
        self.uses_argparse = False
        self.argparse_help_disabled = False
        self.uses_click = False
        self.click_help_disabled = False

    # --- detect imports of argparse / click ---
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name == "argparse":
                self.uses_argparse = True
            elif alias.name == "click":
                self.uses_click = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module == "argparse":
            self.uses_argparse = True
        elif node.module == "click":
            self.uses_click = True
        self.generic_visit(node)

    # --- detect def main(...) ---
    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name == "main":
            self.has_main_function = True
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if node.name == "main":
            self.has_main_function = True
        self.generic_visit(node)

    # --- detect `if __name__ == "__main__":` ---
    def visit_If(self, node: ast.If):
        if self._is_name_main_guard(node):
            self.has_name_main_guard = True
        self.generic_visit(node)

    @staticmethod
    def _is_name_main_guard(node: ast.If) -> bool:
        test = node.test
        if not isinstance(test, ast.Compare):
            return False
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            return False

        left, right = test.left, test.comparators[0]

        def is_dunder_name(n):
            return isinstance(n, ast.Name) and n.id == "__name__"

        def is_main_string(n):
            return isinstance(n, ast.Constant) and n.value == "__main__"

        return (is_dunder_name(left) and is_main_string(right)) or (
            is_dunder_name(right) and is_main_string(left)
        )

    # --- detect ArgumentParser(add_help=False) / click add_help_option=False ---
    def visit_Call(self, node: ast.Call):
        func = node.func

        # argparse.ArgumentParser(...) or ArgumentParser(...) after `from argparse import ArgumentParser`
        func_name = self._resolve_call_name(func)
        if func_name in ("ArgumentParser", "argparse.ArgumentParser"):
            self.uses_argparse = True
            if self._kwarg_is_false(node, "add_help"):
                self.argparse_help_disabled = True

        # click.command(...) / click.group(...) called directly (rare but possible),
        # plus decorator usage is handled in visit_FunctionDef via decorator_list below.
        if func_name in ("click.command", "click.group", "command", "group"):
            self.uses_click = True
            if self._kwarg_is_false(node, "add_help_option"):
                self.click_help_disabled = True

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        # Decorators on functions/classes (e.g. @click.command()) show up as
        # Call nodes in decorator_list — walk those explicitly too, since
        # generic_visit already covers this, but keep for clarity/robustness.
        for decorator in node.decorator_list:
            self._check_decorator(decorator)
        self.generic_visit(node)

    def _check_decorator(self, decorator: ast.expr):
        if isinstance(decorator, ast.Call):
            func_name = self._resolve_call_name(decorator.func)
            if func_name in ("click.command", "click.group", "command", "group"):
                self.uses_click = True
                if self._kwarg_is_false(decorator, "add_help_option"):
                    self.click_help_disabled = True

    @staticmethod
    def _resolve_call_name(func: ast.expr) -> str | None:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parts = []
            node = func
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
            return ".".join(reversed(parts))
        return None

    @staticmethod
    def _kwarg_is_false(call: ast.Call, kwarg_name: str) -> bool:
        for kw in call.keywords:
            if kw.arg == kwarg_name and isinstance(kw.value, ast.Constant) and kw.value is False:
                return True
            if kw.arg == kwarg_name and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                return True
        return False


def analyze_cli_help_support(file_path: str) -> CliHelpAnalysis:
    """
    Analyze a single Python file for CLI --help support.

    Args:
        file_path (str): Path to the .py file to analyze.

    Returns:
        CliHelpAnalysis: structured result — see the dataclass fields above.

    Raises:
        SyntaxError: if the file isn't valid Python.
        FileNotFoundError: if the file doesn't exist.
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))

    visitor = _CliHelpVisitor()
    visitor.visit(tree)

    # Also walk decorator lists on plain function defs (not just classes) —
    # ast.NodeVisitor's generic_visit already recurses into decorator
    # expressions as Call nodes, so visit_Call catches @click.command()
    # decorators automatically. The extra ClassDef handling above covers
    # class-based click groups; this comment documents that both paths
    # are exercised via the general tree walk, not duplicated logic.

    result = CliHelpAnalysis(
        file=str(path),
        has_main_function=visitor.has_main_function,
        has_name_main_guard=visitor.has_name_main_guard,
        uses_argparse=visitor.uses_argparse,
        argparse_help_disabled=visitor.argparse_help_disabled,
        uses_click=visitor.uses_click,
        click_help_disabled=visitor.click_help_disabled,
        manual_help_string_found='"--help"' in source or "'--help'" in source,
    )
    result.is_cli_script = result.has_main_function or result.has_name_main_guard

    return result


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python analyze_cli_help.py <script.py>")
        sys.exit(1)

    analysis = analyze_cli_help_support(sys.argv[1])

    print(f"File: {analysis.file}")
    print(f"  Is CLI script:      {analysis.is_cli_script}")
    print(f"  Has main() func:    {analysis.has_main_function}")
    print(f"  Has __main__ guard: {analysis.has_name_main_guard}")
    print(f"  Uses argparse:      {analysis.uses_argparse}")
    print(f"  Uses click:         {analysis.uses_click}")
    print(f"  Has --help support: {analysis.has_help_support}")

    if analysis.issues:
        print("  Issues:")
        for issue in analysis.issues:
            print(f"    - {issue}")


class PythonScriptHelpRule(Rule):
    id = RULE_ID
    name = "Python CLI scripts must provide help"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "documentation"
    dependencies = []  # Custom rule
    scope = PROJECT_SCOPE
    effort_minutes = 600
    impacts = (Impact(SoftwareQuality.RELIABILITY, ImpactSeverity.LOW),)


    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        issues = []
        for filepath in find_python_files(context.path()):
            relpath = context.relative(filepath)
            logger.debug("Checking: %s", relpath)
            analysis = analyze_cli_help_support(filepath)
            if not analysis.is_cli_script:
                logger.debug("✅ Not a CLI script: %s", filepath)
                continue
            if analysis.issues == []:
                logger.info("✅ Python CLI script provides help: %s", relpath)
                continue
            for message in analysis.issues:
                logger.info("❌ Python CLI script must provide help: %s: %s", relpath, message)
                # See CliHelpAnalysis.issues(), above, for the generated issue messages
                issues.append(context.issue(message, file_path=relpath,))
        logger.debug("Issues: %s", issues)
        return issues