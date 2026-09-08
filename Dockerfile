FROM python:3.11-slim

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN pip install --no-cache-dir /app

# GitHub Actions provides the workspace at /github/workspace
WORKDIR /github/workspace

ENTRYPOINT ["python", "-m", "coding_best_practices_for_oss"]
