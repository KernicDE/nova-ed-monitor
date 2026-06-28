# Voiceline Silence Fix + User File Validation (Issue #99) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `replace = []` not silencing TTS events, and add user-friendly validation of user voiceline files.

**Architecture:** Two independent fixes in `voicelines.py` and `events.py`/`status.py`. The silence bug stems from `_say()` using `or fallback` even when `pick()` returns `None` due to an explicit empty `replace = []`. The fix adds `is_muted()` to `voicelines.py` and guards both `_say()` and `_q()` callers. Validation parses the user file separately from the main load path so a broken file logs a warning without crashing.

**Tech Stack:** Python 3.11+, `tomllib` (stdlib), existing `voicelines.py` / `events.py` / `status.py` / `__main__.py`.

---

## File Map

| File | Change |
|------|--------|
| `ed_monitor/voicelines.py` | Add `is_muted(key, lang)` + `validate_user_file(lang) -> Optional[str]` |
| `ed_monitor/events.py` | Guard `_say()` with `is_muted()` before `or fallback` |
| `ed_monitor/status.py` | Guard `_q()` and inline `pick() or fallback` calls with `is_muted()` |
| `ed_monitor/__main__.py` | Call `validate_user_file()` at startup; push LogEvent + TTS on error |
| `tests/test_voicelines.py` | New file: unit tests for both fixes |

---

## Bug Explanation (read before coding)

In `events.py:493`:
```python
text = _vl.pick(key, lang=_TTS_LANG, **kwargs) or fallback
```
When a user sets `replace = []`, `_load()` stores `lines[key] = []` (correct). `pick()` sees `key in lines_map` → `variants = []` → `not variants` → returns `None`. But then `None or fallback` evaluates to `fallback`, so the hardcoded fallback string is spoken anyway.

The same bug exists in `status.py` at line 284 (`_q()`) and lines 419, 425, 540, 564 (inline `pick() or ...`).

---

### Task 1: Add `is_muted()` to voicelines.py

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Create: `tests/test_voicelines.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_voicelines.py`:

```python
"""Tests for voicelines.py — silence fix and validation."""
from __future__ import annotations

import tomllib
import tempfile
from pathlib import Path
import pytest

import ed_monitor.voicelines as vl


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Point voicelines at a temp dir so tests don't touch ~/.config/nova."""
    monkeypatch.setattr(vl, "_CONFIG_DIR", tmp_path)
    vl._CACHE.clear()
    yield
    vl._CACHE.clear()


def _write_user_file(tmp_path: Path, lang: str, content: str) -> None:
    d = tmp_path / "voicelines"
    d.mkdir(exist_ok=True)
    (d / f"{lang}.toml").write_text(content, encoding="utf-8")


class TestIsMuted:
    def test_not_muted_when_key_absent(self, tmp_path):
        assert vl.is_muted("SomeEvent", "en") is False

    def test_not_muted_when_replace_has_lines(self, tmp_path):
        _write_user_file(tmp_path, "en", '[FSDJump]\nreplace = ["Jumping."]\n')
        assert vl.is_muted("FSDJump", "en") is False

    def test_muted_when_replace_empty(self, tmp_path):
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        assert vl.is_muted("FSDJump", "en") is True

    def test_muted_does_not_affect_other_keys(self, tmp_path):
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        assert vl.is_muted("Docked", "en") is False

    def test_muted_for_lang_only(self, tmp_path):
        """Silencing in 'de' does not silence 'en'."""
        _write_user_file(tmp_path, "de", "[FSDJump]\nreplace = []\n")
        assert vl.is_muted("FSDJump", "de") is True
        assert vl.is_muted("FSDJump", "en") is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_voicelines.py::TestIsMuted -v
```

Expected: `FAILED` — `AttributeError: module 'ed_monitor.voicelines' has no attribute 'is_muted'`

- [ ] **Step 3: Add `is_muted()` to voicelines.py**

Add after the `pick()` function (after line ~175, before `reload()`):

```python
def is_muted(key: str, lang: str = "en") -> bool:
    """Return True if *key* has been explicitly silenced with ``replace = []``."""
    lines_map = _load(lang)
    return key in lines_map and lines_map[key] == []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_voicelines.py::TestIsMuted -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/voicelines.py tests/test_voicelines.py
git commit -m "feat: add is_muted() to voicelines for replace=[] detection"
```

