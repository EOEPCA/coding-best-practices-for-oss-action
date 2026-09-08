# Action inputs and defaults, read once from the environment.
#
# GitHub Actions exposes an input "path-to-check" as INPUT_PATH-TO-CHECK, but
# some runners/shells normalise the dashes to underscores, so both spellings are
# accepted (see `env()`).
import logging
import os
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

ENGINE_ID = "Coding BP for OSS Validator"

ML_MODEL = "claude-sonnet-4-6"
ML_MODEL_API = ""
ML_MODEL_KEY = ""

ML_MODEL_MAX_TOKENS = 8000

def env(input_name: str, default: str = "") -> str:
    """Value of a GitHub Action input, dash or underscore spelling."""
    upper = input_name.upper()
    return os.getenv(
        f"INPUT_{upper.replace('_', '-')}",
        os.getenv(f"INPUT_{upper.replace('-', '_')}", default),
    )


PATH_TO_CHECK = env("path-to-check", ".")
OUTPUT_FILE = env("output-file", "coding-best-practices-report.json")
OUTPUT_FORMAT = env("output-format", "generic")
DEFAULT_ANCHOR_FILE = env("default-anchor-file", "coding-best-practices-issues.md")
CONFIG_FILE = env("config-file", "")
WORKSPACE = os.getenv("GITHUB_WORKSPACE", "/github/workspace")

HELP_BASE_URL = os.getenv("HELP_BASE_URL", "https://readthedocs.org/coding-best-practices-for-oss")

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

MAX_FILE_SIZE_FOR_SNIFF = 8192  # bytes read to decide binary vs text

#OLLAMA_MODEL_NAME = "deepseek-coder"
#OLLAMA_MODEL_NAME = "llama3.2:1b"
#OLLAMA_MODEL_NAME = "llama3.1:8b"
#OLLAMA_MODEL_NAME = "qwen2.5-coder:7b"
#OLLAMA_MODEL_NAME = "qwen2.5-coder:3b"
#OLLAMA_MODEL_NAME = "qwen3.6:35b-a3b"
#OLLAMA_MODEL_NAME = "qwen2.5-coder:14B"
OLLAMA_MODEL_NAME = "qwen2.5-coder:14B"

#GEMINI_MODEL_NAME = "models/gemini-2.5-flash-lite"
GEMINI_MODEL_NAME = "models/gemini-2.5-flash"
CLAUDE_MODEL_NAME = "claude-sonnet-4.6"
COPILOT_MODEL_NAME = "gpt-4o"
CHATGPT_MODEL_NAME = "gpt-4o"

# OpenAI compatible URLs
#OLLAMA_OPENAI_URL = "http://yoda:11434/v1"
OLLAMA_OPENAI_URL = "http://172.16.1.27:11434/v1"
GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
CHATGPT_OPENAI_URL = "https://api.openai.com/v1"
COPILOT_OPENAI_URL = "https://models.inference.ai.azure.com"
CLAUDE_OPENAI_URL = "https://api.anthropic.com/v1"

CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "TBD")

ML_MODEL_API_KEY = CLAUDE_API_KEY
ML_MODEL_BASE_URL = CLAUDE_OPENAI_URL

ML_MODEL_PROVIDER = os.environ.get("ML_MODEL_PROVIDER", "Ollama")

if ML_MODEL_PROVIDER == "Ollama":
    ML_MODEL_BASE_URL = OLLAMA_OPENAI_URL
    ML_MODEL_API_KEY = "ollama"
    ML_MODEL_NAME = OLLAMA_MODEL_NAME
elif ML_MODEL_PROVIDER in ["Anthropic", "Claude"]:
    ML_MODEL_BASE_URL = CLAUDE_OPENAI_URL
    ML_MODEL_API_KEY = CLAUDE_API_KEY
    ML_MODEL_NAME = CLAUDE_MODEL_NAME
elif ML_MODEL_PROVIDER in ["OpenAPI", "ChatGPT"]:
    ML_MODEL_BASE_URL = CHATGPT_OPENAI_URL
    ML_MODEL_API_KEY = CHATGPT_OPENAI_KEY
    ML_MODEL_NAME = CHATGPT_MODEL_NAME
elif ML_MODEL_PROVIDER in ["Google", "Gemini"]:
    # https://aistudio.google.com/
    ML_MODEL_BASE_URL = GEMINI_OPENAI_URL
    ML_MODEL_API_KEY = CLAUDE_API_KEY
    ML_MODEL_NAME = GEMINI_MODEL_NAME
elif ML_MODEL_PROVIDER in ["Microsoft", "Copilot", "Azure"]:
    ML_MODEL_BASE_URL = COPILOT_OPENAI_URL
    ML_MODEL_API_KEY = COPILOT_OPENAI_KEY
    ML_MODEL_NAME = COPILOT_MODEL_NAME
else:
    # We have a problem ...
    raise("Unknown provider name: " + ML_MODEL_PROVIDER)

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
    """Load the rule configuration file, or an empty configuration.

    An empty configuration means "every rule enabled with its default
    severity", which is what the action does when no config file is given.
    See examples/sample-config.yaml for the expected structure.
    """
    config_file = str(config_file or CONFIG_FILE)
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

    return config
