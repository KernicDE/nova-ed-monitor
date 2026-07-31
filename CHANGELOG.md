# Changelog

## v2.20.5 — 2026-07-31

### Bug Fixes

- **Material trades were lost on NOVA restart** — `_init_scan` (the state
  rebuild that replays the journal region already processed before a
  restart) uses an event whitelist, and `MaterialTrade` was missing from
  it. After every NOVA restart, all trades from the already-processed
  journal region were dropped, so the assets panel showed wrong counts
  until the next game login. `MaterialTrade` is now replayed there too.

---

## v2.20.4 — 2026-07-31

### Bug Fixes

- **Material trades were not reflected live** — trading at a material
  trader fires `MaterialTrade` journal events, which NOVA did not handle
  at all, so the assets panel kept stale counts until the next login.
  `Paid` is now subtracted (floored at 0) and `Received` added (clamped
  to the catalogue cap), bumping `materials_version` so the panel
  re-renders immediately.

---

## v2.20.3 — 2026-07-31

### Bug Fixes

- **Material catalogue lookup failed for several real journal names** —
  the internal names the game client actually writes (`encryptionarchives`,
  `adaptiveencryptors`, `encryptedfiles`, `encryptioncodes`) were missing
  from the journal-name mapping (wrong guesses were listed instead), so
  `lookup_fuzzy()` fell back to the localised name. Affected materials
  (e.g. Atypical Encryption Archives, Adaptive Encryptors Capture) appeared
  as untracked extra rows with the 100 fallback cap and were never clamped
  — e.g. `132/100` despite a real cap of 150. The mapping now contains the
  verified internal names (plus `symmetrickeys` / `embeddedfirmware`
  aliases); old keys are kept as aliases.

---

## v2.20.2 — 2026-07-31

### Bug Fixes

- **Assets panel did not update while in the SRV** — material counts changed
  via `MaterialCollected` journal events (e.g. scanning data points in the
  SRV), but the situational panel's change-detection key only compared the
  *lengths* of the material dicts. Collecting more of an already-owned
  material never changed the key, so the panel stayed stale until some other
  state change (like docking back in the ship) forced a re-render. Materials
  state now carries a `materials_version` counter that is bumped on every
  mutation (`Materials`, `MaterialCollected`, `MaterialDiscarded`, and
  `Materials.json` snapshots); the assets panel keys off that counter, and
  the UI snapshot now clones the materials dicts.
- **Material counts could exceed the per-material cap** (e.g. `132/100`) —
  the journal reports the full `MaterialCollected` amount even when the game
  silently discards everything above the material's cap (no discard event is
  emitted). NOVA now clamps collected amounts to the catalogue cap.

---

## v2.20.1 — 2026-07-08

### Bug Fixes

- **AI voice fired during journal backlog replay** — on every NOVA startup,
  historical journal events (backlog catch-up + full-file state rebuild scan)
  are replayed through a throwaway "silent" queue so they rebuild state
  without being spoken — this has always been the design for the static
  voiceline path. The new AI-generated voice path (`voice_engine = kimi` /
  `claude`, added in 2.20.0) ignored this signal entirely, submitting a real
  `kimi -p`/`claude -p` subprocess call for *every* replayed event on *every*
  launch — causing API rate-limiting (`429`) and old events being read aloud
  well after the events actually happened. `events.handle()`'s existing
  `live` parameter is now propagated to a module-level flag that `_say()`
  checks before routing to the AI path; when `live=False` (backlog/init
  replay) it always falls back to the plain static text into whichever
  (silent, discarded) queue the caller passed, exactly matching the
  pre-existing static-voiceline behaviour.
- **AI voice ignored the configured language** — the prompt sent to
  `kimi -p`/`claude -p` never told the model which language to respond in,
  so generated lines randomly drifted between English and the configured
  `tts_lang` (e.g. German) from one line to the next while the TTS voice
  itself stayed fixed. The prompt now explicitly instructs the model to
  respond only in the configured language.

---

## v2.20.0 — 2026-07-01

### New Features