---

### Task 2: Fix `_say()` and `_q()` to respect `replace = []`

**Files:**
- Modify: `ed_monitor/events.py`
- Modify: `ed_monitor/status.py`
- Modify: `tests/test_voicelines.py`

- [ ] **Step 1: Write the failing test (integration style)**

Append to `tests/test_voicelines.py`:

```python
class TestSilencePropagation:
    """Verify that replace=[] prevents any TTS output, even when a fallback exists."""

    def test_pick_returns_none_when_silenced(self, tmp_path):
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        result = vl.pick("FSDJump", lang="en")
        assert result is None

    def test_is_muted_true_blocks_fallback(self, tmp_path):
        """
        Simulate what _say() should do:
        if is_muted → skip, even if fallback is non-empty.
        """
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        fallback = "Jumping to hyperspace."
        # Current (broken) behaviour: pick() or fallback → speaks fallback
        broken = vl.pick("FSDJump", lang="en") or fallback
        assert broken == fallback  # documents the bug

        # Correct behaviour: check is_muted first
        if vl.is_muted("FSDJump", "en"):
            text = None
        else:
            text = vl.pick("FSDJump", lang="en") or fallback
        assert text is None
```

- [ ] **Step 2: Run tests to confirm current behaviour is documented**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_voicelines.py::TestSilencePropagation -v
```

Expected: Both PASSED (including the `broken` assertion that documents the bug — this will keep passing after the fix too since it tests the raw `pick() or fallback` pattern).

- [ ] **Step 3: Fix `_say()` in events.py**

In `ed_monitor/events.py`, replace the `_say()` function body (currently line 488–495):

```python
def _say(
    tts_q: queue.Queue, key: str, priority: bool, fallback: str = "",
    *, cacheable: bool = True, **kwargs,
) -> None:
    """Pick a voiceline variant and speak it; falls back to *fallback* string.

    When the user has ``replace = []`` for *key*, the event is completely
    silenced — the *fallback* string is NOT used.
    """
    if _vl.is_muted(key, lang=_TTS_LANG):
        return
    text = _vl.pick(key, lang=_TTS_LANG, **kwargs) or fallback
    if text:
        _speak(tts_q, text, priority, cacheable=cacheable)
```

- [ ] **Step 4: Fix `_q()` and inline `pick() or` calls in status.py**

In `ed_monitor/status.py`, the inner `_q()` function at line 281. Replace:

```python
def _q(key: str, fallback: str, pri: bool = False, **kwargs):
    nonlocal lang
    text  = _vl.pick(key, lang=lang, **kwargs) or fallback
```

With:

```python
def _q(key: str, fallback: str, pri: bool = False, **kwargs):
    nonlocal lang
    if _vl.is_muted(key, lang=lang):
        return
    text  = _vl.pick(key, lang=lang, **kwargs) or fallback
```

Also fix the three inline `pick() or` patterns in `status.py` (lines ~419, 425, 540, 564). For each, add an `is_muted` guard. Example pattern for line 419:

```python
# Before:
text = _vl.pick("MassLocked", lang=lang) or "Mass locked."

# After:
if not _vl.is_muted("MassLocked", lang=lang):
    text = _vl.pick("MassLocked", lang=lang) or "Mass locked."
else:
    text = None
```

Locate each inline `pick() or "..."` call in `status.py` and apply this guard pattern. (There are 4 such sites: MassLocked ~419, MassLockReleased ~425, BioReady ~540, BioTooClose ~564.)

- [ ] **Step 5: Run full test suite**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/ -v
```

Expected: All PASSED.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/events.py ed_monitor/status.py tests/test_voicelines.py
git commit -m "fix: replace=[] now silences events completely, ignoring fallback (#99)"
```

---

### Task 3: User voiceline file validation

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Modify: `ed_monitor/__main__.py`
- Modify: `tests/test_voicelines.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_voicelines.py`:

```python
class TestValidateUserFile:
    def test_returns_none_when_no_user_file(self, tmp_path):
        result = vl.validate_user_file("en")
        assert result is None

    def test_returns_none_for_valid_file(self, tmp_path):
        _write_user_file(tmp_path, "en", '[FSDJump]\nreplace = ["Jumping."]\n')
        result = vl.validate_user_file("en")
        assert result is None

    def test_returns_error_message_for_invalid_toml(self, tmp_path):
        _write_user_file(tmp_path, "en", "this is not\nvalid toml [\n")
        result = vl.validate_user_file("en")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_message_does_not_contain_exact_parse_error(self, tmp_path):
        """User-facing message must be generic — do not expose TOML parser internals."""
        _write_user_file(tmp_path, "en", "[bad\n")
        result = vl.validate_user_file("en")
        assert result is not None
        # Must NOT contain Python exception class names or file paths
        assert "TOMLDecodeError" not in result
        assert "Traceback" not in result
