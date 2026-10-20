# Coding Best Practices for Open Source Software

Coding Best Practices for Open Source Software Action

## Execute on the CLI

This option requires the tool dependencies to be installed on the local system, preferrably in a virtual environment (see the example execution below).

Alternatively, the tool may also be executed locally using a container with pre-installed dependencies, see below.

### Options

Use the `python3 -m coding_best_practices_for_oss --help` to obtain the detailed help:

```
usage: coding-best-practices-for-oss [-h] [--path-to-check PATH_TO_CHECK] [--output-file OUTPUT_FILE] [--output-format {text,generic,sarif}] [--default-anchor-file DEFAULT_ANCHOR_FILE] [--config-file CONFIG_FILE] [--fail-on-issues]
                                     [--verbose] [--version]

Check whether a project complies with coding best practices.

options:
  -h, --help            show this help message and exit
  --path-to-check PATH_TO_CHECK
                        directory to check (default: .)
  --output-file OUTPUT_FILE
                        report file to write (default: coding-best-practices-report.json)
  --output-format {text,generic,sarif}
                        report format (default: text)
  --default-anchor-file DEFAULT_ANCHOR_FILE
                        file the issues that are not tied to a source file point at (default: coding-best-practices-issues.md)
  --config-file CONFIG_FILE
                        YAML file for enabling/disabling and configuring rules, categories and dependencies
  --fail-on-issues      exit with a non-zero status when issues are found
  --verbose             enable debug logging
  --version             show program's version number and exit
```


### Example Execution

Instructions for executing the library from the repository root folder:

```bash
# Create and activate a local virtual environment
python3 -m venv venv
. venv/bin/activate

# Install the dependencies (see pyproject.toml)
pip install -e .

# Adapt the configuration file as necessary:
# examples/sample-config.toml

# Configure `AI_MODEL` variables to apply rules relying on an AI model.
# The provider must expose an [OpenAI SDK](https://developers.openai.com/api/docs/libraries) compatible endpoint.
# Example:
export AI_MODEL_PROVIDER=Anthropic
export AI_MODEL_BASE_URL=https://api.anthropic.com/v1
export AI_MODEL_API_KEY=...
export AI_MODEL_NAME=claude-sonnet-4.6

python3 -m coding_best_practices_for_oss --path /path/to/project --config examples/sample-config.yaml
```


## Execute as a Containerised CLI Tool

The tool is available as a pre-built Docker image with all its dependencies installed.

Refer to Docker Hub for the latest available version (tagged with either a date or a version number): https://hub.docker.com/r/eoepca/coding-best-practices-for-oss

The tool uses environment variables for its high-level configuration, and a configuration file for a refined control of the rules to be applied.

Environment variables:

|        Name         |                             Description                             |              Default              |
| ------------------- | ------------------------------------------------------------------- | --------------------------------- |
| PATH_TO_CHECK       | Relative to /github/workspace                                       | .                                 |
| OUTPUT_FILE         | Report file name                                                    | coding-best-practices-report.json |
| OUTPUT_FORMAT       | Report format: 'text' (human readable), 'generic' (SonarQube compatible) or 'sarif'     | text          |
| DEFAULT_ANCHOR_FILE | Default anchor file, used for issues not related to a specific file | coding-best-practices-issues.md   |
| CONFIG_FILE         | Rules configuration file                                            | examples/sample-config.yaml       |
| VERBOSE             | Enable debug logging: 'true', 'false'                               | false                             |
| AI_MODEL_ENABLED    | Whether an independent AI model must be used                        | true                              |
| AI_MODEL_PROVIDER   | AI model provider name (free string)                                | Ollama                            |
| AI_MODEL_BASE_URL   | AI model service endpoint                                           | http://hostname:11434/v1          |
| AI_MODEL_API_KEY    | AI model API key (any string for Ollama)                            | ollama                            |
| AI_MODEL_NAME       | AI model name                                                       | llama3                            |


If AI model integration is disabled, the rules that rely on this are automatically disabled.

Example configuration for major AI model providers:

|               Anthropic / Claude               |
| ---------------------------------------------- |
| AI_MODEL_PROVIDER=Anthropic                    |
| AI_MODEL_BASE_URL=https://api.anthropic.com/v1 |
| AI_MODEL_API_KEY=\<key\>                       |
| AI_MODEL_NAME=claude-sonnet-4.6                |

|              OpenAPI / ChatGPT              |
| ------------------------------------------- |
| AI_MODEL_PROVIDER=OpenAPI                   |
| AI_MODEL_BASE_URL=https://api.openai.com/v1 |
| AI_MODEL_API_KEY=\<key\>                    |
| AI_MODEL_NAME=gpt-4o                        |

|                              Google / Gemini                              |
| ------------------------------------------------------------------------- |
| AI_MODEL_PROVIDER=Google                                                  |
| AI_MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai |
| AI_MODEL_API_KEY=\<key\>                                                  |
| AI_MODEL_NAME=models/gemini-2.5-flash                                     |

|               Microsoft / Copilot / Azure               |
| ------------------------------------------------------- |
| AI_MODEL_PROVIDER=Microsoft                             |
| AI_MODEL_BASE_URL=https://models.inference.ai.azure.com |
| AI_MODEL_API_KEY=\<key\>                                |
| AI_MODEL_NAME=                                          |


### Setup

The Docker image includes a script that may be used to generate the environment file `setup.env`:

```bash
docker run --rm -it \
  -v .:/github/workspace  \
  --entrypoint /app/makeenv.sh \
  eoepca/coding-best-practices-for-oss:<tag>
```

This commands generates a `setup.env` file in the current directory with owner ID=1000 and group ID=100.

If this is not appropriate, specific user and group IDs may be provided.

For example, use the following commant to generate a file owned by the current user:

```bash
docker run --rm -it \
  -u $(id -u):$(id -g) \
  -v .:/github/workspace  \
  --entrypoint /app/makeenv.sh \
  coding-best-practices-for-oss:2026-10-19
```

The script asks for the variables one by one, then generates the `setup.env` file:

```
=== Environment Variables Configuration Generator ===
Documentation: https://github.com/EOEPCA/coding-best-practices-for-oss-action/
Press ENTER to accept the [default] value.

Path to check (relative to /github/workspace) [.]: 
Report format (text|generic|sarif) [text]: 
Report file name [coding-best-practices-report.txt]: 
Default anchor file [coding-best-practices-issues.md]: 
Configuration file [examples/sample-config.yaml]: 

Do you want to enable verbose logging? (y/N): 

Do you want to enable AI integration? (y/N): y

--- AI Model Configuration ---
AI model provider (free name) [Ollama]: 
AI model base URL [http://hostname:11434/v1]: 
AI model API key []: ollama
AI model name [llama3]: qwen2.5-coder:14B

✅ Environment configuration saved to 'setup.env'.
To use the variables in a container, add the '--env-file' parameter:
   docker run --env-file setup.env <OPTIONS> <IMAGE_NAME>
```

When the script is re-executed, it detects the presence of the `setup.env` file and proposes the values stored in it as default values.

Generated `setup.env` file:

```bash
# Generated Environment Variables
PATH_TO_CHECK=.
OUTPUT_FORMAT=text
OUTPUT_FILE=coding-best-practices-report.txt
DEFAULT_ANCHOR_FILE=coding-best-practices-issues.md
CONFIG_FILE=examples/sample-config.yaml
VERBOSE=false
AI_MODEL_ENABLED=true
AI_MODEL_PROVIDER=Ollama
AI_MODEL_BASE_URL=http://hostname:11434/v1
AI_MODEL_API_KEY=ollama
AI_MODEL_NAME=qwen2.5-coder:14B
```

### Execution

Execute the following command to analyse source code, replacing `<path-to-source-code>` as appropriate:

```bash
docker run --rm -it \
  --env-file setup.env \
  -v <path-to-source-code>:/github/workspace  \
  coding-best-practices-for-oss:2026-10-19
```

### Example Execution

Output of the validation tool when applied to its own source code (`PATH_TO_CHECK=src`):

