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

# ── Detect package manager ────────────────────────────────────────────────────
# Reads /etc/os-release (reliable on all modern Linux distros) before falling
# back to command presence — prevents false apt-get matches on RPM-based systems.

detect_pm() {
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        local _id _id_like
        _id=$(. /etc/os-release && echo "${ID:-}")
        _id_like=$(. /etc/os-release && echo "${ID_LIKE:-}")
        case "$_id $id_like" in
            *fedora*|*rhel*|*centos*|*rocky*|*alma*|*nobara*) echo "dnf"; return ;;
        esac
        case "$_id_like $id_like" in
            *fedora*|*rhel*|*centos*)                          echo "dnf"; return ;;
            *debian*|*ubuntu*)                                 echo "apt"; return ;;
            *arch*|*manjaro*)                                  echo "pacman"; return ;;
        esac
        case "$_id" in
            fedora|rhel|centos|rocky|almalinux|nobara)         echo "dnf"; return ;;
            debian|ubuntu|linuxmint|pop|elementary|kali)       echo "apt"; return ;;
            arch|manjaro|endeavouros|garuda|artix)             echo "pacman"; return ;;
        esac
    fi
    # Fallback: command presence (note: dnf checked before apt to avoid false matches)
    command -v pacman  &>/dev/null && echo "pacman" && return
    command -v dnf     &>/dev/null && echo "dnf"    && return
    command -v apt-get &>/dev/null && echo "apt"    && return
    command -v brew    &>/dev/null && echo "brew"   && return
    echo "unknown"
}

_PM=$(detect_pm)

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

    case "$_PM" in
        pacman) info "Detected Arch Linux / Manjaro — installing Python via pacman..."
                sudo pacman -S --noconfirm python ;;
        apt)    info "Detected Debian / Ubuntu / Mint — installing Python via apt..."
                sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv ;;
        dnf)    info "Detected Fedora / RHEL — installing Python via dnf..."
                sudo dnf install -y python3 ;;
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

# ── Set up virtual environment ────────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
    info "Creating NOVA virtual environment at $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
    success "Virtual environment created."
fi

# ── Ensure SDL2 build dependencies (needed if pygame must compile from source) ─

ensure_build_deps() {
    # Skip if sdl2-config is already present (pygame can build fine)
    command -v sdl2-config &>/dev/null 2>&1 && return 0
    pkg-config --exists sdl2 2>/dev/null && return 0

    warn "SDL2 development libraries not found — installing build dependencies..."
    case "$_PM" in
        pacman) sudo pacman -S --noconfirm --needed sdl2 freetype2 ;;
        apt)    sudo apt-get install -y libsdl2-dev libfreetype6-dev ;;
        dnf)    sudo dnf install -y SDL2-devel freetype-devel ;;
        brew)   brew install sdl2 freetype ;;
        *)      warn "Could not auto-install SDL2. Install SDL2 dev libraries manually:"
                warn "  Fedora/RHEL:    sudo dnf install SDL2-devel freetype-devel"
                warn "  Debian/Ubuntu:  sudo apt-get install libsdl2-dev libfreetype6-dev"
                warn "  Arch:           sudo pacman -S sdl2 freetype2" ;;
    esac
}

ensure_build_deps

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

# ── Install global 'nova' command (wrapper with auto-update) ──────────────────

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

_NOVA_WRAPPER="$BIN_DIR/nova"
_VENV_PY="$VENV_DIR/bin/python"

# Always (re)write the wrapper so it stays in sync with nova.sh variables.
cat > "$_NOVA_WRAPPER" <<WRAPPER
#!/usr/bin/env bash
# nova-ed-monitor-wrapper — auto-update launcher
NOVA_DATA_DIR="$VENV_DIR/.."
NOVA_CFG_DIR="\${XDG_CONFIG_HOME:-\$HOME/.config}/nova"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PY="$VENV_DIR/bin/python"
VENV_NOVA="$VENV_NOVA"
NOVA_PKG="$NOVA_PKG"
NOVA_URL="$NOVA_URL"
GH_API_URL="$GH_API_URL"

# ── Uninstall ─────────────────────────────────────────────────────────────────

if [ "\${1:-}" = "--uninstall" ]; then
    echo ""
    echo "  This will permanently remove:"
    echo "    \$(realpath \"\$NOVA_DATA_DIR\")   (venv + event log)"
    echo "    \$NOVA_CFG_DIR   (config)"
    echo "    \$0   (this command)"
    echo ""
    echo "  Elite Dangerous journal files will NOT be touched."
    echo ""
    printf "  Confirm uninstall? [y/N] "
    read -r _answer
    if [ "\$_answer" = "y" ] || [ "\$_answer" = "Y" ]; then
        rm -rf "\$(realpath \"\$NOVA_DATA_DIR\")"
        rm -rf "\$NOVA_CFG_DIR"
        rm -f "\$0"
        echo "  NOVA uninstalled."
    else
        echo "  Cancelled."
    fi
    exit 0
fi

# ── Auto-update ───────────────────────────────────────────────────────────────

if command -v curl &>/dev/null; then
    installed_ver=\$("\$VENV_PIP" show "\$NOVA_PKG" 2>/dev/null | awk '/^Version:/{print \$2}')
    latest_ver=\$(curl -fsSL --max-time 5 "\$GH_API_URL" 2>/dev/null \
        | "\$VENV_PY" -c "import sys,json; print(json.load(sys.stdin).get('tag_name','').lstrip('v'))" \
        2>/dev/null || true)
    if [ -n "\$latest_ver" ] && [ -n "\$installed_ver" ] && [ "\$installed_ver" != "\$latest_ver" ]; then
        echo "  NOVA update: \$installed_ver → \$latest_ver — updating..."
        "\$VENV_PIP" install --quiet --upgrade "\$NOVA_URL"
        echo "  Updated. Starting NOVA..."
        echo ""
    fi
fi

exec "\$VENV_NOVA"
WRAPPER
chmod +x "$_NOVA_WRAPPER"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        warn "Note: $BIN_DIR is not in your PATH."
        warn "Add this to ~/.bashrc or ~/.zshrc:"
        warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
        ;;
esac

# ── Create .desktop launcher ──────────────────────────────────────────────────

DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/nova-ed-monitor.desktop"
mkdir -p "$DESKTOP_DIR"

if [ ! -f "$DESKTOP_FILE" ]; then
    cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Name=NOVA
GenericName=Elite Dangerous Monitor
Comment=Navigation, Operations, and Vessel Assistance
Exec=$_NOVA_WRAPPER
Terminal=true
Type=Application
Categories=Game;Utility;
DESKTOP
    success "Desktop launcher created — search for NOVA in your app menu."
fi

# ── Launch NOVA ───────────────────────────────────────────────────────────────

info "Starting NOVA..."
echo ""

exec "$VENV_NOVA"
