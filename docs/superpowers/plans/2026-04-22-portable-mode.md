# Portable Mode Implementation Plan (Issue #102)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NOVA fully portable — all data, config, venv, and scripts live inside a single `NOVA/` directory that can be moved or placed on a USB stick. The launcher scripts are the only entry point; no global `~` directories are created in portable mode.

**Architecture:** The launcher (`nova.sh` / `nova.ps1`) sets `NOVA_PORTABLE_ROOT` to its own directory and execs the venv's `nova` binary. Python reads that env var to redirect all paths from `~/.config/nova` / `~/.local/share/nova` into `NOVA/config/` and `NOVA/data/`. Migration from old system-wide paths runs automatically on first portable launch.

**Tech Stack:** Bash (nova.sh), PowerShell (nova.ps1), Python 3.11+ (config.py, voicelines.py, __main__.py)

---

## Portable Directory Layout

```
NOVA/                              ← NOVA_PORTABLE_ROOT (= script's own directory)
├── nova.sh                        ← Linux/macOS launcher (bootstraps and runs)
├── nova.bat                       ← Windows double-click launcher (calls nova.ps1)
├── nova.ps1                       ← Windows launcher
├── venv/                          ← Python virtual environment
├── config/                        ← replaces ~/.config/nova/
│   ├── config.toml
│   ├── config.toml.example
│   ├── voicelines/
│   │   └── {lang}.toml           ← user voice overrides
│   └── bindings_backup/
│       └── *.binds
├── data/                          ← replaces ~/.local/share/nova/
│   └── events.db
└── logs/                          ← replaces config/ for debug log
    └── nova-debug.log
```

> **Note:** `overlay/` directory is user-configured via `overlay_dir` in `config.toml`. Defaults to `config/overlay/` in portable mode (set by launcher via env var or default path logic).

---

## File Map

| File | Action | Why |
|---|---|---|
| `nova.sh` | Rewrite | Portable bootstrap + drop global install |
| `nova.ps1` | Rewrite | Same for Windows |
| `nova.bat` | No change | Already just delegates to nova.ps1 |
| `ed_monitor/config.py` | Modify | `config_dir()` + new `data_dir()` + `logs_dir()` |
| `ed_monitor/voicelines.py` | Modify | Replace private `_config_dir()` with import from config |
| `ed_monitor/__main__.py` | Modify | Use `config.data_dir()` + `config.logs_dir()` |
| `install_windows.bat` | Delete | Obsolete — nova.bat/nova.ps1 replaces it |

---

## Task 1: Add path resolution functions to `config.py`

**Files:**
- Modify: `ed_monitor/config.py`
- Test: `tests/test_portable_paths.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_portable_paths.py
"""Tests for portable-mode path resolution in config.py."""
from __future__ import annotations
import os
import pytest
from pathlib import Path
from ed_monitor import config


def test_config_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    # Should fall back to ~/.config/nova
    result = config.config_dir()
    assert result == Path.home() / ".config" / "nova"


def test_config_dir_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    result = config.config_dir()
    assert result == tmp_path / "config"


def test_data_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    result = config.data_dir()
    assert result == Path.home() / ".local" / "share" / "nova"


def test_data_dir_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    result = config.data_dir()
    assert result == tmp_path / "data"


def test_logs_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    result = config.logs_dir()
    assert result == Path.home() / ".config" / "nova"  # same as config_dir in non-portable


def test_logs_dir_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    result = config.logs_dir()
    assert result == tmp_path / "logs"
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_portable_paths.py -v
```
Expected: FAIL — `data_dir` and `logs_dir` not defined, `config_dir` doesn't check `NOVA_PORTABLE_ROOT`.

- [ ] **Step 3: Implement the three functions in `config.py`**

Update `config_dir()` and add `data_dir()` + `logs_dir()`. The `NOVA_PORTABLE_ROOT` check is the same pattern in all three:

```python
def config_dir() -> Path:
    """Return the NOVA config directory.

    Portable mode (NOVA_PORTABLE_ROOT set): <root>/config/
    Standard mode:  $XDG_CONFIG_HOME/nova  or  ~/.config/nova
    """
    root = os.environ.get("NOVA_PORTABLE_ROOT")
    if root:
        return Path(root) / "config"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".config" / "nova"


def data_dir() -> Path:
    """Return the NOVA data directory (SQLite db, cache).

    Portable mode: <root>/data/
    Standard mode: $XDG_DATA_HOME/nova  or  ~/.local/share/nova
    """
    root = os.environ.get("NOVA_PORTABLE_ROOT")
    if root:
        return Path(root) / "data"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".local" / "share" / "nova"


def logs_dir() -> Path:
    """Return the directory for nova-debug.log.

    Portable mode: <root>/logs/
    Standard mode: same as config_dir() (backwards-compatible)
    """
    root = os.environ.get("NOVA_PORTABLE_ROOT")
    if root:
        return Path(root) / "logs"
    return config_dir()
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/test_portable_paths.py -v
```
Expected: 6 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/config.py tests/test_portable_paths.py
git commit -m "feat: add config.data_dir() and config.logs_dir() for portable path resolution"
```

---

## Task 2: Fix `voicelines.py` to use `config.config_dir()`

**Files:**
- Modify: `ed_monitor/voicelines.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_portable_paths.py

def test_voicelines_uses_portable_config_dir(tmp_path, monkeypatch):
    """voicelines._config_dir() must respect NOVA_PORTABLE_ROOT."""
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    import importlib
    import ed_monitor.voicelines as vl
    importlib.reload(vl)  # reload so the env var is picked up
    assert vl._config_dir() == tmp_path / "config"
```

- [ ] **Step 2: Run to verify it fails**

```bash
python3.12 -m pytest tests/test_portable_paths.py::test_voicelines_uses_portable_config_dir -v
```
Expected: FAIL — `vl._config_dir()` returns `~/.config/nova`, ignores `NOVA_PORTABLE_ROOT`.

- [ ] **Step 3: Replace `_config_dir()` in `voicelines.py`**

Remove the private implementation and import from config:

Old (lines ~39-45):
```python
def _config_dir() -> Path:
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR
    import os
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".config" / "nova"
```

New:
```python
def _config_dir() -> Path:
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR
    from .config import config_dir
    return config_dir()
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/voicelines.py
git commit -m "fix: voicelines._config_dir() delegates to config.config_dir() (respects NOVA_PORTABLE_ROOT)"
```

---

## Task 3: Update `__main__.py` to use portable paths

**Files:**
- Modify: `ed_monitor/__main__.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_portable_paths.py

def test_db_path_uses_data_dir(tmp_path, monkeypatch):
    """_db_path() must use config.data_dir() so portable root is respected."""
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    import importlib
    import ed_monitor.__main__ as main
    importlib.reload(main)
    assert main._db_path() == tmp_path / "data" / "events.db"
```

- [ ] **Step 2: Run to verify it fails**

```bash
python3.12 -m pytest tests/test_portable_paths.py::test_db_path_uses_data_dir -v
```
Expected: FAIL — `_db_path()` returns `~/.local/share/nova/events.db`.

- [ ] **Step 3: Update `_db_path()` in `__main__.py`**

```python
def _db_path() -> Path:
    p = config.data_dir() / "events.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
```

Also update the `debug_log.setup()` call (line ~68) to use `config.logs_dir()`:

```python
debug_log.setup(cfg.debug_log, config.logs_dir())
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/__main__.py
git commit -m "fix: _db_path() uses config.data_dir(); debug log uses config.logs_dir()"
```

---

## Task 4: Add migration from old system paths on first portable run

When NOVA is launched in portable mode for the first time, copy existing data from the old system locations so the user doesn't lose their event log and config.

**Files:**
- Modify: `ed_monitor/config.py`
- Modify: `ed_monitor/__main__.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_portable_paths.py
import shutil

