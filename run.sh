#!/usr/bin/env bash
set -e

pushd "$(dirname "$0")" >/dev/null
source .venv/bin/activate

if [ -z "${MIKUBOT_DISCORD_KEY:-}" ]; then
    export MIKUBOT_DISCORD_KEY="$(cat token.txt)"
fi

if [ -z "${MIKUBOT_SETTINGS_FILE:-}" ]; then
    export MIKUBOT_SETTINGS_FILE="settings.json"
fi

while true; do
    uv run mikubot run
    code=$?

    if [ "$code" -eq 39 ]; then
        echo "Relaunching..."
    else
        echo "Stopping..."
        break
    fi
done

popd >/dev/null
exit $code
