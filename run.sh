#!/usr/bin/env bash
# ── Floor Tiling — Docker run script ────────────────────────────────────────
set -euo pipefail

IMAGE_NAME="floor-tiling"
IMAGE_TAG="${1:-latest}"          # pass a tag as first arg, default: latest
HOST_PORT="${2:-8000}"            # pass a port as second arg, default: 8000
URL="http://localhost:${HOST_PORT}"

# ── Locate Chrome executable ─────────────────────────────────────────────────
find_chrome() {
    case "$(uname -s)" in
        Linux*)
            for bin in google-chrome google-chrome-stable chromium-browser chromium; do
                command -v "$bin" &>/dev/null && echo "$bin" && return
            done ;;
        Darwin*)
            echo "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            return ;;
        CYGWIN*|MINGW*|MSYS*)
            for path in \
                "/c/Program Files/Google/Chrome/Application/chrome.exe" \
                "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
                "${LOCALAPPDATA}/Google/Chrome/Application/chrome.exe"
            do
                [ -f "$path" ] && echo "$path" && return
            done ;;
    esac
    echo ""
}

CHROME="$(find_chrome)"
if [ -z "$CHROME" ]; then
    echo "⚠  Chrome not found — open ${URL} manually."
fi

# ── Start container in background ────────────────────────────────────────────
echo "▶ Starting ${IMAGE_NAME}:${IMAGE_TAG} on port ${HOST_PORT} ..."

docker run \
  --rm \
  --detach \
  --name floor-tiling-app \
  -p "${HOST_PORT}:8000" \
  "${IMAGE_NAME}:${IMAGE_TAG}"

# Stop container automatically when this script exits (Ctrl+C)
trap 'echo ""; echo "▶ Stopping container ..."; docker stop floor-tiling-app 2>/dev/null || true' EXIT

# ── Wait for server to be ready ───────────────────────────────────────────────
echo "⏳ Waiting for server at ${URL}/health ..."
for i in $(seq 1 60); do
    if curl -sf "${URL}/health" &>/dev/null; then
        echo "✔ Server is ready."
        break
    fi
    sleep 2
    if [ "$i" -eq 60 ]; then
        echo "✖ Server did not respond after 120 s. Check: docker logs floor-tiling-app"
        exit 1
    fi
done

# ── Open Chrome: incognito + app window (no frame/address bar) ───────────────
#    --app              → removes all browser chrome (frame bar, tabs, address bar)
#    --incognito        → private session, no history/cache saved
#    --disable-logging  → suppress browser-side log files
#    --log-level=3      → only fatal messages reach stderr (3 = FATAL)
#    --silent-launch    → no startup sound / splash
#    --disable-extensions            → no extensions in the window
#    --disable-background-networking → no telemetry pings
#    --no-first-run                  → skip welcome UI
#    --no-default-browser-check      → skip "set as default" prompt
if [ -n "$CHROME" ]; then
    echo "▶ Opening ${URL} in Chrome (incognito, app mode) ..."
    "$CHROME" \
        --incognito \
        --app="${URL}" \
        --disable-logging \
        --log-level=3 \
        --silent-launch \
        --disable-extensions \
        --disable-background-networking \
        --no-first-run \
        --no-default-browser-check \
        &>/dev/null &
fi

# ── Keep running until Ctrl+C ─────────────────────────────────────────────────
echo "  Press Ctrl+C to stop the container."
docker logs -f floor-tiling-app
