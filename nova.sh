#!/usr/bin/env bash
# NOVA — Navigation, Operations, and Vessel Assistance
# Portable launcher — all data lives next to this script.
# Usage: ./nova.sh [--uninstall]

set -euo pipefail

NOVA_URL="git+https://github.com/KernicDE/nova-ed-monitor.git"
NOVA_PKG="nova-ed-monitor"
SCRIPT_URL="https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh"
GH_API_URL="https://api.github.com/repos/KernicDE/nova-ed-monitor/releases/latest"

# Portable root = directory containing this script (all data lives here)
SCRIPT_SELF="$(realpath "$0")"
PORTABLE_ROOT="$(cd "$(dirname "$SCRIPT_SELF")" && pwd)"
VENV_DIR="$PORTABLE_ROOT/venv"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_NOVA="$VENV_DIR/bin/nova"

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

# ── Detect package manager ────────────────────────────────────────────────────
# Reads /etc/os-release before falling back to command presence — prevents
# false apt-get matches on RPM-based systems.

detect_pm() {
    # Fedora Atomic / Bazzite / Silverblue use rpm-ostree, not dnf
    if [ -f /run/ostree-booted ] && command -v rpm-ostree &>/dev/null; then
        echo "rpm-ostree"
        return
    fi
    if [ -f /etc/os-release ]; then
        local _id _id_like
        _id=$(. /etc/os-release && echo "${ID:-}")
        _id_like=$(. /etc/os-release && echo "${ID_LIKE:-}")
        case "$_id $_id_like" in
            *fedora*|*rhel*|*centos*|*rocky*|*alma*|*nobara*) echo "dnf";    return ;;
            *debian*|*ubuntu*)                                 echo "apt";    return ;;
            *arch*|*manjaro*)                                  echo "pacman"; return ;;
        esac
    fi
    command -v pacman  &>/dev/null && echo "pacman" && return
    command -v dnf     &>/dev/null && echo "dnf"    && return
    command -v apt-get &>/dev/null && echo "apt"    && return
    command -v brew    &>/dev/null && echo "brew"   && return
    echo "unknown"
}

_PM=$(detect_pm)

# ── Parse args ────────────────────────────────────────────────────────────────

SELF_UPDATE=1
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

# ── Uninstall ─────────────────────────────────────────────────────────────────

if [ "${1:-}" = "--uninstall" ]; then
    echo ""
    warn "This will permanently remove the entire NOVA directory:"
    warn "  $PORTABLE_ROOT"
    echo ""
    warn "Elite Dangerous journal files will NOT be touched."
    echo ""
    printf "  Confirm uninstall? [y/N] "
    read -r _answer
    if [ "$_answer" = "y" ] || [ "$_answer" = "Y" ]; then
        rm -rf "$PORTABLE_ROOT"
        success "NOVA uninstalled."
    else
        echo "  Cancelled."
    fi
    exit 0
fi

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
    for cmd in python3 python python3.14 python3.13 python3.12 python3.11; do
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

    case "$_PM" in
        pacman) info "Detected Arch Linux / Manjaro — installing Python via pacman..."
                sudo pacman -S --noconfirm python ;;
        apt)    info "Detected Debian / Ubuntu / Mint — installing Python via apt..."
                sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv ;;
        dnf)    info "Detected Fedora / RHEL — installing Python via dnf..."
                sudo dnf install -y python3 ;;
        rpm-ostree)
                info "Detected Fedora Atomic / Bazzite — installing Python via rpm-ostree..."
                sudo rpm-ostree install -y python3 python3-devel
                warn "rpm-ostree changes may require a reboot to take effect."
                warn "If NOVA fails to start, please reboot and try again." ;;
        brew)   info "Detected macOS / Homebrew — installing Python via brew..."
                brew install python3 ;;
        *)      error "Cannot auto-install Python on this system."
                error "Please install Python 3.11+ from https://www.python.org/downloads/"
                exit 1 ;;
    esac

    PYTHON=$(find_python) || {
        error "Python installation succeeded but still not found in PATH."
        error "Please open a new terminal and run this script again."
        exit 1
    }
fi

success "Python: $($PYTHON --version)"

# ── Ensure SDL2 build dependencies (needed if pygame must compile from source) ─

ensure_build_deps() {
    local has_sdl2=0 has_pydevel=0
    { command -v sdl2-config &>/dev/null 2>&1 || pkg-config --exists sdl2 2>/dev/null; } && has_sdl2=1
    $PYTHON -c "
import sysconfig, os
h = os.path.join(sysconfig.get_path('include'), 'Python.h')
exit(0 if os.path.exists(h) else 1)
" 2>/dev/null && has_pydevel=1

    [ $has_sdl2 -eq 1 ] && [ $has_pydevel -eq 1 ] && return 0

    warn "Missing build dependencies — installing..."
    case "$_PM" in
        pacman) sudo pacman -S --noconfirm --needed sdl2 freetype2 python ;;
        apt)    sudo apt-get install -y libsdl2-dev libfreetype6-dev python3-dev ;;
        dnf)    sudo dnf install -y SDL2-devel freetype-devel python3-devel ;;
        rpm-ostree)
                sudo rpm-ostree install -y SDL2-devel freetype-devel python3-devel
                warn "rpm-ostree changes may require a reboot to take effect."
                warn "If NOVA fails to start, please reboot and try again." ;;
        brew)   brew install sdl2 freetype ;;
        *)      warn "Could not auto-install build deps. Install them manually:"
                warn "  Fedora Atomic:  sudo rpm-ostree install SDL2-devel freetype-devel python3-devel"
                warn "  Fedora/RHEL:    sudo dnf install SDL2-devel freetype-devel python3-devel"
                warn "  Debian/Ubuntu:  sudo apt-get install libsdl2-dev libfreetype6-dev python3-dev"
                warn "  Arch:           sudo pacman -S sdl2 freetype2 python" ;;
    esac
}

ensure_build_deps

# ── Bootstrap: create portable layout + install NOVA on first run ─────────────

if [ ! -d "$VENV_DIR" ]; then
    info "First run — setting up NOVA in $PORTABLE_ROOT ..."
    mkdir -p "$PORTABLE_ROOT/config" "$PORTABLE_ROOT/data" "$PORTABLE_ROOT/logs"
    info "Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    info "Installing NOVA (this takes a minute)..."
    "$VENV_PIP" install --quiet --upgrade pip
    "$VENV_PIP" install "$NOVA_URL"
    success "NOVA installed successfully!"
    echo ""
else
    # ── Auto-update NOVA package ──────────────────────────────────────────────
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
        "$VENV_PIP" install --quiet --upgrade "$NOVA_URL"
        success "NOVA updated to $latest_ver."
        echo ""
    else
        success "NOVA $installed_ver is up to date."
        echo ""
    fi
fi

# ── Launch NOVA ───────────────────────────────────────────────────────────────

info "Starting NOVA..."
echo ""

# Pop any KKP stack entries the parent shell (fish 4.x) may have left active.
# Fish pushes flags=31 while reading input; if it doesn't pop before exec'ing
# this script, Kitty keeps sending KKP-formatted sequences until Textual's own
# push takes effect.  Eight pops clear all realistic stack depths; extras are
# no-ops on an empty stack.
printf '\033[<u\033[<u\033[<u\033[<u\033[<u\033[<u\033[<u\033[<u'

export NOVA_PORTABLE_ROOT="$PORTABLE_ROOT"
exec "$VENV_NOVA"
