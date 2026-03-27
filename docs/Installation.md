# Installation, Update & Uninstall

## First Installation

### Linux

```bash
curl -O https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh
chmod +x nova.sh
./nova.sh
```

The script automatically:
- Installs Python if missing
- Creates an isolated virtual environment at `~/.local/share/nova/venv/`
- Installs NOVA and all dependencies
- Installs a `nova` command to `~/.local/bin/nova`
- Launches NOVA

> Make sure `~/.local/bin` is in your PATH. Add this to your `~/.bashrc` or `~/.zshrc` if needed:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```

### Windows

1. Download [`install_windows.bat`](https://github.com/KernicDE/nova-ed-monitor/releases/latest/download/install_windows.bat) from the latest release
2. Double-click **`install_windows.bat`**

The installer downloads the launcher files to `%USERPROFILE%\nova\`, installs Python 3.12 (if missing), creates a virtual environment, installs NOVA, and launches it.

> **Always download from the Releases section** — downloading script files from the GitHub repository page gives you HTML, not the actual file.

### Alternative: Standalone Linux binary (no Python needed)

Download `nova-linux-x86_64` from the [latest release](https://github.com/KernicDE/nova-ed-monitor/releases/latest):

```bash
chmod +x nova-linux-x86_64
./nova-linux-x86_64
```

### Alternative: pip install

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

*NOVA running in offline mode. From left to right: System panel, Ship panel, Route panel (top row); Bodies panel, Situational panel, Event log / Chat log (middle row); Footer bar with volume indicator.*

---

## Updating NOVA

Updates happen **automatically** on every launch via the launcher scripts — no manual steps needed.

To force an immediate update, simply run the launcher:

```bash
# Linux
./nova.sh
# or
nova

# Windows — double-click nova.bat in %USERPROFILE%\nova\
```

---

## Uninstalling NOVA

### Linux

```bash
nova --uninstall
```

This removes:
- The virtual environment at `~/.local/share/nova/`
- The config directory at `~/.config/nova/`
- The `nova` command itself

After uninstalling, delete `nova.sh` manually if you no longer need it.

> Elite Dangerous journal files are **never touched**.

### Windows

```powershell
.\nova.ps1 -Uninstall
```

Or via the bat file:

```
nova.bat -Uninstall
```

This removes the virtual environment (`%LOCALAPPDATA%\nova\`) and config (`%USERPROFILE%\.config\nova\`). Prompts for confirmation.

After uninstalling, delete `nova.ps1` and `nova.bat` manually.

---

## Data Paths

| Path | Platform | Contents |
|------|----------|----------|
| `~/.config/nova/config.toml` | Linux | Configuration |
| `%USERPROFILE%\.config\nova\config.toml` | Windows | Configuration |
| `~/.local/share/nova/events.db` | Linux | SQLite event log, statistics & EDSM dump cache (~30–50 MB after first download) |
| `%LOCALAPPDATA%\nova\events.db` | Windows | SQLite event log, statistics & EDSM dump cache (~30–50 MB after first download) |
| `~/.local/share/nova/venv/` | Linux | Python virtual environment |
| `%LOCALAPPDATA%\nova\venv\` | Windows | Python virtual environment |

---

## Troubleshooting

**"No events are showing / journal not found"**
→ Set `journal_dir` manually in config.toml (see the [Settings Guide](Settings))

**"No TTS voice / audio"**
→ Make sure pygame works: on Arch try `yay -S python-pygame`; elsewhere `pip install --upgrade pygame` inside the NOVA venv

**"nova: command not found" (Linux)**
→ Run `./nova.sh` once — it installs the `nova` command to `~/.local/bin/`
→ Make sure `~/.local/bin` is in your PATH

**"Access denied" / execution policy error (Windows)**
→ Right-click `nova.bat` → "Run as administrator" once, or run in PowerShell:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