- **AI-generated voice lines** — new `voice_engine` setting (`static` | `kimi` |
  `claude`, default `static`). When set to `kimi` or `claude`, NOVA generates
  its spoken lines on the fly via `kimi -p`/`claude -p` instead of picking from
  the built-in template pool, falling back to the static line on any CLI
  failure/timeout. Rapid-fire events (e.g. FSS scanning many bodies) are
  grouped into a single AI call via a debounce window (`ai_voice_burst_window_s`).
  New module `ed_monitor/ai_voice.py`.
- **Personality configuration** — `config/personality/<name>.toml` shapes the
  tone of AI-generated lines (mirrors the voicelines override + reference-copy
  pattern). New module `ed_monitor/personality.py`, `personality_name` setting.
- **Ambient commentary** — optional periodic, unprompted situational remark
  every 180–360 s (randomised), togglable via `ambient_commentary_enabled`.
  Requires `voice_engine != static`. New module `ed_monitor/ambient.py`.
- New Settings overlay rows: **Voice Engine** and **Ambient Commentary**.

---

## v2.19.2 — 2026-06-07

### Changes

- **Portrait: Bodies as Situational tab** — BodiesPanel is no longer a separate
  column in portrait layouts. Instead, "Bodies" appears as the first tab in the
  Situational panel (← / → to switch), giving the full panel width to both the
  body list and all other situational views. BodiesPanel is not mounted at all
  in portrait mode; its content is rendered directly by the Situational panel.

---

## v2.19.1 — 2026-06-07

### Bug Fixes

- **Settings save restarts into Python REPL** — `nova.sh` launched via
  `exec "$VENV_NOVA"` (the pip entry-point script), which set `sys.argv[0]` to
  `/path/to/venv/bin/nova`. The restart logic in `__main__.py` then called
  `os.execv(sys.executable, sys.argv)`, passing argv without a script argument —
  Python started in interactive mode. Fix: `nova.sh` now launches via
  `python -m ed_monitor` so `sys.argv[0]` ends with `__main__.py` and the
  correct restart branch fires. Defence-in-depth: the `else` branch in
  `__main__.py` now uses `os.execv(sys.argv[0], sys.argv)` (exec the entry-point
  directly via its shebang) instead of the broken `python argv[0]` form.

- **pip "new release available" notice on every NOVA update** — pip was only
  auto-upgraded on first install, not on subsequent NOVA updates. pip is now
  silently upgraded whenever NOVA itself is updated.

### Changes

- **Portrait layout: bodies panel as fixed left column** — previous portrait
  layout stacked all panels full-width vertically. New layout splits below the
  top-row into a left column (BodiesPanel, fixed width 79) and a right column
  (SituationalPanel + log row). This matches the landscape feel and makes better
  use of portrait width.

---

## v2.19.0 — 2026-06-07

### New Features

- **Portrait layout modes** — NOVA can now run in portrait orientation for
  vertically mounted monitors or tall terminal windows (e.g. a 1080×1920 display
  or a 960-pixel-tall terminal pane). Three layouts are now available, switchable
  via the Settings overlay (`s` → Layout row → `← / →`):
  - `landscape` — original side-by-side layout (unchanged, default)
  - `portrait-half` — portrait for ~68-row terminals (~960 px tall @ 14 px/row):
    top-row panels stacked horizontally, BodiesPanel full-width (12 rows),
    SituationalPanel full-width (elastic), log row full-width (10 rows)
  - `portrait-full` — portrait for ~137-row terminals (~1920 px tall):
    same structure with taller bodies (18 rows) and log (18 rows) sections
  Layout changes require a restart (same as theme changes).

### Bug Fixes

- **Theme change restart was silently broken** — `on_settings_screen_saved` was
  re-reading `old_theme` from `self._cfg` *after* it had already been replaced
  with the new config object, so the `cfg.theme != old_theme` guard was always
  `False`. Theme changes now correctly trigger a restart.

---

## v2.18.5 — 2026-05-25

### Bug Fixes

- **TTS subprocesses break keyboard input** — every `subprocess.run()` call for
  audio synthesis (`edge_tts`) and playback (`mpg123`, `ffplay`, `afplay`,
  `pygame_sys`, Windows fallbacks) was inheriting the parent's stdin (the
  terminal in Textty raw mode). `mpg123` detects a tty on stdin and calls
  `tcsetattr` to set up its interactive keyboard controls (space=pause, q=quit),
  which re-enables terminal echo and disables raw mode while NOVA is running.
  Key presses were then echoed as literal escape sequences at the terminal cursor
  position (top-left of the Textual frame). Fix: add `stdin=subprocess.DEVNULL`
  to all `subprocess.run()` calls in `tts.py`.

