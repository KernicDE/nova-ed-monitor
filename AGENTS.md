# AGENTS.md — NOVA Developer Reference

> This file is for AI coding agents. Read it first before modifying anything in this repository.

---

## 1. Project Overview

**NOVA** (Navigation, Operations, and Vessel Assistance) is a real-time TUI companion for the game *Elite Dangerous*. It tails the game's JSON journal and `Status.json`, speaks events via TTS, and renders a cockpit-style dashboard in the terminal.

- **Language:** Python 3.11+
- **UI Framework:** Textual (`textual>=0.80.0`)
- **TTS Engine:** `edge-tts` (Microsoft Edge online voices)
- **Audio Playback:** Platform-aware fallback chain ending in `pygame`
- **Database:** SQLite (WAL mode) for events, bodies, bio scans, stats, and offline EDSM dumps
- **License:** MIT
- **Repository:** https://github.com/KernicDE/nova-ed-monitor

---

## 2. Build, Run, and Test Commands

### Run locally (development)
```bash
python -m ed_monitor
```

### Install in editable mode
```bash
pip install -e ".[dev]"
```

### Run tests
```bash
pytest
# or verbose
pytest -v
```

### Build distribution
```bash
python -m build
```

### Build Linux standalone binary
```bash
pip install pyinstaller
printf 'from ed_monitor.__main__ import main\nmain()\n' > _nova_entry.py
pyinstaller --onefile --name nova --collect-all textual --collect-all edge_tts --hidden-import pygame --hidden-import httpx _nova_entry.py
```

---

## 3. Technology Stack

| Dependency | Purpose |
|-----------|---------|
| `textual>=0.80.0` | Terminal UI framework |
| `httpx>=0.27.0` | HTTP client for EDSM, Spansh, Twitch, YouTube |
| `edge-tts>=7.0.0` | Text-to-speech generation |
| `pygame>=2.5.0` | Audio playback fallback |
| `Pillow>=10.0` | Screenshot BMP→PNG conversion |
| `watchdog>=3.0` | File-system watcher for config/voiceline hot-reload |
| `pytest>=8.0` | Test runner (dev extra) |

No heavy web frameworks, no ORM, no async/await event loop. Everything is synchronous threading.

---

## 4. Project Structure

```
nova-ed-monitor/
├── ed_monitor/              # Main package (~11,700 LOC)
│   ├── __main__.py          # Entry point: spawns all daemon threads + Textual app
│   ├── state.py             # AppState, BodyInfo, BioScan, value formulas
│   ├── events.py            # Giant event dispatcher (~3,200 LOC)
│   ├── journal.py           # Journal file tailing + backlog processing
│   ├── status.py            # Status.json / Cargo.json / Materials.json monitor
│   ├── db.py                # SQLite wrapper + migrations
│   ├── config.py            # TOML config loader, path detection, portable mode
│   ├── config_watcher.py    # Hot-reload watcher for config.toml & voicelines
│   ├── tts.py               # TTS worker: edge-tts → cache → playback
│   ├── voicelines.py        # Random-variant picker with template engine
│   ├── ui/
│   │   ├── app.py           # NOVAApp (Textual App)
│   │   ├── panels.py        # All widgets (~4,600 LOC)
│   │   ├── settings_screen.py
│   │   └── palette.py       # HUD color constants
│   ├── edsm.py              # EDSM live API worker
│   ├── edsm_dumps.py        # Nightly EDSM dump downloader/importer
│   ├── spansh.py            # Spansh fleet-carrier lookup
│   ├── neutron.py           # Spansh neutron-route planner
│   ├── twitch.py            # Anonymous Twitch IRC chat monitor
│   ├── youtube.py           # YouTube live-chat scraper
│   ├── overlay.py           # OBS/Streamlabs .txt overlay files
│   ├── screenshots.py       # Screenshot rename + BMP→PNG
│   ├── bindings.py          # .binds file backup watcher
│   ├── _http.py             # Shared HTTP constants
│   ├── debug_log.py         # Optional nova-debug.log
│   └── voicelines/          # Built-in default TOML files (en, de, fr, es, it, pt, ru)
├── tests/                   # pytest suite (~240 tests)
├── docs/                    # User documentation (Markdown)
├── pyproject.toml           # Package metadata, setuptools backend
├── nova.sh / nova.ps1       # Portable launchers (auto-install venv + update)
└── .github/workflows/
    └── release.yml          # Tag-triggered release (wheel, sdist, PyInstaller binary)
```

---

## 5. Architecture & Concurrency

### Pattern: Threaded Producer-Consumer with Centralized State

