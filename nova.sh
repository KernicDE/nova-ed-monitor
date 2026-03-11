#!/usr/bin/env bash
# NOVA — Navigation, Operations, and Vessel Assistance
# Launcher script for Linux / macOS
# Usage: ./nova.sh [--update]

set -euo pipefail

NOVA_URL="git+https://github.com/KernicDE/nova-ed-monitor.git"
NOVA_PKG="nova-ed-monitor"
VENV_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nova/venv"
SCRIPT_URL="https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh"
GH_API_URL="https://api.github.com/repos/KernicDE/nova-ed-monitor/releases/latest"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}  ${*}${NC}"; }
success() { echo -e "${GREEN}  ${*}${NC}"; }
warn()    { echo -e "${YELLOW}  ${*}${NC}"; }
error()   { echo -e "${RED}  ${*}${NC}"; }

# ── Parse args ────────────────────────────────────────────────────────────────

SELF_UPDATE=1   # set to 0 after self-update to avoid loop
for arg in "$@"; do
    case "$arg" in
        --no-self-update) SELF_UPDATE=0 ;;
    esac
done

# ── Banner ────────────────────────────────────────────────────────────────────

echo -e "${BOLD}${CYAN}"
echo "  ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗ "
echo "  ████╗  ██║██╔═══██╗██║   ██║██╔══██╗"
echo "  ██╔██╗ ██║██║   ██║██║   ██║███████║"
echo "  ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║"
echo "  ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║"
echo "  ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝"
echo -e "${NC}"
echo "  Navigation, Operations, and Vessel Assistance"
echo "  ─────────────────────────────────────────────"
echo ""

SCRIPT_SELF="$(realpath "$0")"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_NOVA="$VENV_DIR/bin/nova"

# ── Self-update ───────────────────────────────────────────────────────────────
# Download the latest nova.sh from GitHub; replace self and re-exec if changed.

if [ "$SELF_UPDATE" -eq 1 ] && command -v curl &>/dev/null; then
    tmp=$(mktemp)
    if curl -fsSL --max-time 8 "$SCRIPT_URL" -o "$tmp" 2>/dev/null; then
        old_hash=$(sha256sum "$SCRIPT_SELF" | cut -d' ' -f1)
        new_hash=$(sha256sum "$tmp"         | cut -d' ' -f1)
        if [ "$old_hash" != "$new_hash" ]; then
            info "Script update found — applying..."
            chmod +x "$tmp"
            mv "$tmp" "$SCRIPT_SELF"
            success "Script updated. Restarting..."
            echo ""
            exec "$SCRIPT_SELF" --no-self-update "$@"
        fi
    fi
    rm -f "$tmp" 2>/dev/null || true
fi

# ── Find Python 3.11+ ─────────────────────────────────────────────────────────

find_python() {
    for cmd in python3 python python3.13 python3.12 python3.11; do
        if command -v "$cmd" &>/dev/null 2>&1; then
            ok=$("$cmd" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")
            if [ "$ok" = "True" ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=""
if ! PYTHON=$(find_python); then
    warn "Python 3.11+ not found. Attempting to install..."
    echo ""

    if command -v pacman &>/dev/null; then
        info "Detected Arch Linux / Manjaro — installing Python via pacman..."
        sudo pacman -S --noconfirm python
    elif command -v apt-get &>/dev/null; then
        info "Detected Debian / Ubuntu / Mint — installing Python via apt..."
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv
    elif command -v dnf &>/dev/null; then
        info "Detected Fedora / RHEL — installing Python via dnf..."
        sudo dnf install -y python3
    elif command -v brew &>/dev/null; then
        info "Detected macOS / Homebrew — installing Python via brew..."
        brew install python3
    else
        error "Cannot auto-install Python on this system."
        error "Please install Python 3.11+ from https://www.python.org/downloads/"
        exit 1
    fi

    PYTHON=$(find_python) || {
        error "Python installation succeeded but still not found in PATH."
        error "Please open a new terminal and run this script again."
        exit 1
    }
fi

success "Python: $($PYTHON --version)"

# ── Set up virtual environment ────────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
    info "Creating NOVA virtual environment at $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
    success "Virtual environment created."
fi

# ── Install or auto-update NOVA ───────────────────────────────────────────────

if ! "$VENV_PIP" show "$NOVA_PKG" &>/dev/null 2>&1; then
    info "Installing NOVA..."
    "$VENV_PIP" install --quiet --upgrade pip
    "$VENV_PIP" install "$NOVA_URL"
    success "NOVA installed successfully!"
    echo ""
else
    # Compare installed version against latest GitHub release
    installed_ver=$("$VENV_PIP" show "$NOVA_PKG" 2>/dev/null \
        | grep '^Version:' | awk '{print $2}')

    latest_ver=""
    if command -v curl &>/dev/null; then
        latest_ver=$(curl -fsSL --max-time 8 "$GH_API_URL" 2>/dev/null \
            | $PYTHON -c "
import sys, json
try:
    tag = json.load(sys.stdin).get('tag_name', '')
    print(tag.lstrip('v'))
except Exception:
    pass
" 2>/dev/null || true)
    fi

    if [ -n "$latest_ver" ] && [ "$installed_ver" != "$latest_ver" ]; then
        info "Update available: $installed_ver → $latest_ver — updating..."
        "$VENV_PIP" install --upgrade "$NOVA_URL"
        success "NOVA updated to $latest_ver."
        echo ""
    else
        success "NOVA $installed_ver is up to date."
        echo ""
    fi
fi

# ── Install global 'nova' command ─────────────────────────────────────────────

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
if [ ! -L "$BIN_DIR/nova" ] || [ "$(readlink "$BIN_DIR/nova")" != "$VENV_NOVA" ]; then
    ln -sf "$VENV_NOVA" "$BIN_DIR/nova"
    success "Installed 'nova' command to $BIN_DIR/nova"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            warn "Note: $BIN_DIR is not in your PATH."
            warn "Add this to ~/.bashrc or ~/.zshrc:"
            warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            echo ""
            ;;
    esac
fi

# ── Launch NOVA ───────────────────────────────────────────────────────────────

info "Starting NOVA..."
echo ""

exec "$VENV_NOVA"
