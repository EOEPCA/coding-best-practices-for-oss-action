FROM python:3.13-slim

ARG GOSU_VERSION=1.17

#  Install 'gosu' without using 'apt-get'
RUN python3 -c "\
import os, platform, urllib.request; \
arch_map = {'x86_64': 'amd64', 'aarch64': 'arm64', 'armv7l': 'armhf'}; \
arch = arch_map.get(platform.machine(), 'amd64'); \
url = f'https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-{arch}'; \
urllib.request.urlretrieve(url, '/usr/local/bin/gosu'); \
os.chmod('/usr/local/bin/gosu', 0o755)" && \
    /usr/local/bin/gosu --version

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN pip install --no-cache-dir /app

COPY entrypoint.sh makeenv.sh /
RUN chmod +x /entrypoint.sh /makeenv.sh

WORKDIR /github/workspace

ENTRYPOINT ["/entrypoint.sh"]