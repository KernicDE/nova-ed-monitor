#!/usr/bin/env bash
# NOVA — Navigation, Operations, and Vessel Assistance
# Launcher script for Linux / macOS
# Usage: ./nova.sh [--update]

set -euo pipefail

NOVA_URL="git+https://github.com/KernicDE/nova-ed-monitor.git"
NOVA_PKG="nova-ed-monitor"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}${*}${NC}"; }
success() { echo -e "${GREEN}${*}${NC}"; }
warn()    { echo -e "${YELLOW}${*}${NC}"; }
error()   { echo -e "${RED}${*}${NC}"; }

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
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip
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

# ── Ensure pip is available ───────────────────────────────────────────────────

if ! $PYTHON -m pip --version &>/dev/null 2>&1; then
    warn "pip not available — installing via get-pip.py..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON
fi

# ── Install or update NOVA ────────────────────────────────────────────────────

if ! $PYTHON -m pip show "$NOVA_PKG" &>/dev/null 2>&1; then
    info "NOVA not installed — installing now..."
    $PYTHON -m pip install --user "$NOVA_URL"
    # Add ~/.local/bin to PATH for this session if needed
    export PATH="$HOME/.local/bin:$PATH"
    success "NOVA installed successfully!"
    echo ""
elif [ "$DO_UPDATE" -eq 1 ]; then
    info "Updating NOVA..."
    $PYTHON -m pip install --user --upgrade "$NOVA_URL"
    export PATH="$HOME/.local/bin:$PATH"
    success "NOVA updated."
    echo ""
else
    success "NOVA is installed."
    info "  Tip: run with --update to check for updates."
    echo ""
fi

# ── Launch NOVA ───────────────────────────────────────────────────────────────

info "Starting NOVA..."
echo ""

export PATH="$HOME/.local/bin:$PATH"

if command -v nova &>/dev/null 2>&1; then
    exec nova
else
    exec $PYTHON -m ed_monitor
fi
