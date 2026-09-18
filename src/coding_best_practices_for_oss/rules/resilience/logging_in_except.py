# rules/programming/use_logging.py
#
# Log the errors, log the progress
#
import ast
import json
import logging
import os
import sys

from coding_best_practices_for_oss.core.issue import Severity, Impact, ImpactSeverity, SoftwareQuality
from coding_best_practices_for_oss.core.rule import PROJECT_SCOPE, Rule
from coding_best_practices_for_oss.utils.file_tools import find_python_files


logger = logging.getLogger(__name__)

DESCRIPTION = """<p>The Python 'logging' library should be used to report about progress and errors.</p>
"""


class UnloggedExceptVisitor(ast.NodeVisitor):

    def __init__(self, context, filepath, logger_names: set[str] | None = None):
        self.context = context
        self.filepath = filepath
        # Recognized logger identifiers or method namespaces
        self.logger_names = logger_names or {
            "logging",
            "logger",
            "log",
            "LOGGER",
            "LOG",
        }
        self.issues = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # Inspect all child nodes inside the except block for logging calls
        has_logging_call = False

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # Handles logger.error(), logging.exception(), self.logger.info(), etc.
                if isinstance(child.func, ast.Attribute):
                    # Check 'logger' in 'logger.error(...)'
                    if (
                        isinstance(child.func.value, ast.Name)
                        and child.func.value.id in self.logger_names
                    ):
                        has_logging_call = True
                        break
                    # Check 'self.logger' in 'self.logger.error(...)'
                    elif (
                        isinstance(child.func.value, ast.Attribute)
                        and child.func.value.attr in self.logger_names
                    ):
                        has_logging_call = True
                        break

        if not has_logging_call:
            exc_name = (
                node.type.id
                if isinstance(node.type, ast.Name)
                else "catch-all"
            )
            self.issues.append(
                self.context.issue(
                    f"Except block handling '{exc_name}' contains no logging calls.",
                    #severity=Severity.MINOR, Use default severity
                    line=node.lineno,
                    column=node.col_offset,
                    file_path=self.filepath,
                )
            )

        # Continue traversing nested statements
        self.generic_visit(node)


class LoggingInExceptRule(Rule):
    id = "RES002"
    name = "Use Python logging in except"
    description = DESCRIPTION
    default_severity = "MINOR"
    category = "programming"
    dependencies = []  # Custom rule
    scope = PROJECT_SCOPE
    effort_minutes = 600
    impacts = (Impact(SoftwareQuality.MAINTAINABILITY, ImpactSeverity.MEDIUM),)


    def check(self, context):
        logger.debug("%s context: %s", self, context.rule_settings)
        issues = []
        for filepath in find_python_files(context.path()):
            with open(filepath, "r", encoding="utf-8") as file:
                source_code = file.read()
            logger.debug("Checking: %s", filepath)
            """Parses source code string and returns list of unlogged except blocks."""
            tree = ast.parse(source_code, filename=filepath)
            visitor = UnloggedExceptVisitor(context, filepath)
            visitor.visit(tree)
            logger.debug("Issues: %s", visitor.issues)
            issues.extend(visitor.issues)
        logging.info("❌ Found %s except blocks without logging", len(issues))
        return issues