---

## v2.18.4 — 2026-05-25

### Bug Fixes

- **Kitty+fish: two-layer fix for persistent keyboard failure**
  - Root cause: Textual pushes KKP `flags=25` (DISAMBIGUATE | REPORT_ALL_KEYS |
    REPORT_ASSOCIATED_TEXT) which causes Kitty to send sequences that interact
    badly with fish's `flags=31` stack — specifically `\x1b[I` (the FOCUSIN
    marker) was being generated mid-sequence, causing the parser to misread cursor
    keys like `\x1b[1;129C` as a Focus event followed by stray characters.
  - **Fix 1**: Downgrade Textual's KKP push to `flags=1` (DISAMBIGUATE only) by
    zeroing `KITTY_REPORT_ALL_KEYS` and `KITTY_REPORT_ASSOCIATED_TEXT` in
    `linux_driver` before `start_application_mode()` runs. With `flags=1` all keys
    arrive in classic xterm format (`\x1b[C`, `\x1b[1;2C`, etc.) that Textual's
    ANSI dict handles perfectly. No Num Lock modifier, no 3-field sequences.
  - **Fix 2**: Send `\x1b[<u` × 8 to `__stderr__` (same fd as Textual) just before
    `NOVAApp.run()` to pop any leftover fish KKP stack entries. Previous attempts
    (v2.17.3) used `sys.stdout` instead of `sys.__stderr__`, so Kitty processed
    them on the wrong fd ordering.
  - `:N` sub-param stripping from v2.18.3 is kept as a safety net.

---

## v2.18.3 — 2026-05-25

### Bug Fixes

- **Kitty+fish: fix keyboard breaking after < 1 second**
  - v2.18.2's `_collapse_u` regex incorrectly collapsed 3-field sequences produced
    by Textual's own KKP push (`flags=25` includes `REPORT_ASSOCIATED_TEXT`). For
    a plain `'a'` keypress, Kitty sends `\x1b[97;1;97u]` (codepoint; modifier;
    associated_text). The regex captured `97` (associated text) as the modifier,
    producing `\x1b[97;97u]` with modifier_bits=96 — wrong key events every time.
  - Fix: remove the field-collapsing logic entirely. KKP uses `:` sub-params for
    alternate keys, not extra `;`-separated fields. Stripping `:\d+` patterns is
    sufficient. Textual 8.2.7+ handles the 3-field REPORT_ASSOCIATED_TEXT format
    natively without any pre-processing.

---

## v2.18.2 — 2026-05-25

### Bug Fixes

- **Kitty+fish: root cause found — REPORT_ALTERNATE_KEYS drops all character keys**
  - Fish 4.x enables KKP `flags=31` which includes `REPORT_ALTERNATE_KEYS` (bit 4).
    This inserts two extra semicolon-separated fields into every character key
    sequence: e.g. `\x1b[97;65;97;1:1u` (codepoint + shifted + base + modifier +
    event-type). Textual's regex expects at most 3 fields; 4-field sequences never
    matched and every character key was silently dropped.
  - Previous attempts (v2.17.0–v2.18.1) only stripped `:N` event-type sub-params
    and tried clearing the KKP stack — neither addressed the 4-field format.
  - Fix: normalize sequences in `_sequence_to_key_events` before Textual parses them:
    1. Strip `:N` event-type sub-params (`\x1b[97;1:1u` → `\x1b[97;1u`)
    2. Collapse alternate-key extra fields to `codepoint;modifier` form
       (`\x1b[97;65;97;1u` → `\x1b[97;1u`)
  - Works on Textual 8.2.3 and 8.2.7+ without version detection. Handles cursor
    keys, character keys, and Num Lock modifier (129) correctly.

---

## v2.18.1 — 2026-05-25

### Bug Fixes

- **Kitty+fish keyboard fix and theme files now in release**
  - Re-release of v2.18.0 to ensure auto-updater picks up the KKP stack-clearing
    fix (v2.17.3) and the bundled theme files (`themes/*.toml`, `themes/README.md`).

---

## v2.18.0 — 2026-05-25

