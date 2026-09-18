# Coding Best Practices for Open Source Software

Coding Best Practices for Open Source Software Action

## Execute on the CLI

### Options

Use the `python3 -m coding_best_practices_for_oss --help` to obtain the detailed help:

```
usage: coding-best-practices-for-oss [-h] [--path-to-check PATH_TO_CHECK] [--output-file OUTPUT_FILE] [--output-format {generic,sarif}] [--default-anchor-file DEFAULT_ANCHOR_FILE] [--config-file CONFIG_FILE] [--fail-on-issues]
                                     [--verbose] [--version]

Check whether a project complies with coding best practices.

options:
  -h, --help            show this help message and exit
  --path-to-check PATH_TO_CHECK
                        directory to check (default: .)
  --output-file OUTPUT_FILE
                        report file to write (default: coding-best-practices-report.json)
  --output-format {generic,sarif}
                        report format (default: generic)
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

## Execute as a GitHub Action

In this example GitHub workflow fragment, the tool is applied on the full content of the repository.
GitHub Variables and Secret are used to set the AI model variables.

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
          ai-model-provider: '${{ vars.CBP4OSS_AI_MODEL_PROVIDER }}'
          ai-model-base-url: '${{ vars.CBP4OSS_AI_MODEL_BASE_URL }}'
          ai-model-api-key: '${{ secrets.CBP4OSS_AI_MODEL_API_KEY }}'
          ai-model-name: '${{ vars.CBP4OSS_AI_MODEL_NAME }}'
```
