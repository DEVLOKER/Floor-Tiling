#!/usr/bin/env bash
# ── Floor Tiling — Dependency installer ─────────────────────────────────────
# Installs Docker and Google Chrome depending on the current OS.
#
# Supported platforms:
#   Linux   → Ubuntu/Debian (apt), Fedora/RHEL (dnf), Arch (pacman)
#   macOS   → Homebrew (installs brew if missing)
#   Windows → Git Bash / MSYS2 / WSL via winget or Chocolatey
set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo "  $*"; }
success() { echo "✔ $*"; }
warn()    { echo "⚠  $*"; }
error()   { echo "✖ $*" >&2; exit 1; }

require_root() {
    if [ "$EUID" -ne 0 ] && ! sudo -n true 2>/dev/null; then
        warn "Some steps need sudo — you may be prompted for your password."
    fi
}

command_exists() { command -v "$1" &>/dev/null; }

# ── Detect OS ─────────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux*)
        if [ -f /etc/os-release ]; then
            # shellcheck disable=SC1091
            . /etc/os-release
            DISTRO="${ID:-unknown}"
        else
            DISTRO="unknown"
        fi
        ;;
    Darwin*)  DISTRO="macos" ;;
    CYGWIN*|MINGW*|MSYS*) DISTRO="windows" ;;
    *) error "Unsupported OS: $OS" ;;
esac