### New Features

- **Theming System**
  - NOVA now supports custom colour themes via TOML files in `config/themes/`.
  - Two built-in themes: **Default** (classic ED orange-cyan HUD) and **Sakura Night** (soft pink-violet).
  - Themes are selectable in `config.toml` (`theme = sakura`) or via the in-app Settings overlay (first row).
  - Changing the theme requires a restart — NOVA restarts automatically when you save a different theme in Settings.
  - All UI chrome colours (panel borders, mode palettes, overlays, pip colours, chat source colours, etc.) are exposed in the theme file. Gameplay-specific mappings (star classes, planet types) remain hardcoded.
  - See `config/themes/README.md` for the full theme authoring guide.

### Bug Fixes

- **Theme files missing from pip installation**
  - `ed_monitor/themes/` was not listed in `package-data`, so `default.toml`,
    `sakura.toml`, and `README.md` were absent after `pip install`. Theme files
    are now bundled and copied to `config/themes/` on first startup via
    `ensure_theme_files()`.

---

## v2.17.3 — 2026-05-25

### Bug Fixes

- **Kitty+fish: keys still echoed as raw bytes despite v2.17.2 sub-param patch**
  - Fish 4.x re-pushes its KKP flags (31) onto Kitty's stack after Textual's own
    push (`\x1b[>1u` / `\x1b[>25u`), making fish's flags=31 the active layer.
    Even with `:N` sub-params stripped correctly, if terminal echo is active the
    raw sequences appear on screen instead of being interpreted as keypresses.
  - Fix: send `\x1b[<u` × 8 just before `NOVAApp.run()`. This drains any leftover
    KKP push frames (Kitty ignores excess pops), so Textual's subsequent push
    lands on a clean stack and its chosen flags are authoritative. Only sent when
    `KITTY_WINDOW_ID` or `TERM=xterm-kitty` is detected.

---

## v2.17.2 — 2026-05-25

### Bug Fixes

- **Kitty+fish: keys broken on Textual 8.2.7+ (regression in v2.17.1)**
  - v2.17.1 replaced `_re_extended_key` with a 3-group regex. Textual 8.2.7
    introduced a new `_parse_extended_key()` method that expects exactly 2
    groups from that regex; the 3-group replacement caused `ValueError: too
    many values to unpack`, crashing the input thread silently.
  - Fix: detect the Textual version by inspecting the existing regex group
    count. On 8.2.7+ (2 groups), monkey-patch `_parse_extended_key()` to
    strip `:N` sub-parameters before delegating to the original. On 8.2.6
    (3 groups), patch `_re_extended_key` as before.
  - All Kitty+fish sequences now parse correctly on both versions:
    `\x1b[97;1:1u` → `a`, `\x1b[1:129B` → `down`, `\x1b[1;129A` → `up`.

---

## v2.17.1 — 2026-05-25

### Bug Fixes

- **Kitty+fish: cursor keys still garbled after v2.17.0**
  - Root: `\x1b[1:129B` (cursor-down from fish flags=31) puts the sub-parameter
    in the *first* CSI field (before any semicolon), which v2.17.0's regex still
    could not match. Timing: Textual's `\x1b[>1u` push is sent *late* in
    `start_application_mode()`, so for ~1 second fish's flags=31 remains active
    and arrow keys arrive in this `num:subparam final` format.
  - Fix: extend `_re_extended_key` to allow any number of `:N` sub-parameters
    after *either* the first or second CSI number field, covering all Kitty
    protocol sequence variants.
  - Also silence `\x1b[p` and related terminal-control sequences that Kitty
    emits during initialisation; without this they produce spurious `^[p` key
    events.

---

## v2.17.0 — 2026-05-24

### Bug Fixes

- **Kitty + fish: garbled `^[[A^[[O` text on startup — root cause fixed**
  - Previous attempts tried to suppress/disable the Kitty keyboard protocol
    entirely. This was the wrong approach: Textual 8.x sends `\x1b[>1u` to
    enable the protocol and fish re-enables it with flags=31, so suppression
    always lost the race.
  - The actual bug: fish's protocol variant includes an event-type suffix
    (e.g. `\x1b[97;1:1u` for key-press), which Textual's `_re_extended_key`
    regex could not match. The parser then fell back to
    `reissue_sequence_as_keys`, converting ESC bytes to `^` and producing
    visible garbage like `^[[A^[[O` instead of key events.
  - Fix: extend `_re_extended_key` to allow the optional `:N` event-type
    suffix. All prior Kitty-suppression code (TERM env override, protocol
    push/pop patching, input-thread restart wrapper) has been removed.