- **`AppState`** (`state.py`) is a large mutable dataclass (~450 fields) protected by a single `threading.RLock`.
- **Producer threads** (all daemonized):
  - `journal.py` — tails `Journal.*.log`
  - `status.py` — polls `Status.json`, `Cargo.json`, `Materials.json`
  - `edsm.py` / `edsm_dumps.py` — fetches EDSM data
  - `spansh.py` — fleet-carrier lookups
  - `neutron.py` — route planning
  - `twitch.py` / `youtube.py` — chat monitors
  - `overlay.py` — writes overlay `.txt` files
  - `screenshots.py` — watches screenshot folder
  - `tts.py` — consumes TTS queue
- **Consumer:** `ui/app.py` (`NOVAApp`) snapshots `AppState` every 0.5 s and renders panels.

### Critical Rules
1. **Threads never call Textual APIs directly.** They mutate `AppState` under the `RLock`; the UI thread reads a snapshot and renders.
2. **Thread watchdog** (`__main__._spawn_guarded`): every daemon thread restarts after a 5 s backoff on uncaught exception.
3. **Fingerprint early-out:** the UI skips expensive copies when `AppState` hasn't meaningfully changed.
4. **Debounced DB writes:** body writes are batched and flushed on idle to avoid write storms during FSS honks.

### Queues
- `tts_q` (`queue.Queue[TtsMsg]`) — TTS requests
- `edsm_q`, `spansh_q`, `neutron_q` — external-service requests

---

## 6. Code Style Guidelines

- **Formatter:** None enforced. The codebase is hand-formatted.
- **Indentation:** 4 spaces.
- **Line length:** ~100–120 characters (soft limit).
- **Imports:** `from __future__ import annotations` at the top of every file. Group: stdlib → third-party → local.
- **Typing:** Uses `from __future__ import annotations` and modern syntax (`list[str]`, `str | None`). `Optional` is still present in older code but new code should prefer `X | None`.
- **Docstrings:** Minimal. Functions usually have a one-line docstring if non-obvious. Large functions have inline comments with `── Section ──` headers.
- **Naming:**
  - `snake_case` for functions, variables, modules
  - `PascalCase` for classes
  - `SCREAMING_SNAKE_CASE` for module-level constants
  - Private helpers prefixed with `_`
- **Logging:** One logger per module: `_log = logging.getLogger("nova.module_name")`.
- **Error handling:** Prefer `try/except Exception` with rollback in DB code. Thread workers must never raise unhandled exceptions (watchdog restarts them, but logs should explain why).

---

## 7. Testing Strategy

Test runner: **pytest** (`pytest>=8.0`).

| Test file | What it covers |
|-----------|----------------|
| `test_state.py` | Body index consistency, upserts, rebuilds |
| `test_events.py` | Event handler logic (FSDJump, Scan, SAAScanComplete, high-G timers, first-footfall) |
| `test_db.py` | SQLite round-trips, migrations, pruning, EDSM imports |
| `test_voicelines.py` | Mute/silence, user-file isolation |
| `test_voicelines_template.py` | Template includes, conditionals, fragment keys |
| `test_config_save.py` | Config serialization |
| `test_config_watcher.py` | Polling watcher logic |
| `test_http.py` | User-Agent string |
| `test_portable_paths.py` | Portable mode path resolution |
| `test_settings_screen.py` | Settings row cycling, voice catalog parsing |
| `test_spansh.py` | Spansh API response parsing |
| `test_status_distance.py` | Bio distance / bearing calculations |
| `test_syntax.py` | General syntax / import checks |
| `test_bio_prediction.py` | Biological species prediction logic |
| `test_body_value.py` | Exploration value formulas |

### Testing conventions
- Use `tmp_path` for filesystem isolation.
- Use `monkeypatch` for config / environment overrides.
- No integration tests against live APIs or the full Textual app.
- Run the full suite before any release-worthy change.

---

## 8. Configuration & Data Paths

### Portable mode
Set `NOVA_PORTABLE_ROOT` env var (launcher scripts do this automatically). All data lives under that root:
- Config: `<root>/config/config.toml`
- Data/DB: `<root>/data/events.db`
- Logs: `<root>/logs/`
- Voicelines: `<root>/config/voicelines/`

### System install
- Config: `~/.config/nova/config.toml` (or `XDG_CONFIG_HOME/nova`)
- Data: `~/.local/share/nova/`

