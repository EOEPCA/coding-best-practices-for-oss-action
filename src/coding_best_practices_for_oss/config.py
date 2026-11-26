# Action inputs and defaults, read once from the environment.
#
# GitHub Actions exposes an input "path-to-check" as INPUT_PATH-TO-CHECK, but
# some runners/shells normalise the dashes to underscores, so both spellings are
# accepted (see `env()`).
import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

ENGINE_ID = "Coding BP for OSS Validator"


def env(input_name: str, default: str = "") -> str:
    """Value of environment variable (e.g. via a GitHub Action input),
    dash or underscore spelling, with or without `INPUT` prefix.
    """
    upper = input_name.upper()
    return os.getenv(
        f"INPUT_{upper.replace('_', '-')}",
        os.getenv(
            f"INPUT_{upper.replace('-', '_')}",
            os.getenv(upper.replace('-', '_'), default)
        )
    )

WORKSPACE = os.getenv("GITHUB_WORKSPACE", "/github/workspace")

PATH_TO_CHECK = env("path-to-check", ".")
OUTPUT_FILE = env("output-file", "coding-best-practices-report.json")
OUTPUT_FORMAT = env("output-format", "generic")
DEFAULT_ANCHOR_FILE = env("default-anchor-file", "coding-best-practices-issues.md")
CONFIG_FILE = env("config-file", "")
RULES = env("rules", "")
VERBOSE = env("verbose", "false")

AI_MODEL_ENABLED = env("ai-model-enabled", "true")
AI_MODEL_PROVIDER = env("ai-model-provider", "")
AI_MODEL_BASE_URL = env("ai-model-base-url", "").rstrip('/')
AI_MODEL_API_KEY = env("ai-model-api-key", "")
AI_MODEL_NAME = env("ai-model-name", "")
AI_MODEL_MAX_TOKENS = 8000

HELP_BASE_URL = os.getenv("HELP-BASE-URL", "https://readthedocs.org/coding-best-practices-for-oss")

# Directories to skip entirely — VCS internals, dependency/build caches, etc.
SKIP_DIR_NAMES = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".tox", "target", "tmp",
}

SKIP_FILE_NAMES = {
    ".gitignore", "Dockerfile",
}

SKIP_FILE_EXTENSIONS = {
    ".log", ".tmp", ".out", ".err",
}

# Extensions that are almost always binary — skip without even opening them.
BINARY_FILE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a",
    ".pyc", ".pyo", ".class", ".jar",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".db", ".sqlite", ".sqlite3",
}

PYTHON_FILE_EXTENSIONS = {
    ".py",
}

# bytes read to decide binary vs text
MAX_FILE_SIZE_FOR_SNIFF = 8192

DEFAULT_CHAT_OPTIONS = {
    # Lock temperature to 0 for strict structural compliance
    "temperature": 0.0,
    # Set a static seed value for predictability
    "seed": 42,
}

DEFAULT_GENERATE_OPTIONS = {
    # Lock temperature to 0 for strict structural compliance
    "temperature": 0.0,
    # Set a static seed value for predictability
    "seed": 42,
}

def load_config(config_file: str | Path | None = None) -> Mapping[str, Any]:
    """Load the rule configuration file, then apply the run parameters to it.

    An empty configuration means "every rule enabled with its default
    severity and settings", which is what the action does when no config
    file is given.
    See examples/sample-config.yaml for the expected structure.

    The availability of the dependencies (AI model settings, ruff library) is
    applied whether a configuration file is given or not: the AI model is
    configured with run parameters, not with the configuration file.
    """
    config = _read_config_file(str(config_file or CONFIG_FILE))
    _apply_dependency_availability(config)
    return config


def _read_config_file(config_file: str) -> dict[str, Any]:
    """Content of the configuration file, or an empty configuration."""
    if not config_file:
        return {}

    path = Path(config_file)
    if not path.is_file():
        logger.warning("Configuration file %s not found, using the defaults.", path)
        return {}

    try:
        import yaml  # imported lazily: a GitHub action image may not ship PyYAML
    except ImportError:
        logger.warning(
            "PyYAML is not installed, ignoring %s and using the defaults.", path
        )
        return {}

    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        logger.error("Could not read the configuration file %s: %s", path, error)
        return {}

    if not isinstance(config, Mapping):
        logger.error("Configuration file %s must contain a mapping, ignoring it.", path)
        return {}

    logger.info("Loaded configuration file: %s", path)
    return dict(config)


def _apply_dependency_availability(config: dict[str, Any]) -> None:
    """Disable the dependencies that are turned off or not available.

    The `dependencies:` section is optional (and may be empty) in the file.
    """
    dependencies = config.get("dependencies")
    dependencies = dict(dependencies) if isinstance(dependencies, Mapping) else {}
    config["dependencies"] = dependencies

    def explicitly_disabled(name: str) -> bool:
        settings = dependencies.get(name)
        return isinstance(settings, Mapping) and not settings.get("enabled", True)

    if AI_MODEL_ENABLED == "false":
        logger.info("AI integration disabled")
        dependencies["ai"] = {"enabled": False}
    elif "" in [AI_MODEL_NAME, AI_MODEL_BASE_URL, AI_MODEL_API_KEY]:
        # Disable rules depending on AI if AI settings are missing
        if not explicitly_disabled("ai"):
            logger.warning(
                "Disabling AI dependent rules due to missing connection properties."
            )
        dependencies["ai"] = {"enabled": False}
    elif not explicitly_disabled("ai"):
        logger.info("Found configuration for AI model provider: %s", AI_MODEL_PROVIDER)

    # Disable using "ruff" if the "ruff" module cannot be imported
    if importlib.util.find_spec("ruff") is None:
        if not explicitly_disabled("ruff"):
            logger.warning("Disabling 'ruff' dependent rules due to missing library.")
        dependencies["ruff"] = {"enabled": False}