---

## v2.16.1 — 2026-05-24

### Bug Fixes

- **Input thread dies after ~0.5 s in Kitty — fourth attempt**
  - Added `termios` re-apply when the input thread auto-restarts, in case
    fish or another process changed the terminal settings while NOVA runs.
  - Monkey-patched Textual's `XTermParser._re_extended_key` regex so it
    understands Kitty protocol sequences with `:flags` (e.g. `CSI 97;1:3 u`).
  - Added missing Kitty functional-key codes (arrow keys, home, end, etc.)
    to `_keyboard_protocol.FUNCTIONAL_KEYS` so Textual can map them even
    if the protocol is active.

---

## v2.16.0 — 2026-05-24

### Bug Fixes

- **Remove keep-alive thread + auto-restart input thread**
  - The 500 ms keep-alive thread in v2.15.8/v2.15.9 could interfere with
    Textual's writer queue and may have destabilised the input path.
    Removed entirely.
  - Added a defensive patch on `LinuxDriver._run_input_thread()`:
    if the input thread crashes for any reason it is now automatically
    restarted after a 1 s back-off instead of leaving NOVA without
    keyboard input.

---

## v2.15.9 — 2026-05-24

### Bug Fixes

- **Crash on startup in v2.15.8**
  - `_orig_start` was referenced in `_patched_start` but never captured, causing a `NameError` the instant the driver entered application mode.
  - Fixed by adding the missing `_orig_start = LinuxDriver.start_application_mode` assignment.

---

## v2.15.8 — 2026-05-24

### Bug Fixes

- **Kitty keyboard stops working after ~0.5 s (third attempt)**
  - v2.15.7 only disabled the protocol once at startup. Something (Kitty itself or the fish shell) re-enabled it shortly after the UI appeared, causing keys to die again.
  - Replaced the one-shot disable with an **aggressive three-layer defence**:
    1. `LinuxDriver.write()` is monkey-patched so *any* `\x1b[>Nu` (N≥1) is rewritten to `\x1b[>0u` on the fly.
    2. A tiny keep-alive thread sends `\x1b[>0u` every 500 ms for the entire lifetime of NOVA.
    3. On shutdown we pop every push we created (plus the initial pre-startup push) so the terminal stack is restored cleanly.
  - This guarantees the protocol stays off regardless of what else tries to turn it on.

- **BodiesPanel truncated long body names**
  - Increased the "Body" column width from 11 to 14 characters so names like "Lowing's…" and "Darkes Ho…" render correctly.

---

## v2.15.7 — 2026-05-24

### Bug Fixes

- **Kitty keyboard still broken after v2.15.6**
  - The v2.15.6 patch only prevented Textual from *enabling* the protocol, but did nothing if the user's shell (fish) had already enabled it before NOVA started.
  - Now sending `\x1b[>0u` before startup. This pushes the current state onto the stack and sets Kitty keyboard flags to 0, reliably disabling the protocol for NOVA's lifetime.
  - Textual's `stop_application_mode()` already sends `\x1b[<u` (pop) on exit, so the previous state (e.g. fish's enabled protocol) is restored cleanly.

---

## v2.15.6 — 2026-05-24

### Bug Fixes

- **Kitty terminal keyboard completely non-functional**
  - Textual 8.0.2's Linux driver unconditionally sends `\x1b[>1u` to enable the Kitty keyboard protocol. This causes Kitty to emit CSI-u escape sequences that Textual fails to parse, resulting in garbled screen characters and completely broken key input (arrow keys, Ctrl+C, etc. did not work).
  - Added a monkey-patch on `LinuxDriver.start_application_mode()` that filters out the `\x1b[>1u` sequence before it reaches the terminal. The terminal stays in normal ANSI mode and all keys work as expected.