### Key config keys (see `docs/Settings.md` for full reference)
- `journal_dir` — override auto-detected journal path
- `twitch_channel` / `youtube_channel` — enable chat monitors
- `tts_rate`, `tts_lang`, `tts_voice_<lang>` — TTS settings
- `overlay_dir` — stream overlay `.txt` output directory
- `default_volume` — 0–100
- `carrier_lookup` — enable Spansh fleet-carrier lookup
- `prune_events_days` — auto-delete old events at startup (0 = disabled)
- `situational_panels` — panel order string

### Hot-reload
`watchdog` monitors `config.toml` and `voicelines/*.toml`. Changes apply within ~2 s.

---

## 9. Release & Deployment

### GitHub Actions (`.github/workflows/release.yml`)
- **Trigger:** push tag `v*`
- **Steps:**
  1. Build sdist + wheel (`python -m build`)
  2. Build Linux standalone binary with PyInstaller (`--onefile --name nova`)
  3. Extract release notes from the annotated tag's message body
  4. Create GitHub release with assets: wheel, sdist, `nova-linux-x86_64`, launcher scripts

### Version bumping
- Edit `version` in `pyproject.toml`.
- Tag: `git tag -a vX.Y.Z -m "Release notes…"`
- Push tags: `git push origin vX.Y.Z`

### Launchers
- `nova.sh` (Bash) and `nova.ps1` (PowerShell) are **portable launchers**. They create a local `venv`, install/update NOVA from PyPI or git, and run it. All data stays next to the script.
- These scripts are included in every GitHub release.

---

## 10. Security Considerations

- **No secrets in repo.** There are no API keys, tokens, or passwords committed.
- **Twitch / YouTube** use anonymous scraping / IRC; no OAuth or API keys required.
- **EDSM** is read-only, GET-only, no API key.
- **File I/O:** The app reads the user's Elite Dangerous journal directory and writes to its own config/data directories. Path traversal is mitigated by using `pathlib` and restricting writes to known subdirectories.
- **TTS cache:** MP3 files are cached in `data_dir() / tts_cache` with an LRU limit (500 MB). Filenames are SHA-256 hashes of the text content — safe from path injection.
- **SQL injection:** The DB layer uses parameterized queries exclusively.
- **Input validation:** Journal events are parsed as JSON; missing keys are handled with safe defaults (`_s`, `_f`, `_b`, `_u` helpers in `events.py`).

---

## 11. UI Style Guide

### Design Philosophy
NOVA is a cockpit-style HUD. The visual language should feel like an extension of the Elite Dangerous in-game interface: dark, functional, and immediately readable at a glance. Bright neon colours are forbidden except for critical warnings.

### Colour Palette
All colours **must** be defined in `ed_monitor/ui/palette.py` and imported as `from . import palette as P`. No inline `rgb()` values in panel/app logic except for gameplay-specific scientific mappings (star classes, planet types, pip colours).

| Constant | Value | Semantic Use |
|----------|-------|--------------|
| `P.AMBER` | `rgb(210,115,0)` | Primary accent — ship status, target, actions |
| `P.HUD_CYAN` | `rgb(0,175,185)` | Info / exploration / position panels |
| `P.HUD_GREEN` | `rgb(0,170,60)` | Positive / success / scoopable / bio present |
| `P.HUD_WARN` | `rgb(195,150,0)` | Warning states |
| `P.HUD_CRIT` | `rgb(185,40,40)` | Critical / combat / error |
| `P.GOLD` | `rgb(230,185,0)` | First discovery / mapping / notable value |
| `P.PURPLE` | `rgb(140,100,165)` | On-foot mode / geo signals |
| `P.HEADER` | `rgb(195,160,55)` | Table headers, section titles, modal borders |
| `P.HEADER_BG` | `rgb(45,35,10)` | Background behind section headers |
| `P.ROW_ALT` | `rgb(38,38,38)` | Alternating table row background |
| `P.LABEL` | `rgb(145,145,145)` | Secondary text / labels |
| `P.LABEL_DIM` | `rgb(100,100,100)` | Timestamps / hints / tertiary text |
| `P.LABEL_LIGHT` | `rgb(160,160,160)` | Muted primary text / inactive buttons |
| `P.DIM` | `rgb(60,60,60)` | Disabled / faint / no-data |
| `P.WHITE` | `white` | Primary high-contrast text |
| `P.BG_DARK` | `rgb(18,18,18)` | App background |

### Border Colour Rules
Panel borders communicate function. Follow this hierarchy:
- **Cyan (`P.HUD_CYAN`)** = Information / position / exploration (`SystemPanel`, `BodiesPanel`)
- **Amber (`P.AMBER`)** = Ship status / target / actionable (`ShipPanel`, `RoutePanel`)
- **Neutral grey** = Secondary readouts / logs (`EventLogPanel`, `ChatLogPanel`, `SituationalPanel`)
- **Mode overlays** (applied at `Screen` level): Red = combat, Green = analysis, Purple = on-foot, Dark grey = offline