def test_migrate_config_on_first_portable_run(tmp_path, monkeypatch):
    """If portable config doesn't exist but old config does, copy it over."""
    old_cfg = tmp_path / "old_config"
    old_cfg.mkdir()
    (old_cfg / "config.toml").write_text("tts_lang = de\n")

    portable_root = tmp_path / "NOVA"
    portable_root.mkdir()

    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))
    from ed_monitor.config import migrate_from_system_paths
    migrate_from_system_paths(
        old_config_dir=old_cfg,
        old_data_dir=tmp_path / "nonexistent_data",
    )
    assert (portable_root / "config" / "config.toml").read_text() == "tts_lang = de\n"


def test_migrate_db_on_first_portable_run(tmp_path, monkeypatch):
    """If portable events.db doesn't exist but old one does, copy it over."""
    old_data = tmp_path / "old_data"
    old_data.mkdir()
    (old_data / "events.db").write_bytes(b"SQLite")

    portable_root = tmp_path / "NOVA"
    portable_root.mkdir()

    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))
    from ed_monitor.config import migrate_from_system_paths
    migrate_from_system_paths(
        old_config_dir=tmp_path / "nonexistent_config",
        old_data_dir=old_data,
    )
    assert (portable_root / "data" / "events.db").read_bytes() == b"SQLite"


def test_migrate_does_not_overwrite_existing(tmp_path, monkeypatch):
    """Migration must not overwrite files that already exist in portable dir."""
    old_cfg = tmp_path / "old_config"
    old_cfg.mkdir()
    (old_cfg / "config.toml").write_text("old content\n")

    portable_root = tmp_path / "NOVA"
    (portable_root / "config").mkdir(parents=True)
    (portable_root / "config" / "config.toml").write_text("new content\n")

    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))
    from ed_monitor.config import migrate_from_system_paths
    migrate_from_system_paths(old_config_dir=old_cfg, old_data_dir=tmp_path / "x")
    assert (portable_root / "config" / "config.toml").read_text() == "new content\n"
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_portable_paths.py -k migrate -v
```
Expected: FAIL — `migrate_from_system_paths` not defined.

- [ ] **Step 3: Add `migrate_from_system_paths()` to `config.py`**

```python
def migrate_from_system_paths(
    old_config_dir: Path | None = None,
    old_data_dir: Path | None = None,
) -> None:
    """Copy existing system-wide config/data into the portable layout.

    Only runs when NOVA_PORTABLE_ROOT is set. Never overwrites existing files.
    Silently skips if old paths don't exist or portable dir already has data.
    """
    import shutil

    if not os.environ.get("NOVA_PORTABLE_ROOT"):
        return

    # Config: copy whole directory tree if portable config dir is empty
    if old_config_dir is None:
        old_config_dir = _old_system_config_dir()
    dst_cfg = config_dir()
    if old_config_dir.exists() and not dst_cfg.exists():
        shutil.copytree(old_config_dir, dst_cfg)

    # DB: copy single file if portable data dir has no db yet
    if old_data_dir is None:
        old_data_dir = _old_system_data_dir()
    dst_db = data_dir() / "events.db"
    old_db = old_data_dir / "events.db"
    if old_db.exists() and not dst_db.exists():
        dst_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_db, dst_db)


