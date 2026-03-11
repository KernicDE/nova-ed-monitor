#!/usr/bin/env bash
# NOVA — Navigation, Operations, and Vessel Assistance
# Launcher script for Linux / macOS
# Usage: ./nova.sh [--update]

set -euo pipefail

NOVA_URL="git+https://github.com/KernicDE/nova-ed-monitor.git"
NOVA_PKG="nova-ed-monitor"
VENV_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nova/venv"

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

DO_UPDATE=0
for arg in "$@"; do
    case "$arg" in
        --update|-u) DO_UPDATE=1 ;;
    esac
done

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
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
        info "Detected Fedora / RHEL — installing Python via dnf..."
        sudo dnf install -y python3 python3-pip
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
# Using a dedicated venv avoids PEP 668 "externally managed environment" errors
# on modern distros (Arch, Ubuntu 23.04+, etc.)

VENV_PIP="$VENV_DIR/bin/pip"
VENV_NOVA="$VENV_DIR/bin/nova"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating NOVA virtual environment at $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
    success "Virtual environment created."
fi

# ── Install or update NOVA inside the venv ────────────────────────────────────

if ! "$VENV_PIP" show "$NOVA_PKG" &>/dev/null 2>&1; then
    info "Installing NOVA..."
    "$VENV_PIP" install --quiet --upgrade pip
    "$VENV_PIP" install "$NOVA_URL"
    success "NOVA installed successfully!"
    echo ""
elif [ "$DO_UPDATE" -eq 1 ]; then
    info "Updating NOVA..."
    "$VENV_PIP" install --upgrade "$NOVA_URL"
    success "NOVA updated."
    echo ""
else
    success "NOVA is ready."
    info "Tip: run with --update to check for updates."
    echo ""
fi

# ── Install global 'nova' command ─────────────────────────────────────────────
# Symlink the venv binary into ~/.local/bin so 'nova' works from anywhere.

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
if [ ! -L "$BIN_DIR/nova" ] || [ "$(readlink "$BIN_DIR/nova")" != "$VENV_NOVA" ]; then
    ln -sf "$VENV_NOVA" "$BIN_DIR/nova"
    success "Installed 'nova' command to $BIN_DIR/nova"
    # Warn if ~/.local/bin is not in PATH
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            warn "Note: $BIN_DIR is not in your PATH."
            warn "Add this to ~/.bashrc or ~/.zshrc to fix it:"
            warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            echo ""
            ;;
    esac
fi

# ── Launch NOVA ───────────────────────────────────────────────────────────────

info "Starting NOVA..."
echo ""

exec "$VENV_NOVA"