```
2026-10-19 17:02:25  INFO    Loaded configuration file: examples/sample-config.yaml
2026-10-19 17:02:26  INFO    Checking /github/workspace/src with 9 project rule(s) and 0 file rule(s)
2026-10-19 17:02:26  INFO    [DOC001] ❌ README (md, rst, txt) file missing in folder src
2026-10-19 17:02:26  INFO    [DOC004] ❌ Python CLI script must provide help: coding_best_practices_for_oss/__main__.py: Python script appears to be a CLI entry point but no --help support was detected (no argparse/click usage, and no manual '--help' handling found).
2026-10-19 17:02:26  INFO    [DOC004] ✅ Python CLI script provides help: coding_best_practices_for_oss/cli.py
2026-10-19 17:02:26  INFO    [DOC004] ✅ Python CLI script provides help: coding_best_practices_for_oss/rules/documentation/python_script_help.py
2026-10-19 17:02:26  INFO    [LNG002] Found 41 files; will scan them in chucks with --max-files=20
2026-10-19 17:02:39  INFO    [LNG001] ✅ No exotic languages used in src: JSON (popular), Python (popular)
2026-10-19 17:02:39  INFO    [LNG002] Found 41 files; will scan them in chucks with --max-files=20
2026-10-19 17:02:39  INFO    [LNG002] Detected 2 different languages used in 'src'
2026-10-19 17:02:39  INFO    [LNG002] ✅ Too Many Languages: Identified 2 different languages in 'src' (fine): JSON, Python
Keeping this 'print()' call for testing purpose
2026-10-19 17:02:39  INFO    [RES001] ❌ Found 11 print()/pprint() usage(s):
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:248:9 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:253:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:254:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:255:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:256:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:257:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:258:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:259:5 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:262:9 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/documentation/python_script_help.py:264:13 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES001] coding_best_practices_for_oss/rules/resilience/ban_print.py:38:13 [ruff T201] `print` found
2026-10-19 17:02:39  INFO    [RES002] ❌ Found 11 except blocks without logging
2026-10-19 17:02:39  INFO    [RES003] ❌ Found 2 mishandled exceptions:
2026-10-19 17:02:39  INFO    [RES003] coding_best_practices_for_oss/core/registry.py:27:16 [ruff BLE001] Do not catch blind exception: `Exception`
2026-10-19 17:02:39  INFO    [RES003] coding_best_practices_for_oss/core/registry.py:64:16 [ruff BLE001] Do not catch blind exception: `Exception`
2026-10-19 17:02:39  INFO    Done: 28 issue(s) found by 9 rule(s) on 34 file(s) in 13.55s
2026-10-19 17:02:39  INFO    Successfully saved: coding-best-practices-report.txt
```

Detailed information about each rule and each detected issue can be found in the generated report (by default: `coding-best-practices-report.txt`).


## Execute as a GitHub Action

In this example GitHub workflow fragment, the tool is applied on the full content of the repository.
GitHub Variables and Secret are used to set the AI model variables.

When executed in a terminal (see above), a textual, human readable, output is preferred, however the `generic` format should be used when executed in a GitHub workflow, as this produces a report that may be submitted to SonarQube.

See `action.yaml` for the definition and default values of the GitHub Action input variables.

```yaml
#...

jobs:
  analyze-and-report:
    runs-on: ubuntu-latest

    # ...

    steps:
      # Apply Coding Best Practices for Open Source Software
      - name: Coding Best Practices for OSS
        uses: EOEPCA/coding-best-practices-for-oss-action@main
        with:
          path-to-check: '.'
          output-file: 'reports/coding-best-practices-report.json'
          output-format: 'generic'
          default-anchor-file: 'backend/coding-best-practices-issues.md'
          config-file: 'examples/sample-config.yaml'
          verbose: 'false'
          ai-model-provider: '${{ vars.CBP4OSS_AI_MODEL_PROVIDER }}'
          ai-model-base-url: '${{ vars.CBP4OSS_AI_MODEL_BASE_URL }}'
          ai-model-api-key: '${{ secrets.CBP4OSS_AI_MODEL_API_KEY }}'
          ai-model-name: '${{ vars.CBP4OSS_AI_MODEL_NAME }}'
```
