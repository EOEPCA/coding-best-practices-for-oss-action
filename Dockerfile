FROM python:3.11-slim
COPY main.py /main.py

# GitHub Actions provides the workspace at /github/workspace
WORKDIR /github/workspace

ENTRYPOINT ["python", "/main.py"]