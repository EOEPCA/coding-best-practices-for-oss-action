#!/usr/bin/env bash

set -euo pipefail

ENV_FILE="setup.env"

# Load existing environment file if it exists to preserve past choices
if [ -f "${ENV_FILE}" ]; then
    echo "ℹ️ Existing configuration '${ENV_FILE}' found. Loading default values from it..."
    # Suppress unbound variable check temporarily during sourcing
    set +u
    source "${ENV_FILE}"
    set -u
    echo ""
fi

echo "=== Environment Variables Configuration Generator ==="
echo "Documentation: https://github.com/EOEPCA/coding-best-practices-for-oss-action/"
echo "Press ENTER to accept the [default] value."
echo ""

# Helper function to prompt with a dynamic default value
prompt_var() {
    local prompt_text="$1"
    local default_val="$2"
    local user_input

    read -r -p "${prompt_text} [${default_val}]: " user_input
    echo "${user_input:-$default_val}"
}

# Standard Configuration Prompts (Using existing env variables or fallbacks)
PATH_TO_CHECK=$(prompt_var "Path to check (relative to /github/workspace)" "${PATH_TO_CHECK:-.}")

# Prompt for OUTPUT_FORMAT with strict validation
CURRENT_FORMAT="${OUTPUT_FORMAT:-text}"
while true; do
    OUTPUT_FORMAT=$(prompt_var "Report format (text|generic|sarif)" "${CURRENT_FORMAT}")
    OUTPUT_FORMAT=$(echo "${OUTPUT_FORMAT}" | tr '[:upper:]' '[:lower:]')
    
    if [[ "${OUTPUT_FORMAT}" == "text" || "${OUTPUT_FORMAT}" == "generic" || "${OUTPUT_FORMAT}" == "sarif" ]]; then
        break
    else
        echo "❌ Invalid output format '${OUTPUT_FORMAT}'. Allowed values are 'text', 'generic' and 'sarif'."
    fi
done

if [ "${OUTPUT_FORMAT}" = "text" ]; then
    OUTPUT_FILE=$(prompt_var "Report file name" "${OUTPUT_FILE:-coding-best-practices-report.txt}")
else
    OUTPUT_FILE=$(prompt_var "Report file name" "${OUTPUT_FILE:-coding-best-practices-report.json}")
fi

DEFAULT_ANCHOR_FILE=$(prompt_var "Default anchor file" "${DEFAULT_ANCHOR_FILE:-coding-best-practices-issues.md}")
CONFIG_FILE=$(prompt_var "Rules configuration file" "${CONFIG_FILE:-examples/sample-config.yaml}")

# Verbose Configuration Prompt
CURRENT_VERBOSE_ENABLED="${VERBOSE:-false}"
DEFAULT_VERBOSE_PROMPT="y/N"
if [ "${CURRENT_VERBOSE_ENABLED}" = "true" ]; then
    DEFAULT_VERBOSE_PROMPT="Y/n"
fi

echo ""
read -r -p "Do you want to enable verbose logging? (${DEFAULT_VERBOSE_PROMPT}): " ENABLE_VERBOSE_RESPONSE
ENABLE_VERBOSE_RESPONSE=$(echo "${ENABLE_VERBOSE_RESPONSE}" | tr '[:upper:]' '[:lower:]')

# Resolve enable/disable selection based on existing state and user prompt
if [ -z "${ENABLE_VERBOSE_RESPONSE}" ]; then
    IS_VERBOSE_ENABLED="${CURRENT_VERBOSE_ENABLED}"
elif [[ "${ENABLE_VERBOSE_RESPONSE}" == "y" || "${ENABLE_VERBOSE_RESPONSE}" == "yes" ]]; then
    IS_VERBOSE_ENABLED="true"
else
    IS_VERBOSE_ENABLED="false"
fi

# AI Configuration Prompt
CURRENT_AI_ENABLED="${AI_MODEL_ENABLED:-false}"
DEFAULT_AI_PROMPT="y/N"
if [ "${CURRENT_AI_ENABLED}" = "true" ]; then
    DEFAULT_AI_PROMPT="Y/n"
fi

echo ""
read -r -p "Do you want to enable AI integration? (${DEFAULT_AI_PROMPT}): " ENABLE_AI_RESPONSE
ENABLE_AI_RESPONSE=$(echo "${ENABLE_AI_RESPONSE}" | tr '[:upper:]' '[:lower:]')

# Resolve enable/disable selection based on existing state and user prompt
if [ -z "${ENABLE_AI_RESPONSE}" ]; then
    IS_AI_ENABLED="${CURRENT_AI_ENABLED}"
elif [[ "${ENABLE_AI_RESPONSE}" == "y" || "${ENABLE_AI_RESPONSE}" == "yes" ]]; then
    IS_AI_ENABLED="true"
else
    IS_AI_ENABLED="false"
fi

AI_MODEL_ENABLED="${IS_AI_ENABLED}"

if [ "${AI_MODEL_ENABLED}" = "true" ]; then
    echo ""
    echo "--- AI Model Configuration ---"
    AI_MODEL_PROVIDER=$(prompt_var "AI model provider (free name)" "${AI_MODEL_PROVIDER:-Ollama}")
    AI_MODEL_BASE_URL=$(prompt_var "AI model base URL" "${AI_MODEL_BASE_URL:-http://hostname:11434/v1}")
    AI_MODEL_API_KEY=$(prompt_var "AI model API key" "${AI_MODEL_API_KEY:-}")
    AI_MODEL_NAME=$(prompt_var "AI model name" "${AI_MODEL_NAME:-llama3}")
# else
#     AI_MODEL_PROVIDER=""
#     AI_MODEL_BASE_URL=""
#     AI_MODEL_API_KEY=""
#     AI_MODEL_NAME=""
fi

# Write variables to the environment file
cat <<EOF > "${ENV_FILE}"
# Generated Environment Variables
PATH_TO_CHECK=${PATH_TO_CHECK}
OUTPUT_FILE=${OUTPUT_FILE}
OUTPUT_FORMAT=${OUTPUT_FORMAT}
DEFAULT_ANCHOR_FILE=${DEFAULT_ANCHOR_FILE}
CONFIG_FILE=${CONFIG_FILE}
VERBOSE=${IS_VERBOSE_ENABLED}
AI_MODEL_ENABLED=${AI_MODEL_ENABLED}
EOF

if [ "${AI_MODEL_ENABLED}" = "true" ]; then
    cat <<EOF >> "${ENV_FILE}"
AI_MODEL_PROVIDER=${AI_MODEL_PROVIDER}
AI_MODEL_BASE_URL=${AI_MODEL_BASE_URL}
AI_MODEL_API_KEY=${AI_MODEL_API_KEY}
AI_MODEL_NAME=${AI_MODEL_NAME}
EOF
fi

echo ""
echo "✅ Environment configuration saved to '${ENV_FILE}'."
echo "To use the variables in a container, add the '--env-file' parameter:"
echo "   docker run --env-file ${ENV_FILE} <OPTIONS> <IMAGE_NAME>"
