# Entry point: reads the action inputs, runs the checks, writes the report.
#
# Every input can also be given as a command line option, so that the exact
# same code path can be run locally:
#     python -m coding_best_practices_for_oss --path-to-check . --output-format sarif
import argparse
import logging
import os
import sys

from coding_best_practices_for_oss import __version__, config
from coding_best_practices_for_oss.core.report import (
    FORMAT_GENERIC,
    SUPPORTED_FORMATS,
    generate_report,
    write_report,
)
from coding_best_practices_for_oss.core.runner import Runner

logger = logging.getLogger("coding_best_practices_for_oss")


class GitHubActionsFormatter(logging.Formatter):
    """Bridges Python logging with the GitHub workflow commands.

    Warnings and errors become annotations shown on the workflow run; anything
    else is printed as-is in the job log.
    """

    def format(self, record):
        message = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"::error::{message}"
        if record.levelno >= logging.WARNING:
            return f"::warning::{message}"
        return message


def configure_logging(verbose: bool = False, github_actions: bool | None = None) -> None:
    """Send the logs to stdout, annotated when running in GitHub Actions."""
    if github_actions is None:
        github_actions = os.getenv("GITHUB_ACTIONS") == "true"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        GitHubActionsFormatter()
        if github_actions
        else logging.Formatter("%(levelname)-8s %(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()  # replace the handlers, so calling main() twice is safe
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)


def build_parser() -> argparse.ArgumentParser:
    """Command line parser, defaulting to the action inputs."""
    parser = argparse.ArgumentParser(
        prog="coding-best-practices-for-oss",
        description="Check whether a project complies with coding best practices.",
    )
    parser.add_argument(
        "--path-to-check",
        default=config.PATH_TO_CHECK,
        help="directory to check (default: %(default)s)",
    )
    parser.add_argument(
        "--output-file",
        default=config.OUTPUT_FILE,
        help="report file to write (default: %(default)s)",
    )
    # No argparse `choices` here: the value usually comes from an action input,
    # and an unknown format falls back to the generic report with a warning
    # rather than failing the whole workflow.
    parser.add_argument(
        "--output-format",
        default=config.OUTPUT_FORMAT,
        metavar="{" + ",".join(SUPPORTED_FORMATS) + "}",
        help="report format (default: %(default)s)",
    )
    parser.add_argument(
        "--default-anchor-file",
        default=config.DEFAULT_ANCHOR_FILE,
        help="file the issues that are not tied to a source file point at "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--config-file",
        default=config.CONFIG_FILE,
        help="YAML file enabling/disabling rules and overriding severities",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="exit with a non-zero status when issues are found",
    )
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the validator, return the process exit code."""
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    runner = Runner(
        args.path_to_check,
        anchor_file=args.default_anchor_file,
        engine_id=config.ENGINE_ID,
        config=config.load_config(args.config_file),
    )

    try:
        result = runner.run()
    except NotADirectoryError as error:
        logger.error("%s", error)
        return 1

    report = generate_report(result, args.output_format, engine_id=config.ENGINE_ID)
    try:
        path = write_report(report, args.output_file)
    except OSError as error:
        logger.error("Could not write the report %s: %s", args.output_file, error)
        return 1

    logger.info("Successfully saved: %s", path)
    if result.errors:
        logger.warning("%d rule execution(s) failed, see the log above.", len(result.errors))

    if args.fail_on_issues and result.issues:
        logger.error("%s", result.summary())
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