- **Mouse tracking still active despite `mouse = False`**
  - Setting `mouse = False` as a class attribute on `NOVAApp` has no effect in Textual 8.0.2. Mouse support is controlled exclusively by the `mouse=` parameter of `app.run()`.
  - Changed `NOVAApp(...).run()` to `NOVAApp(...).run(mouse=False)`. This disables mouse tracking at the driver level: no `MouseMove` events are generated (eliminating TTS lag from mouse movement), panels can no longer be hovered/selected with the mouse, and the mouse cursor no longer interacts with the TUI.

---

## v2.15.5 — 2026-05-24

### Bug Fixes

- **Mouse movement causes TTS lag**
  - Rapid `MouseMove` events were flooding the UI thread, causing audio stutter.
  - Added `NOVAApp.mouse = False` and `CSI ?1003l` escape sequence on mount to disable mouse tracking.
  - *Note: this fix was incomplete; v2.15.6 replaces it with the proper driver-level disable.*

---

## v2.15.4 — 2026-05-24

### Bug Fixes

- **Kitty terminal shows garbled keyboard escape sequences**
  - Kitty's CSI-u keyboard protocol sent sequences like `^[[5744;137u^` that Textual did not recognise.
  - Added `TERM=xterm-256color` override when `KITTY_WINDOW_ID` is detected.
  - *Note: this fix was incomplete because Textual's Linux driver re-enabled the protocol later; v2.15.6 replaces it with a driver-level patch.*

---

## v2.15.3 — 2026-05-24

### Bug Fixes

- **German TTS spoke "STRICH" for scan type hyphen**
  - The German voiceline used `{scan_type}-Scan` which the TTS voice read as "Cargo STRICH Scan".
  - Changed to `{scan_type} Scan` in `de.default.toml`.
  - Added hyphen sanitisation in `events.py` so journal `ScanType` values containing dashes are replaced with spaces before speech.

---

## v2.15.2 — 2026-05-24

### Bug Fixes

- **TTS audio engine stops after extended use**
  - `pygame.mixer.quit()` was never called after playback. The mixer was initialised on every TTS message but never shut down, leaking audio resources until the process exited. When another application (e.g. a Python overlay using edge-tts/pygame) competed for the same audio device, the mixer would eventually stop responding.
  - Added `pygame.mixer.quit()` in `finally` blocks on Windows and in the Linux subprocess fallback.

- **PipeWire audio routing improved**
  - Reordered Linux audio backends: plain `mpg123` is now tried before `mpg123 -o pulse`. On PipeWire systems the ALSA route is often more reliable when multiple apps compete for the audio device.

---

## v2.15.0 — 2026-05-24

### Features

- **Complete TTS unit localization for all supported languages**
  - NOVA now speaks units, measurements, and status phrases in the user's configured `tts_lang` instead of mixing English into non-English sentences.
  - Localized: light years/seconds, credits, population (million/billion), temperature (Kelvin), distance (kilometres), mass (Earth masses), gravity (G), orbital period (minutes/hours/days), and many more.
  - Added `[units]` tables to all 7 built-in voiceline TOMLs (`en`, `de`, `fr`, `es`, `it`, `pt`, `ru`) so every unit word is translated.

- **Slavic plural support for Russian TTS**
  - Russian uses 3 plural forms (1 / 2–4 / 5+). NOVA now correctly selects "световой год" (1), "световых года" (2–4), or "световых лет" (5+) based on the number.
  - Added `_slavic_plural()` helper and `unit_for()` with plural dispatch to `voicelines.py`.

- **Localized FSDJump suffixes**
  - Star class, scoopable status, remaining jumps, and population are now spoken in the target language.
  - Example (German): "Ankunft in Zeessze. Sprung über 11,2 Lichtjahre. Stern Typ K, tankbar. 3 Sprünge verbleiben. Bevölkerung: 37 Millionen."

### Bug Fixes

- **Fixed duplicate `[FSDJump_Home]` key in `en.default.toml`**
  - The duplicate table caused `tomllib` to reject the entire English voiceline file, silently breaking all English TTS fallback paths.

- **Translated `FSDJump_Home` in all non-English languages**
  - Previously this line was always spoken in English regardless of language setting.

- **Eliminated `{bio_word}` / `{verb}` dependency in bio scan voicelines**
  - These variables only worked for English grammar ("is" / "are", "bio" / "bios"). Each language now uses its own natural sentence structure.

