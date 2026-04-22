# Installation, Update & Uninstall

## First Installation

NOVA is fully portable — the launcher script keeps everything (venv, config, database) in the same folder as the script. There is nothing installed system-wide.

### Linux

```bash
curl -O https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh
chmod +x nova.sh
./nova.sh
```

On first run the script:
- Installs Python if missing (via your package manager)
- Creates `venv/` next to the script and installs NOVA and all dependencies
- Creates `config/`, `data/`, and `logs/` subdirectories
- Launches NOVA

On every subsequent run it checks for a newer release and upgrades automatically before launching.

### Windows

1. Download [`nova.ps1`](https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.ps1) — right-click the link and **Save As** into a folder of your choice (e.g. `C:\Nova\`)
2. Right-click **`nova.ps1`** → **Run with PowerShell**

On first run the script installs Python 3.12 (if missing), creates a virtual environment, and installs NOVA — all inside the folder where `nova.ps1` lives. On every subsequent run it checks for a newer release and upgrades automatically before launching.

> If PowerShell blocks the script, open a PowerShell window and run:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> Then re-run `nova.ps1`.

### Alternative: pip install

For developers or users who prefer a system-level install (paths differ — see [Data Paths](#data-paths)):

```bash
# Linux (use a venv to avoid PEP 668 errors)
python -m venv ~/nova-venv
~/nova-venv/bin/pip install git+https://github.com/KernicDE/nova-ed-monitor.git
~/nova-venv/bin/nova

# Windows
py -m pip install git+https://github.com/KernicDE/nova-ed-monitor.git
nova
```

---

## Screenshot

![NOVA screenshot](nova-screenshot.png)

*NOVA running in offline mode. From left to right: Position panel, Ship panel, Route panel (top row); Bodies panel, Situational panel, Event log / Chat log (middle row); Footer bar with volume indicator.*

---

## Updating NOVA

Updates happen **automatically** on every launch via the launcher scripts — no manual steps needed.

To force an immediate update, simply run the launcher again:

```bash
# Linux
./nova.sh

# Windows — right-click nova.ps1 → Run with PowerShell
```

---

## Uninstalling NOVA

### Linux

```bash
./nova.sh --uninstall
```

Removes the entire NOVA folder (venv, config, database). Prompts for confirmation. Elite Dangerous journal files are **never touched**. Delete `nova.sh` afterwards to finish.

### Windows

```powershell
.\nova.ps1 -Uninstall
```

Removes the entire NOVA folder (venv, config, database). Prompts for confirmation. Elite Dangerous journal files are **never touched**. Delete `nova.ps1` afterwards to finish.

---

## Data Paths

### Portable mode (recommended — via launcher script)

All data lives next to `nova.sh` / `nova.ps1`:

| Subfolder | Contents |
|-----------|----------|
| `config/config.toml` | Configuration file |
| `config/voicelines/` | User voiceline override files |
| `config/voicelines/default/` | Built-in reference files (overwritten each launch) |
| `data/events.db` | SQLite event log, statistics, EDSM dump cache & neutron stars (~50–80 MB after first download) |
| `logs/nova-debug.log` | Debug log (when `debug_log = true` in config) |
| `venv/` | Python virtual environment |

Migrating from an older system install? On first portable launch NOVA automatically copies your existing `~/.config/nova/` and `events.db` into the portable layout (non-destructive — originals are never deleted).

### System install (via pip)

| Path | Platform | Contents |
|------|----------|----------|
| `~/.config/nova/config.toml` | Linux | Configuration |
| `%USERPROFILE%\.config\nova\config.toml` | Windows | Configuration |
| `~/.local/share/nova/events.db` | Linux | SQLite event log & EDSM cache |
| `%LOCALAPPDATA%\nova\events.db` | Windows | SQLite event log & EDSM cache |
| `~/.config/nova/bindings_backup/` | Linux | Keybindings backups (last 5 versions) |
| `%USERPROFILE%\.config\nova\bindings_backup\` | Windows | Keybindings backups |
| `~/.config/nova/nova-debug.log` | Linux | Debug log |
| `%USERPROFILE%\.config\nova\nova-debug.log` | Windows | Debug log |

---

## Troubleshooting

**"No events are showing / journal not found"**
→ Set `journal_dir` manually in config.toml (see the [Settings Guide](Settings.md))

**"No TTS voice / audio"**
→ Make sure pygame works: on Arch try `yay -S python-pygame`; elsewhere `pip install --upgrade pygame` inside the NOVA venv

**"Access denied" / execution policy error (Windows)**
→ In a PowerShell window run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
→ Then right-click `nova.ps1` → **Run with PowerShell**

**Something is not working / reporting a bug**
→ Add `debug_log = true` to `config.toml`, reproduce the issue, then attach `nova-debug.log` from the `logs/` folder (portable) or config directory (system install) with your report
