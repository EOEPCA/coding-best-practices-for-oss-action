#!/bin/sh
set -e

# Match the UID/GID that actually owns the mounted workspace directory, so
# the process can read/write it whether this is a GitHub Actions runner or
# a local `docker run` with a bind-mounted directory.
WORKSPACE_UID=$(stat -c '%u' /github/workspace)
WORKSPACE_GID=$(stat -c '%g' /github/workspace)

if ! getent group "$WORKSPACE_GID" > /dev/null 2>&1; then
    groupadd -g "$WORKSPACE_GID" runnergroup
fi
if ! id -u "$WORKSPACE_UID" > /dev/null 2>&1; then
    useradd -m -u "$WORKSPACE_UID" -g "$WORKSPACE_GID" runneruser
fi

exec gosu "$WORKSPACE_UID":"$WORKSPACE_GID" python3 -m coding_best_practices_for_oss "$@"
