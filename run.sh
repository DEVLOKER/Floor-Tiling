#!/usr/bin/env bash
# ── Floor Tiling — Docker run script ────────────────────────────────────────
# Usage: ./run.sh <version> [port]
#   version   Required. Image tag to run, e.g. 1.0.0
#   port      Optional. Host port to bind (default: 8000)
set -euo pipefail

IMAGE_NAME="floor-tiling"

if [ -z "${1:-}" ]; then
    echo "✖ Version is required."
    echo ""
    echo "Usage: ./run.sh <version> [port]"
    echo "  e.g: ./run.sh 1.0.0"
    echo "  e.g: ./run.sh 1.0.0 9000"
    echo ""
    echo "Available local images:"
    docker images "${IMAGE_NAME}" --format "  {{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" 2>/dev/null || true
    exit 1
fi

IMAGE_TAG="${1:-latest}" # pass an image tag as first arg, default: latest
HOST_PORT="${2:-8000}"   # pass a port as second arg, default: 8000
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

# Stop container automatically when this script exits (Ctrl+C or browser close)
trap '
    echo ""
    echo "▶ Stopping container ..."
    docker stop floor-tiling-app 2>/dev/null || true
    [ -n "${CHROME_PROFILE:-}" ] && rm -rf "$CHROME_PROFILE"
' EXIT

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

# ── Open Chrome: kiosk mode ───────────────────────────────────────────────────
#    --kiosk                        → full-screen, ALL DevTools shortcuts
#                                     (F12, Ctrl+Shift+I/J/C, Ctrl+U) are
#                                     hard-disabled by Chrome — no admin needed.
#    --incognito                    → private session, no history/cache
#    --disable-logging              → suppress browser log files
#    --log-level=3                  → only fatal messages to stderr
#    --disable-extensions           → no extensions loaded
#    --disable-background-networking→ no telemetry pings
#    --no-first-run                 → skip welcome UI
#    --disable-extensions           → no extensions loaded
#    --disable-background-networking→ no telemetry pings
#    --no-first-run                 → skip welcome UI
#    --no-default-browser-check     → skip "set as default" prompt
#    --remote-debugging-port=0      → block CDP remote debugging
CHROME_PID=""
if [ -n "$CHROME" ]; then
    echo "▶ Opening ${URL} in Chrome (kiosk mode) ..."
    echo "  ℹ  To close: Alt+F4 (Windows)  |  Cmd+Q (macOS)  |  Ctrl+W (Linux)"

    # Kill any existing Chrome so the kiosk instance starts fresh
    case "$(uname -s)" in
        Linux*)          pkill -f "chrome|chromium" 2>/dev/null || true ;;
        Darwin*)         pkill -f "Google Chrome"   2>/dev/null || true ;;
        CYGWIN*|MINGW*|MSYS*) taskkill /F /IM chrome.exe /T &>/dev/null || true ;;
    esac
    sleep 1

    # Unique temp profile — forces a standalone process (no hand-off to an
    # existing Chrome instance which would make the PID die in < 1 s).
    CHROME_PROFILE="$(mktemp -d)"

    "$CHROME" \
        --kiosk "${URL}" \
        --incognito \
        --user-data-dir="${CHROME_PROFILE}" \
        --disable-logging \
        --log-level=3 \
        --disable-extensions \
        --disable-background-networking \
        --remote-debugging-port=0 \
        --no-first-run \
        --no-default-browser-check \
        &>/dev/null &
    CHROME_PID=$!

    # Give Chrome a moment to fully initialise before we start watching it
    sleep 3
fi

# ── Keep running until browser closes or Ctrl+C ───────────────────────────────
if [ -n "$CHROME_PID" ]; then
    echo "  Close the browser window or press Ctrl+C to stop."
    # Poll Chrome process; when the window is closed the PID disappears
    while kill -0 "$CHROME_PID" 2>/dev/null; do
        sleep 1
    done
    echo ""
    echo "▶ Browser closed — shutting down ..."
    # EXIT trap fires here automatically → stops the container
else
    echo "  Press Ctrl+C to stop the container."
    docker logs -f floor-tiling-app
fi