def _old_system_config_dir() -> Path:
    """The standard (non-portable) config dir — used for migration source."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".config" / "nova"


def _old_system_data_dir() -> Path:
    """The standard (non-portable) data dir — used for migration source."""
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".local" / "share" / "nova"
```

- [ ] **Step 4: Call migration at startup in `__main__.py`**

Add after the config is loaded (before db init):
```python
# Migrate existing system-wide data into portable layout (no-op if not portable
# or if destination files already exist)
config.migrate_from_system_paths()
```

- [ ] **Step 5: Run tests**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/config.py ed_monitor/__main__.py tests/test_portable_paths.py
git commit -m "feat: auto-migrate system config/db into portable layout on first portable run"
```

---

## Task 5: Rewrite `nova.sh` for portable-first bootstrap

**Files:**
- Rewrite: `nova.sh`

No new tests for shell scripts — manual validation required (see testing notes).

- [ ] **Step 1: Write the new `nova.sh`**

Key logic:
1. `SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"` — absolute dir of the script itself
2. `VENV_DIR="$SCRIPT_DIR/venv"` — venv lives next to the script
3. If `$VENV_DIR` doesn't exist → first-run bootstrap (Python check, venv create, pip install)
4. After bootstrap, set `NOVA_PORTABLE_ROOT="$SCRIPT_DIR"` and exec nova binary
5. Auto-update: compare installed vs. latest GitHub version, pip upgrade if needed
6. Self-update: download latest nova.sh and replace self if hash differs (then re-exec)
7. Remove: global `~/.local/bin/nova` wrapper creation; `.desktop` file creation
8. `--uninstall` flag: remove `$SCRIPT_DIR` entirely (the whole NOVA folder), with confirmation

```bash
#!/usr/bin/env bash
# NOVA — Navigation, Operations, and Vessel Assistance
# Portable launcher — all data lives next to this script.
# Usage: ./nova.sh [--update] [--uninstall]

set -euo pipefail

NOVA_URL="git+https://github.com/KernicDE/nova-ed-monitor.git"
NOVA_PKG="nova-ed-monitor"
SCRIPT_URL="https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh"
GH_API_URL="https://api.github.com/repos/KernicDE/nova-ed-monitor/releases/latest"

# Portable root = directory containing this script
SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_NOVA="$VENV_DIR/bin/nova"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}  ${*}${NC}"; }
success() { echo -e "${GREEN}  ${*}${NC}"; }
warn()    { echo -e "${YELLOW}  ${*}${NC}"; }
error()   { echo -e "${RED}  ${*}${NC}"; }

# ... (banner, detect_pm, find_python — same as current nova.sh) ...

SELF_UPDATE=1
for arg in "$@"; do
    case "$arg" in --no-self-update) SELF_UPDATE=0 ;; esac
done

# -- Uninstall ------------------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
    echo ""
    warn "This will permanently remove the entire NOVA directory:"
    warn "  $SCRIPT_DIR"
    echo ""
    printf "  Confirm? [y/N] "
    read -r _answer
    if [ "$_answer" = "y" ] || [ "$_answer" = "Y" ]; then
        rm -rf "$SCRIPT_DIR"
        success "NOVA removed."
    else
        echo "  Cancelled."
    fi
    exit 0
fi

# -- Self-update ----------------------------------------------------------------
SCRIPT_SELF="$(realpath "$0")"
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
            exec "$SCRIPT_SELF" --no-self-update "$@"
        fi
    fi
    rm -f "$tmp" 2>/dev/null || true
fi

# -- Python --------------------------------------------------------------------
# ... find_python, install if missing (same as current) ...
PYTHON=$(find_python) || { error "Python 3.11+ required."; exit 1; }
success "Python: $($PYTHON --version)"

# -- Bootstrap: create venv + install NOVA on first run ------------------------
if [ ! -d "$VENV_DIR" ]; then
    info "First run — setting up NOVA in $SCRIPT_DIR ..."
    mkdir -p "$SCRIPT_DIR/config" "$SCRIPT_DIR/data" "$SCRIPT_DIR/logs"
    $PYTHON -m venv "$VENV_DIR"
    info "Installing NOVA..."
    "$VENV_PIP" install --quiet --upgrade pip
    "$VENV_PIP" install "$NOVA_URL"
    success "NOVA installed."
fi

# -- Auto-update NOVA package --------------------------------------------------
installed_ver=$("$VENV_PIP" show "$NOVA_PKG" 2>/dev/null | awk '/^Version:/{print $2}')
if command -v curl &>/dev/null; then
    latest_ver=$(curl -fsSL --max-time 8 "$GH_API_URL" 2>/dev/null \
        | "$VENV_DIR/bin/python" -c "
import sys, json
try: print(json.load(sys.stdin).get('tag_name','').lstrip('v'))
except: pass
" 2>/dev/null || true)
    if [ -n "$latest_ver" ] && [ "$installed_ver" != "$latest_ver" ]; then
        info "Update: $installed_ver → $latest_ver"
        "$VENV_PIP" install --quiet --upgrade "$NOVA_URL"
        success "NOVA updated to $latest_ver."
    else
        success "NOVA $installed_ver is up to date."
    fi
fi

# -- Launch --------------------------------------------------------------------
info "Starting NOVA..."
export NOVA_PORTABLE_ROOT="$SCRIPT_DIR"
exec "$VENV_NOVA"
```

- [ ] **Step 2: Make executable and verify syntax**

```bash
bash -n nova.sh
chmod +x nova.sh
```
Expected: no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add nova.sh
git commit -m "feat: nova.sh portable-first bootstrap — venv and data live next to the script"
```

---

## Task 6: Rewrite `nova.ps1` for portable-first bootstrap (Windows)

**Files:**
- Rewrite: `nova.ps1`

- [ ] **Step 1: Write the new `nova.ps1`**

Key differences from current:
- `$PortableRoot = $PSScriptRoot` — PowerShell always has the script directory available
- `$VenvDir = Join-Path $PortableRoot "venv"`
- Bootstrap on first run: create subfolders, venv, install NOVA
- Set `$env:NOVA_PORTABLE_ROOT = $PortableRoot` before running
- Remove global `%LOCALAPPDATA%\nova\` usage
- `--Uninstall`: remove `$PortableRoot` entirely (with confirmation)

```powershell
#Requires -Version 5.1
param(
    [switch]$NoSelfUpdate,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$NOVA_URL     = "git+https://github.com/KernicDE/nova-ed-monitor.git"
$NOVA_PKG     = "nova-ed-monitor"
$SCRIPT_URL   = "https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.ps1"
$GH_API_URL   = "https://api.github.com/repos/KernicDE/nova-ed-monitor/releases/latest"

$PortableRoot = $PSScriptRoot
$VenvDir      = Join-Path $PortableRoot "venv"
$VenvPip      = Join-Path $VenvDir "Scripts\pip.exe"
$VenvNova     = Join-Path $VenvDir "Scripts\nova.exe"

# ... (Write-Info/Success/Warn/Err helpers, banner — same style as current) ...

# -- Uninstall ------------------------------------------------------------------
if ($Uninstall) {
    Write-Warn "This will permanently remove the entire NOVA directory:"
    Write-Warn "  $PortableRoot"
    $answer = Read-Host "Confirm? [y/N]"
    if ($answer -eq "y" -or $answer -eq "Y") {
        Remove-Item $PortableRoot -Recurse -Force
        Write-Success "NOVA removed."
    } else {
        Write-Host "Cancelled."
    }
    exit 0
}

# -- Self-update (PowerShell) --------------------------------------------------
$ScriptPath = $MyInvocation.MyCommand.Path
if (-not $NoSelfUpdate) {
    try {
        $tmp = [System.IO.Path]::GetTempFileName() + ".ps1"
        Invoke-WebRequest -Uri $SCRIPT_URL -OutFile $tmp -TimeoutSec 8 -ErrorAction SilentlyContinue
        $oldHash = (Get-FileHash $ScriptPath -Algorithm SHA256).Hash
        $newHash = (Get-FileHash $tmp        -Algorithm SHA256).Hash
        if ($oldHash -ne $newHash) {
            Write-Info "Script update found — applying..."
            Copy-Item $tmp $ScriptPath -Force
            Write-Success "Script updated. Restarting..."
            & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath -NoSelfUpdate @args
            exit 0
        }
    } catch { }
}

# -- Find Python ---------------------------------------------------------------
# ... (same logic as current nova.ps1 — find python 3.11+, install if missing) ...

# -- Bootstrap on first run ----------------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Write-Info "First run — setting up NOVA in $PortableRoot ..."
    @("config","data","logs") | ForEach-Object { New-Item -ItemType Directory -Path (Join-Path $PortableRoot $_) -Force | Out-Null }
    & $PythonExe -m venv $VenvDir
    Write-Info "Installing NOVA..."
    & $VenvPip install --quiet --upgrade pip
    & $VenvPip install $NOVA_URL
    Write-Success "NOVA installed."
}

# -- Auto-update ---------------------------------------------------------------
$installedVer = (& $VenvPip show $NOVA_PKG 2>$null | Select-String "^Version:") -replace "Version: ",""
try {
    $response = Invoke-RestMethod -Uri $GH_API_URL -TimeoutSec 8 -ErrorAction SilentlyContinue
    $latestVer = $response.tag_name.TrimStart("v")
    if ($latestVer -and $installedVer -ne $latestVer) {
        Write-Info "Update: $installedVer → $latestVer"
        & $VenvPip install --quiet --upgrade $NOVA_URL
        Write-Success "NOVA updated to $latestVer."
    } else {
        Write-Success "NOVA $installedVer is up to date."
    }
} catch { }

# -- Launch --------------------------------------------------------------------
Write-Info "Starting NOVA..."
$env:NOVA_PORTABLE_ROOT = $PortableRoot
& $VenvNova
```

- [ ] **Step 2: Verify PowerShell syntax**

```powershell
# On Windows or via PowerShell:
$null = [System.Management.Automation.Language.Parser]::ParseFile("nova.ps1", [ref]$null, [ref]$null)
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add nova.ps1
git commit -m "feat: nova.ps1 portable-first bootstrap — venv and data live next to the script"
```

---

## Task 7: Remove obsolete `install_windows.bat`

**Files:**
- Delete: `install_windows.bat`

- [ ] **Step 1: Delete the file**

```bash
git rm install_windows.bat
```

- [ ] **Step 2: Verify**

```bash
ls install_windows.bat 2>/dev/null && echo "STILL EXISTS" || echo "Removed"
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove install_windows.bat — superseded by nova.bat/nova.ps1 portable setup"
```

---

## Task 8: Bump version and release

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version**

Change `version = "1.33.8"` → `version = "1.34.0"` (minor bump, user-visible behaviour change).

- [ ] **Step 2: Run full test suite**

```bash
python3.12 -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 3: Commit and tag**

```bash
git add pyproject.toml
git commit -m "chore: bump to v1.34.0 — portable mode"
git tag v1.34.0
git push origin main --tags
```

- [ ] **Step 4: Create GitHub release**

Release title: `v1.34.0`
Release notes body (see below):

```
## Changelog

### Changed — Portable Mode (Issue #102)
- **NOVA is now fully portable.** All data, config, and the Python venv live
  in the same directory as `nova.sh` / `nova.bat`. Move the `NOVA/` folder to
  a USB stick, another machine, or a cloud-synced directory and everything comes with it.
- `nova.sh` and `nova.ps1` set up the portable layout automatically on first run —
  no separate installer needed.
- **Removed** global `~/.local/bin/nova` system wrapper and `.desktop` file creation.
- **Migration**: on first portable run, existing `~/.config/nova/` config and
  `~/.local/share/nova/events.db` are copied into the portable layout automatically.
  The originals are not deleted.
- `--uninstall` now removes the entire `NOVA/` directory.
```

---

## Testing Notes (Manual Verification)

Since launcher scripts can't be unit-tested in CI, verify these manually:

### Linux/macOS (`nova.sh`)
1. **Fresh install**: place `nova.sh` in an empty dir, run it. Verify `venv/`, `config/`, `data/`, `logs/` created next to the script. NOVA launches.
2. **Subsequent run**: run again. Verify update check runs, NOVA launches without reinstalling.
3. **Migration**: place `nova.sh` alongside an existing `~/.config/nova/config.toml`. On first run, verify `config/config.toml` appears next to the script.
4. **Portability**: move the entire directory to a different path. Run nova.sh again. NOVA launches with correct paths (check that debug log writes to `logs/` not `~/.config/nova/`).
5. **Uninstall**: run `./nova.sh --uninstall`. Confirm directory is removed.

### Windows (`nova.bat` / `nova.ps1`)
1. **Fresh install**: same as Linux test 1 above.
2. **Subsequent run**: same as Linux test 2.
3. **Portability**: move folder, rerun.
4. **Uninstall**: run with `-Uninstall` flag.