echo "──────────────────────────────────────────────────────────"
echo "  Floor Tiling — Dependency Installer"
echo "  Detected OS : $OS  ($DISTRO)"
echo "──────────────────────────────────────────────────────────"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# macOS
# ═══════════════════════════════════════════════════════════════════════════════
install_macos() {
    # ── Homebrew ──────────────────────────────────────────────────────────────
    if ! command_exists brew; then
        info "Installing Homebrew ..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add brew to PATH for Apple Silicon
        if [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        success "Homebrew installed."
    else
        info "Homebrew already installed — updating ..."
        brew update --quiet
    fi

    # ── Docker ────────────────────────────────────────────────────────────────
    if ! command_exists docker; then
        info "Installing Docker Desktop ..."
        brew install --cask docker
        success "Docker Desktop installed. Launch it from Applications to start the daemon."
    else
        success "Docker already installed: $(docker --version)"
    fi

    # ── Docker autostart on login ─────────────────────────────────────────────
    info "Enabling Docker Desktop to start at login ..."
    osascript -e \
        'tell application "System Events" to make login item at end with properties \
         {path:"/Applications/Docker.app", hidden:true}' 2>/dev/null \
        && success "Docker Desktop will start at login." \
        || warn "Could not add Docker to Login Items — enable it manually in Docker Desktop → Settings → General → Start Docker Desktop when you sign in."

    # ── Chrome ────────────────────────────────────────────────────────────────
    if [ ! -d "/Applications/Google Chrome.app" ]; then
        info "Installing Google Chrome ..."
        brew install --cask google-chrome
        success "Google Chrome installed."
    else
        success "Google Chrome already installed."
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Windows (Git Bash / MSYS2)
# ═══════════════════════════════════════════════════════════════════════════════
install_windows() {
    # Prefer winget (available on Windows 10 1709+), fall back to Chocolatey
    if command_exists winget; then
        info "Using winget ..."

        # ── Docker ────────────────────────────────────────────────────────────
        if ! command_exists docker; then
            info "Installing Docker Desktop ..."
            winget install --id Docker.DockerDesktop -e --silent --accept-package-agreements --accept-source-agreements
            success "Docker Desktop installed. Launch it to start the daemon."
        else
            success "Docker already installed: $(docker --version)"
        fi

        # ── Docker autostart on login ──────────────────────────────────────────
        info "Enabling Docker Desktop to start at login (registry) ..."
        DOCKER_EXE="C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"
        reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" \
            /v "Docker Desktop" /t REG_SZ \
            /d "\"${DOCKER_EXE}\"" /f &>/dev/null \
            && success "Docker Desktop will start at login." \
            || warn "Could not set registry key — enable it manually in Docker Desktop → Settings → General → Start Docker Desktop when you sign in."

        # ── Chrome ────────────────────────────────────────────────────────────
        CHROME_PATH="$LOCALAPPDATA/Google/Chrome/Application/chrome.exe"
        if [ ! -f "$CHROME_PATH" ]; then
            info "Installing Google Chrome ..."
            winget install --id Google.Chrome -e --silent --accept-package-agreements --accept-source-agreements
            success "Google Chrome installed."
        else
            success "Google Chrome already installed."
        fi

    elif command_exists choco; then
        info "Using Chocolatey ..."

        if ! command_exists docker; then
            info "Installing Docker Desktop ..."
            choco install docker-desktop -y
            success "Docker Desktop installed. Launch it to start the daemon."
        else
            success "Docker already installed: $(docker --version)"
        fi

        # ── Docker autostart on login ──────────────────────────────────────────
        info "Enabling Docker Desktop to start at login (registry) ..."
        DOCKER_EXE="C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"
        reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" \
            /v "Docker Desktop" /t REG_SZ \
            /d "\"${DOCKER_EXE}\"" /f &>/dev/null \
            && success "Docker Desktop will start at login." \
            || warn "Could not set registry key — enable it manually in Docker Desktop → Settings → General → Start Docker Desktop when you sign in."

        CHROME_PATH="$LOCALAPPDATA/Google/Chrome/Application/chrome.exe"
        if [ ! -f "$CHROME_PATH" ]; then
            info "Installing Google Chrome ..."
            choco install googlechrome -y
            success "Google Chrome installed."
        else
            success "Google Chrome already installed."
        fi

    else
        warn "Neither winget nor Chocolatey found."
        echo ""
        echo "Install manually:"
        echo "  Docker Desktop : https://www.docker.com/products/docker-desktop/"
        echo "  Google Chrome  : https://www.google.com/chrome/"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Linux — Ubuntu / Debian
# ═══════════════════════════════════════════════════════════════════════════════
install_debian() {
    require_root

    sudo apt-get update -qq

    # ── Docker ────────────────────────────────────────────────────────────────
    if ! command_exists docker; then
        info "Installing Docker (official apt repository) ..."
        sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release

        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg

        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
            https://download.docker.com/linux/${DISTRO} \
            $(lsb_release -cs) stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

        sudo apt-get update -qq
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

        # Allow current user to run docker without sudo
        sudo usermod -aG docker "$USER"
        success "Docker installed. Log out and back in for group changes to take effect."
    else
        success "Docker already installed: $(docker --version)"
    fi

    # ── Docker autostart on boot ───────────────────────────────────────────────
    info "Enabling Docker service to start on boot ..."
    sudo systemctl enable docker
    sudo systemctl enable containerd
    success "Docker will start automatically on boot."

    # ── Chrome ────────────────────────────────────────────────────────────────
    if ! command_exists google-chrome && ! command_exists google-chrome-stable; then
        info "Installing Google Chrome ..."
        TMP_DEB="$(mktemp /tmp/chrome-XXXXXX.deb)"
        curl -fsSL "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb" -o "$TMP_DEB"
        sudo apt-get install -y "$TMP_DEB"
        rm -f "$TMP_DEB"
        success "Google Chrome installed."
    else
        success "Google Chrome already installed."
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Dispatch
# ═══════════════════════════════════════════════════════════════════════════════
case "$DISTRO" in
    macos)                       install_macos   ;;
    windows)                     install_windows ;;
    ubuntu|debian|linuxmint|pop) install_debian  ;;
    *) error "Unsupported distro '${DISTRO}'. Supported: macOS, Windows, Ubuntu/Debian." ;;
esac

echo ""
echo "──────────────────────────────────────────────────────────"
success "All done! Verify your installation:"
echo "  docker --version"
echo "  google-chrome --version  (or open Chrome from Applications)"
echo "──────────────────────────────────────────────────────────"