- **Moved `First footfall bonus applied` into WHEN...THEN blocks**
  - Previously hardcoded English string; now localized per language via conditional voiceline templates.

---

## v2.14.10 — 2026-05-10

### Bug Fixes

- **Clean up localisation tokens in target names**
  - Elite Dangerous sometimes emits raw internal keys like `$MULTIPLAYER_SCENARIO79_TITLE;` in `Status.json Destination.Name` when a localised string is missing (e.g. for new Frontline zones, Megaships, etc.). This produced unreadable text in the Target panel.
  - Added `_clean_localised()` in `events.py` which strips the `$...;` wrapper and turns underscores into readable Title Case text.
  - Applied to `target_body`, `target_body_system`, `target_body_body`, and `nearest_body` in `status.py` so every destination read from `Status.json` is sanitised at the source.

---

## v2.14.9 — 2026-05-10

### Features

- **Improved target information for all target types**
  - Surface settlements / planetary ports now show their parent **body** (planet/moon) when targeted.
  - Cross-system targets (bodies, stations, or settlements in another system) now display the **target system** name.
  - Unknown targets (systems or bodies not in the local database) now show any available **EDSM route data** (population, allegiance) if the target happens to be a route waypoint.
  - `_render_target()` fallback no longer displays a bare name — it always provides context (system, body, or EDSM metadata).

---

## v2.14.8 — 2026-05-10

### Features

- **Station targeting in Target panel**
  - When a station is targeted (via left-panel nav or galaxy map), the Target panel now displays EDSM station data instead of falling through to "No target".
  - Shows: station name, type (Coriolis, Outpost, etc.), distance from star, and services icons (M=Market, S=Shipyard, O=Outfitting, R=Repair, F=Refuel, N=Restock).
  - If the station is in a different system, the system name is shown too.
  - Implementation: `status.py` reads `Destination.System` from `Status.json`; `journal.py` fetches current-system stations from the local EDSM dump; `panels.py` looks up the target in current/route/nearest station lists and renders the info.

---

## v2.14.7 — 2026-05-10

### Bug Fixes

- **Volume control — +/- keys still reset to config default**
  - v2.14.6 fixed the reload loop caused by `config.toml.example` writes, but the watchdog path still fired on *every* file change inside `~/.config/nova/`. This meant overlay `.txt` writes (1 Hz) and bindings backups triggered spurious config reloads, which unconditionally reset `state.volume` to `default_volume`.
  - Fixed by filtering the `watchdog` event handler so it only reacts to `config.toml` and `*.toml` files directly inside `voicelines/`. All other files in the config directory (overlay, bindings_backup, cache, etc.) are now ignored.

---

## v2.14.6 — 2026-05-07

### Bug Fixes

- **Volume control — +/- keys reset to config default**
  - `_update_example_file()` wrote `config.toml.example` on every `config.load()` call, including inside the hot-reload callback. The file-system watcher picked up that write and re-triggered the callback in a ~0.3 s loop, resetting `state.volume` to `default_volume` from config.toml after every keypress.
  - Fixed by calling `_notify_self_write()` after writing the example file so the watcher ignores self-generated events.
  - Also fixed `_on_config_changed` not updating `volume[0]` (the TTS worker list), keeping display and playback volume in sync on genuine config reloads.

---

## v2.14.5 — 2026-05-07

### Bug Fixes

- **#122 Material Tracker — category overflow & edge margins**
  - Category names (e.g. "Emission Data", "Data Archives") are now properly truncated with `…` when they exceed the allocated column width, preventing line breaks in narrow terminals
  - Added 1-space left and right margin to every material row so text no longer touches the panel walls

---

## v2.14.4 — 2026-05-07

### Enhancements

- **#126 Make missions better readable**
  - Empty line between each destination system block for clearer visual separation
  - Mission rows indented by 2 spaces relative to the column header
  - Blank line added between the massacre progress section and the first destination block

---

## v2.14.3 — 2026-05-07

### Enhancements

- **#122 Material Tracker — Compact Vertical List (Option A)**
  - Replaced horizontal grade-based tables with a compact vertical list: one row per material
  - Columns: Category | Grade | Name | Count/Cap | [Progress Bar] | Percentage
  - Global column alignment: widths computed once across all material types and applied uniformly
  - Space-filling progress bars: all remaining panel width goes to the bar after fixing other columns
  - Minimum 1-space gap between every column
  - Names truncate with … when tight; full names shown on wide terminals
  - Colour coding: dim grey (empty), white (partial), amber (near-cap), green (≥80%)
  - Scroll count fixed: counts individual material rows for smooth scrolling