```

- [ ] **Step 2: Run to confirm failures**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_voicelines.py::TestValidateUserFile -v
```

Expected: `FAILED` — `AttributeError: module 'ed_monitor.voicelines' has no attribute 'validate_user_file'`

- [ ] **Step 3: Add `validate_user_file()` to voicelines.py**

Add after `is_muted()`:

```python
def validate_user_file(lang: str) -> Optional[str]:
    """Validate the user voiceline file for *lang*.

    Returns None if the file doesn't exist or parses successfully.
    Returns a short user-friendly error message if the file has a syntax error.
    The message deliberately does not include TOML parser internals.
    """
    user_path = _config_dir() / "voicelines" / f"{lang}.toml"
    if not user_path.exists():
        return None
    try:
        with open(user_path, "rb") as f:
            tomllib.load(f)
        return None
    except Exception:
        return (
            f"User voiceline file '{lang}.toml' has a syntax error and will not be used. "
            "Please check and fix the file."
        )
```

- [ ] **Step 4: Run the test**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_voicelines.py::TestValidateUserFile -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Call validation at startup in `__main__.py`**

In `ed_monitor/__main__.py`, after the `voicelines.ensure_user_files()` call (~line 74), add:

```python
    voicelines.ensure_user_files()   # copy built-ins to config dir if missing
    voicelines._load(cfg.tts_lang)   # pre-warm cache

    # Validate user voiceline file — warn on parse error without crashing
    _vl_error = voicelines.validate_user_file(cfg.tts_lang)
```

Then later, after `state.push_event(LogEvent.new(EventCategory.System, "NOVA active."))` (~line 115), add:

```python
        state.push_event(LogEvent.new(EventCategory.System, "NOVA active."))
        if _vl_error:
            state.push_event(LogEvent.new(EventCategory.System, f"⚠ {_vl_error}"))
```

And after the TTS startup message block (~line 133), add:

```python
    if _vl_error:
        try:
            tts_q.put_nowait(TtsMsg(
                text="Warning: voiceline file has an error and will not be used.",
                priority=True,
                volume=cfg.default_volume,
                voice=None,
                deduplication_key="VoicelineFileError",
            ))
        except Exception:
            pass
```

- [ ] **Step 6: Run full suite**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/ -v
```

Expected: All PASSED.

- [ ] **Step 7: Commit**

```bash
git add ed_monitor/voicelines.py ed_monitor/__main__.py tests/test_voicelines.py
git commit -m "feat: validate user voiceline file at startup, warn in log and TTS (#99)"
```

---

### Task 4: Version bump, push, release, close issue

- [ ] **Step 1: Bump version in `pyproject.toml`**

Change `version = "1.32.3"` → `version = "1.32.4"`.

- [ ] **Step 2: Run full test suite one final time**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/ -v
```

Expected: All PASSED.

- [ ] **Step 3: Commit, tag, push, release**

```bash
git add pyproject.toml
git commit -m "chore: bump to 1.32.4"
git tag v1.32.4
git push origin main v1.32.4
gh release create v1.32.4 --repo KernicDE/nova-ed-monitor \
  --title "Fix replace=[] voiceline silencing + user file validation" \
  --notes "## What's Changed
### Fixes (#99)
- **\`replace = []\` now silences events completely** — previously the hardcoded fallback text was still spoken.
- **User voiceline file validation** — on startup, if the user's \`{lang}.toml\` has a TOML syntax error, NOVA logs a warning in the Event log and speaks a TTS alert. The file is not used; built-in defaults take over."
gh issue comment 99 --repo KernicDE/nova-ed-monitor \
  --body "Implemented in v1.32.4. See release notes."
gh issue close 99 --repo KernicDE/nova-ed-monitor
```
