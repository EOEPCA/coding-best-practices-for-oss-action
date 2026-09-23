import json
import subprocess
import sys

from pathlib import Path

from coding_best_practices_for_oss.utils.log_tools import getLogger


logger = getLogger(__name__)

def exec_ruff(path_to_check: str, select: list[str] = []) -> dict:
    """
    Run Ruff against a project optionnally using a rules subset.

    Args:
        path_to_check (str): Path to the project/folder to check.
        select ([str]): Array of rule IDs, or prefixes (e.g. ["T20"])

    Returns:
        list: [
            {"file": str, "line": int, "column": int, "code": str, "message": str},
            ...
        ]

    Raises:
        Exception: if `ruff` execution as a subprocess failed.
        RuntimeError: if Ruff's output can't be parsed as JSON.
    """
    try:
        ruff_exec = [sys.executable, "-m", "ruff", "check", "--output-format", "json"]
        rules_select = []
        if isinstance(select, str):
            select = [select]
        for _select in select:
            rules_select.extend(["--select", _select])
        logger.debug("Checking rules: %s", rules_select)
        path_to_check = str(Path(path_to_check).resolve())
        logger.debug("Checking path: %s", path_to_check)
        result = subprocess.run(
            ruff_exec + rules_select + [path_to_check],
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise Exception("ruff execution failed.") from e

    # Ruff exits with code 1 when it finds violations — that's expected, not an error.
    # Only treat it as a real failure if there's no valid JSON in stdout at all.
    try:
        violations_raw = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse Ruff output as JSON: {result.stderr}") from e

    violations = [
        {
            # Return relative file paths
            "file": str(Path(v["filename"]).relative_to(path_to_check)),
            "line": v["location"]["row"],
            "column": v["location"]["column"],
            "code": v["code"],
            "message": v["message"],
        }
        for v in violations_raw
    ]
    return violations


def new_issue(context, v: dict = {}):
    return context.issue(
        v["message"],
        #severity=Severity.MINOR,
        line=v["line"],
        column=v["column"],
        file_path=v["file"],
    )

def violation_string(v: dict = {}):
    return f"{v['file']}:{v['line']}:{v['column']} [ruff {v['code']}] {v['message']}"