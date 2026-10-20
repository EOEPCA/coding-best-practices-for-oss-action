FROM python:3.11-slim

COPY pyproject.toml README.md LICENSE makeenv.sh /app/
COPY src /app/src
RUN pip install --no-cache-dir /app

# GitHub Actions provides the workspace at /github/workspace
WORKDIR /github/workspace

# Configure non-root user (1000:100)
RUN useradd -m -u 1000 -g 100 appuser
USER 1000:100

ENTRYPOINT ["python", "-m", "coding_best_practices_for_oss"]