### Typography Hierarchy
1. **Headers** — `bold P.HEADER` (gold-brown, section titles and table headers)
2. **Labels** — `P.LABEL` (grey, field names)
3. **Values** — `P.WHITE` or semantic colour (data content)
4. **Dim / Hints** — `P.LABEL_DIM` or `P.DIM` (tertiary info, disabled states)

### Scrolling & Focus Rules
- **SituationalPanel** (center) scrolls with `↑` / `↓` (arrow keys or `k`/`j`)
- **All other panels** scroll with `PgUp` / `PgDn` **only when focused** (keys `1`–`6`)
- **Home / End** jump to top / bottom of the **focused** panel
- **No global scroll keys** — do not add single-key shortcuts like `w` for specific panels
- Focus is shown with a `heavy white` border and underlined title (`.focused` CSS class)

### Styling Mechanisms (pick one per layer)
| Layer | Mechanism | Example |
|-------|-----------|---------|
| Widget chrome (borders, height, width) | Textual `DEFAULT_CSS` | `border: solid {P.HUD_CYAN};` |
| Data tables | Rich `Table` with shared helpers | `Table(..., row_styles=["", f"on {P.ROW_ALT}"])` |
| Inline highlights | Rich `Text.append(..., style=...)` | `t.append(label, style=P.LABEL)` |
| Dynamic markup | Rich markup strings | Avoid unless absolutely necessary |

### Adding a New Panel
1. Inherit from `_Panel` in `ui/panels.py`
2. Set `DEFAULT_CSS` with a border colour following the semantic rules above
3. Use `P.*` constants for all colours in `render()`
4. If the panel scrolls, implement `jump_top()` and `jump_bottom()`
5. Register in `NOVAApp.compose()` in `ui/app.py`
6. Add focus handling in `NOVAApp.on_key()` and `_scroll_focused()` if needed
7. Add to `HelpScreen` keyboard shortcuts table
8. Document in `docs/Usage.md`

---

## 12. Conventions for AI Agents

### Before you change anything
1. Run `pytest` and confirm the baseline is green.
2. Read `CLAUDE.md` for detailed event-handling notes, voiceline variables, and known quirks.
3. If you are changing the UI, remember: **threads must not call Textual APIs.** Only `ui/app.py` and its widgets interact with Textual.

### When adding a new journal event handler
- Add the logic in `events.py` inside the `match ev["event"]:` block.
- Update `AppState` in `state.py` if new fields are needed.
- Add a voiceline key to `ed_monitor/voicelines/en.default.toml` (and other languages if you can).
- Add a test in `tests/test_events.py`.

### When adding a new panel or UI mode
- Add the widget class in `ui/panels.py`.
- Register it in `NOVAApp.compose()` in `ui/app.py`.
- Add the abbrev to `SituationalPanel` logic if it is a situational sub-mode.
- Ensure `markup=False` on all `Static` widgets (Textual 8.x compatibility).

### When modifying the database schema
- Add a migration in `db.py` (`_migrate_*`).
- Bump the schema version constant.
- Add a test in `tests/test_db.py`.
- Ensure migrations are atomic (`with self._conn:`).

### When changing config keys
- Add the key to `config.py` (load / save logic).
- Add the setting row to `ui/settings_screen.py` if it should appear in the in-app overlay.
- Document it in `docs/Settings.md`.

### General rules
- Keep changes minimal. This is a production-stable tool; users run it for hours at a time.
- Do not introduce heavy new dependencies. The project prides itself on a small dependency footprint.
- Do not use `async` / `await`. The architecture is fully synchronous threading.
- Prefer `threading.RLock` over `threading.Lock` for re-entrant safety.
- Test your change, then run `pytest` again.

---

## 13. Useful Files for Quick Reference

| File | What to look up |
|------|-----------------|
| `CLAUDE.md` | Event-handling edge cases, voiceline variable reference, status flags, bio prediction rules |
| `docs/Settings.md` | Every `config.toml` key |
| `docs/Usage.md` | Keyboard shortcuts, panel explanations |
| `docs/VoiceVariables.md` | Full template variable catalog |
| `ed_monitor/state.py` | `AppState` fields, `BodyInfo`, value formulas |
| `ed_monitor/events.py` | `handle()` dispatcher — how every journal event is processed |
| `ed_monitor/voicelines.py` | Template engine (`pick()`, includes, conditionals) |
| `ed_monitor/db.py` | Schema, migrations, query patterns |