---

## v2.14.2 — 2026-05-07

### Enhancements

- **#122 Material Tracker — Layout Overhaul**
  - Horizontal grade-based tables: G1–G5 as columns, categories as rows
  - Aligned columns within each material type (Raw / Manufactured / Encoded)
  - Two rows per category: name+count/cap, then progress bar+percentage
  - Responsive truncation for narrow terminals
  - Fixed scroll bug: scroll count now correctly includes category headers

---

## v2.14.1 — 2026-05-07

### Bug Fixes

- **#120 Fix wording in docking computer**
  - Coriolis, Orbis, and Ocellus station hints now use **Front / Back** terminology instead of inner / outer rings
  - All cylindrical station types are now consistent with the spatial layout relative to the mailslot

- **#121 Slow refresh rate of position in orbital cruise**
  - Status monitor now **slow-polls (5 s) in deep space** when no lat/lon/alt data is present
  - Fast-poll (0.2 s) preserved for: landed, SRV, on-foot, orbital cruise, and near-surface flight
  - Reduces unnecessary CPU load when exact positions aren't needed

---

## v2.14.0 — 2026-05-06

### Enhancements

- **#122 Material Tracker**
  - New Assets panel section showing full Raw (G1‑G4), Manufactured (G1‑G5), and Encoded (G1‑G5) material catalogues
  - Zero-count materials shown dimmed; owned materials highlighted with colour-coded stock levels
  - Progress bars and percentage indicators for every material
  - Uses the verified in-game material catalogue with correct caps per grade

- **#123 Fuel Warning**
  - Configurable fuel threshold (default 25%) in `config.toml`
  - Triggers `LowFuel` TTS voiceline and event log entry when fuel drops below threshold

- **#124 Home System**
  - New `home_system` config key — set your home system name
  - `FSDJump_Home` voiceline fires on arrival (falls back to `FSDJump` if undefined)

- **#125 Panel Toggles**
  - New `situational_panels` config key controls which situational panels are shown and in what order
  - Cycle left/right only visits visible panels

---

## v2.13.0 — 2026-05-05

### Enhancements

- **In-app Settings Overlay** (`S` key)
  - Live editable settings: TTS rate/volume, voice selection per language, panel toggles, fuel threshold, home system
  - Voice catalog fetched from `edge-tts` with language filtering
  - Settings saved back to `config.toml` on confirm (`Enter`)
  - Cancel (`Esc` / `Q`) discards changes

- **Bio Panel Improvements**
  - Distance and bearing calculations now use proper spherical geometry with body-radius scaling
  - Prescan and predicted body rows show genus list and estimated value range
  - First-footfall bonus tracking across sessions

- **Mission Panel Improvements**
  - Destination grouping: massacre missions to the same system are stacked with kill counts
  - Type badges (Massacre, Courier, etc.) and wing/influence indicators
  - Reward column with CR formatting and colour coding

---

## v2.12.0 — 2026-05-04

### Enhancements

- **Neutron Route Planner**
  - Integrated Spansh neutron router: request routes, monitor progress, display hop list with scoopable indicators
  - Scrollable route list with jump range and remaining distance

- **Colonisation Panel**
  - Track colonisation construction sites, required commodities, and completion progress
  - Commodity tables with delivered / required counts

- **Engineers Panel**
  - List view with rank pips, unlock status, and invite progress
  - Detail view with workshop location, modifications offered, and experimental effects

---

## v2.11.0 — 2026-05-03

### Enhancements

- **BGS Panel**
  - System-level faction influence tracking with colour-coded bars
  - State badges (Boom, War, Election, etc.) and pending/recovery indicators
  - Activity log grouped by system with timestamps

- **Route Panel**
  - In-system route display with next waypoint, distance, and scoopable star indicator
  - Station list for next system with services and landing pad sizes

- **Stats Panel**
  - Session and lifetime statistics: jumps, scans, mapped bodies, first discoveries, total exploration value
  - Credits balance and session earnings
