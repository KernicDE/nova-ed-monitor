# Voiceline Template Engine — Includes & Conditionals (Issue #96)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the voiceline template engine with two new authoring features: (1) reusable include fragments (`{include:_KeyName}` or shorthand `{_KeyName}`) and (2) inline conditional message parts (`WHEN condition THEN "text";`). Both are processed by the engine before the final `{variable}` substitution pass.

**Architecture:** All new logic lives in `ed_monitor/voicelines.py`. The `pick()` function gains a three-step render pipeline: expand includes → evaluate conditionals → `.format_map()`. No new modules, no changes to how callers invoke `pick()` — fully backwards-compatible.

**Tech Stack:** Python 3.11+, stdlib `re`, existing `tomllib` TOML loader, `pytest`

---

## Authoring Reference (what users will write)

### Includes

Define a fragment (key must start with `_`) in your user TOML:

```toml
[_ship_status]
add = ["{ship_name} — hull {hull}, fuel {fuel}."]

[FSDJump]
add = ["Arrived in {system}. {include:_ship_status}"]
# Shorthand (equivalent):
add = ["Arrived in {system}. {_ship_status}"]
```

**Two equivalent syntaxes:**

| Syntax | Key name restriction | Use when |
|--------|----------------------|----------|
| `{include:_KeyName}` | Any characters (letters, digits, `_`, `-`) | Key contains hyphens or you want to be explicit |
| `{_KeyName}` | Word characters only (`[a-zA-Z0-9_]`) | Shorter, more natural for simple key names |

> **Hyphen note:** `{_my-fragment}` does **not** work as a shorthand because Python's `format_map()` would mis-parse the `-` as subtraction on an unresolved key. Use `{include:_my-fragment}` for hyphenated keys.

Rules:
- Fragment keys start with `_`; they are never spoken directly by NOVA
- Both syntaxes are replaced at render time with a randomly picked line from the fragment pool
- The picked fragment line is itself variable-formatted with the same kwargs
- Missing fragment key → warning logged, expands to `""`
- Circular includes (A includes B includes A) → detected at depth > 5, expands to `""`

### Conditionals

Inline `WHEN condition THEN "text"` clauses within any template line:

```toml
[FSDJump]
add = ["Arrived in {system}. WHEN {terra} IS TRUE THEN \"Terraformable system.\";"]

[Scan_Notable]
add = ["Scanned {body_short}. WHEN {value_raw} > 500000 THEN \"Worth {value}.\"; WHEN {bio_count} > 0 THEN \"{bio_count} bio signatures.\";"]
```

- Terminated by `;` (optional at end of string)
- Condition false → the whole `WHEN...;` block is replaced with `""`
- THEN text may contain `{variable}` references — filled in the final format pass
- Multiple WHEN clauses in one line are all evaluated independently

**Supported operators:**

| Operator | Type | Example |
|----------|------|---------|
| `IS TRUE` | Truthy check | `WHEN {terra} IS TRUE THEN "..."` |
| `IS FALSE` | Falsy check | `WHEN {first_disc} IS FALSE THEN "..."` |
| `IS NOT TRUE` | Non-truthy | `WHEN {landable} IS NOT TRUE THEN "..."` |
| `==` | Equality | `WHEN {economy} == "Refinery" THEN "..."` |
| `!=` | Not equal | `WHEN {economy} != "Refinery" THEN "..."` |
| `<` | Less than | `WHEN {hull_raw} < 50 THEN "..."` |
| `>` | Greater than | `WHEN {bio_count} > 0 THEN "..."` |
| `<=` | Less or equal | `WHEN {hull_raw} <= 25 THEN "..."` |
| `>=` | Greater or equal | `WHEN {hull_raw} >= 75 THEN "..."` |
| `AND` | Logical AND | `WHEN {bio_count} > 0 AND {first_disc} IS TRUE THEN "..."` |
| `OR` | Logical OR | `WHEN {terra} IS TRUE OR {landable} IS TRUE THEN "..."` |

**Truthy/falsy rules:** A variable value is truthy when it is non-empty and not `"0"` or `"false"` (case-insensitive). Most flag variables (`{terra}`, `{landable}`, `{first_disc}`) are `""` when absent and non-empty when present — so `IS TRUE` works naturally.

---

## Render Pipeline (inside `pick()`)

```
Random template string
        │
        ▼  _expand_includes(template, lines_map, kwargs, depth=0)
Includes expanded (fragment text inserted)
        │
        ▼  _evaluate_conditionals(template, kwargs)
WHEN clauses replaced with THEN text or ""
        │
        ▼  template.format_map(SafeDict(kwargs))
Final formatted string
```

`SafeDict` is a `dict` subclass that returns `""` for unknown keys instead of raising `KeyError` — protects against unknown `{variables}` in user templates.

---

## File Map

| File | Action |
|---|---|
| `ed_monitor/voicelines.py` | Add `_expand_includes()`, `_eval_condition()`, `_eval_clause()`, `_evaluate_conditionals()`, `_render()`, update `pick()`, update `_load()` to collect `_` fragment keys |
| `ed_monitor/voicelines/en.default.toml` | Add authoring comments with include and conditional examples |
| `tests/test_voicelines_template.py` | All new tests |
| `pyproject.toml` | Bump to `v1.35.0` |

---

## Task 1: Helper utilities — `SafeDict` and `_eval_clause()`

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Create: `tests/test_voicelines_template.py`

- [ ] **Step 1: Write failing tests for `_eval_clause()`**

```python
# tests/test_voicelines_template.py
"""Tests for the voiceline template engine — includes and conditionals (issue #96)."""
from __future__ import annotations
import pytest
from ed_monitor.voicelines import _eval_clause, _eval_condition, _expand_includes, _evaluate_conditionals


class TestEvalClause:
    def test_is_true_with_nonempty(self):
        assert _eval_clause("Terraformable IS TRUE") is True

    def test_is_true_with_empty(self):
        assert _eval_clause(" IS TRUE") is False

    def test_is_false_with_empty(self):
        assert _eval_clause(" IS FALSE") is True

    def test_is_false_with_nonempty(self):
        assert _eval_clause("Landable IS FALSE") is False

    def test_is_not_true_with_nonempty(self):
        assert _eval_clause("Landable IS NOT TRUE") is False

    def test_is_not_true_with_empty(self):
        assert _eval_clause(" IS NOT TRUE") is True

    def test_numeric_less_than_true(self):
        assert _eval_clause("25 < 50") is True

    def test_numeric_less_than_false(self):
        assert _eval_clause("75 < 50") is False

    def test_numeric_greater_than(self):
        assert _eval_clause("3 > 0") is True

    def test_numeric_equal(self):
        assert _eval_clause("100 == 100") is True

    def test_numeric_not_equal(self):
        assert _eval_clause("50 != 100") is True

    def test_numeric_lte(self):
        assert _eval_clause("50 <= 50") is True

    def test_numeric_gte(self):
        assert _eval_clause("75 >= 75") is True

    def test_string_equality_true(self):
        assert _eval_clause('Industrial == Industrial') is True

    def test_string_equality_false(self):
        assert _eval_clause('Refinery == Industrial') is False

    def test_string_equality_quoted(self):
        assert _eval_clause('Refinery == "Refinery"') is True

    def test_string_not_equal(self):
        assert _eval_clause('Industrial != "Refinery"') is True

    def test_zero_is_falsy_for_is_true(self):
        assert _eval_clause("0 IS TRUE") is False

    def test_zero_is_truthy_for_is_false(self):
        assert _eval_clause("0 IS FALSE") is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestEvalClause -v
```
Expected: FAIL — `_eval_clause` not defined.

- [ ] **Step 3: Add `_eval_clause()` and `SafeDict` to `voicelines.py`**

Add after the existing imports:

```python
class _SafeDict(dict):
    """dict subclass that returns '' for missing keys instead of raising KeyError.
    Used in format_map() so unknown {variables} in user templates don't crash."""
    def __missing__(self, key: str) -> str:
        return ""
```

Add as module-level functions (not inside a class):

```python
def _eval_clause(clause: str) -> bool:
    """Evaluate a single condition clause.

    Supported forms:
      value IS TRUE / IS FALSE / IS NOT TRUE / IS NOT FALSE
      left == right  |  left != right  |  left < right  |  left > right
      left <= right  |  left >= right
    Values are compared numerically when both sides parse as float,
    otherwise as stripped strings. '' and '0' are falsy for IS TRUE checks.
    """
    clause = clause.strip()

    # IS NOT TRUE / IS NOT FALSE
    m = re.match(r'^(.*?)\s+IS\s+NOT\s+(TRUE|FALSE)\s*$', clause, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        right = m.group(2).upper()
        is_truthy = bool(val) and val.upper() not in ("FALSE", "0")
        return (not is_truthy) if right == "TRUE" else is_truthy

    # IS TRUE / IS FALSE
    m = re.match(r'^(.*?)\s+IS\s+(TRUE|FALSE)\s*$', clause, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        right = m.group(2).upper()
        is_truthy = bool(val) and val.upper() not in ("FALSE", "0")
        return is_truthy if right == "TRUE" else not is_truthy

    # Comparison operators (==, !=, <=, >=, <, >)
    m = re.match(r'^(.*?)\s*(==|!=|<=|>=|<|>)\s*(.*)\s*$', clause)
    if m:
        left  = m.group(1).strip().strip('"')
        op    = m.group(2)
        right = m.group(3).strip().strip('"')
        try:
            lf, rf = float(left), float(right)
            return {
                "==": lf == rf, "!=": lf != rf,
                "<":  lf <  rf, ">":  lf >  rf,
                "<=": lf <= rf, ">=": lf >= rf,
            }[op]
        except ValueError:
            return {
                "==": left == right, "!=": left != right,
                "<":  left <  right, ">":  left >  right,
                "<=": left <= right, ">=": left >= right,
            }[op]

    # Bare value — truthy check
    return bool(clause) and clause.upper() not in ("FALSE", "0")
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestEvalClause -v
```
Expected: 20 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/voicelines.py tests/test_voicelines_template.py
git commit -m "feat: add _SafeDict and _eval_clause() for voiceline conditional engine (#96)"
```

---

## Task 2: `_eval_condition()` — AND/OR logic

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Modify: `tests/test_voicelines_template.py`

- [ ] **Step 1: Write failing tests**

```python
class TestEvalCondition:
    def test_and_both_true(self):
        assert _eval_condition("3 > 0 AND Terraformable IS TRUE", {}) is True

    def test_and_first_false(self):
        assert _eval_condition("0 > 3 AND Terraformable IS TRUE", {}) is False

    def test_and_second_false(self):
        assert _eval_condition("3 > 0 AND  IS TRUE", {}) is False

    def test_or_first_true(self):
        assert _eval_condition("3 > 0 OR  IS TRUE", {}) is True

    def test_or_both_false(self):
        assert _eval_condition(" IS TRUE OR 0 > 3", {}) is False

    def test_variable_substitution(self):
        # {bio_count} = "3" → 3 > 0 is True
        assert _eval_condition("{bio_count} > 0", {"bio_count": "3"}) is True

    def test_variable_substitution_false(self):
        # {bio_count} = "" → "" > 0: non-numeric comparison, "" > "0" is False
        # actually "" < "0" in string comparison — but more importantly
        # when bio_count is "" (absent), numeric parse fails, "" > "0" string → False
        assert _eval_condition("{bio_count} > 0", {"bio_count": ""}) is False

    def test_is_true_via_var(self):
        # {terra} = "Terraformable" → IS TRUE
        assert _eval_condition("{terra} IS TRUE", {"terra": "Terraformable"}) is True

    def test_is_true_via_empty_var(self):
        # {terra} = "" → IS TRUE is False
        assert _eval_condition("{terra} IS TRUE", {"terra": ""}) is False

    def test_and_with_vars(self):
        assert _eval_condition(
            "{bio_count} > 0 AND {first_disc} IS TRUE",
            {"bio_count": "2", "first_disc": "Undiscovered"},
        ) is True

    def test_or_with_vars(self):
        assert _eval_condition(
            "{terra} IS TRUE OR {landable} IS TRUE",
            {"terra": "", "landable": "Landable"},
        ) is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestEvalCondition -v
```
Expected: FAIL — `_eval_condition` not defined.

- [ ] **Step 3: Add `_eval_condition()` to `voicelines.py`**

```python
# Regex to find {varname} references in a condition string
_COND_VAR_RE = re.compile(r'\{(\w+)\}')


def _eval_condition(condition: str, kwargs: dict) -> bool:
    """Evaluate a full WHEN condition (may contain AND/OR) against kwargs.

    Variable references {varname} are substituted from kwargs before evaluation.
    OR has lower precedence than AND: each OR-group is ANDed together.
    """
    # Substitute {var} with values from kwargs
    def _sub(m: re.Match) -> str:
        return str(kwargs.get(m.group(1), ""))

    cond = _COND_VAR_RE.sub(_sub, condition)

    # Split by OR (lower precedence) — any OR-group being true makes the whole true
    for or_part in re.split(r'\bOR\b', cond, flags=re.IGNORECASE):
        # Split by AND — all AND-clauses must be true
        if all(_eval_clause(c.strip()) for c in re.split(r'\bAND\b', or_part, flags=re.IGNORECASE)):
            return True
    return False
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestEvalCondition -v
```
Expected: 11 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/voicelines.py tests/test_voicelines_template.py
git commit -m "feat: add _eval_condition() with AND/OR and variable substitution (#96)"
```

---

## Task 3: `_evaluate_conditionals()` — inline WHEN...THEN expansion

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Modify: `tests/test_voicelines_template.py`

- [ ] **Step 1: Write failing tests**

```python
class TestEvaluateConditionals:
    def test_condition_true_inserts_text(self):
        result = _evaluate_conditionals(
            'Hello. WHEN {terra} IS TRUE THEN "Terraformable.";',
            {"terra": "Terraformable"},
        )
        assert result == "Hello. Terraformable."

    def test_condition_false_removes_block(self):
        result = _evaluate_conditionals(
            'Hello. WHEN {terra} IS TRUE THEN "Terraformable.";',
            {"terra": ""},
        )
        assert result == "Hello. "

    def test_condition_without_trailing_semicolon(self):
        result = _evaluate_conditionals(
            'WHEN {bio_count} > 0 THEN "Bio detected."',
            {"bio_count": "3"},
        )
        assert result == "Bio detected."

    def test_multiple_when_blocks(self):
        result = _evaluate_conditionals(
            'X. WHEN {terra} IS TRUE THEN "TF."; WHEN {bio_count} > 0 THEN "Bio.";',
            {"terra": "Terraformable", "bio_count": "2"},
        )
        assert result == "X. TF. Bio."

    def test_multiple_when_one_false(self):
        result = _evaluate_conditionals(
            'X. WHEN {terra} IS TRUE THEN "TF."; WHEN {bio_count} > 0 THEN "Bio.";',
            {"terra": "", "bio_count": "2"},
        )
        assert result == "X.  Bio."

    def test_then_text_may_contain_var_references(self):
        # {value} reference in THEN text is preserved for later format pass
        result = _evaluate_conditionals(
            'WHEN {value_raw} > 0 THEN "Worth {value}.";',
            {"value_raw": "500000", "value": "500 thousand"},
        )
        assert result == "Worth {value}."

    def test_no_when_blocks_unchanged(self):
        result = _evaluate_conditionals("Arrived in {system}.", {"system": "Sol"})
        assert result == "Arrived in {system}."

    def test_empty_string(self):
        assert _evaluate_conditionals("", {}) == ""
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestEvaluateConditionals -v
```
Expected: FAIL — `_evaluate_conditionals` not defined.

- [ ] **Step 3: Add `_evaluate_conditionals()` and the regex to `voicelines.py`**

```python
# Regex to find WHEN ... THEN "..." ; blocks in a template string.
# Group 1: condition text (everything between WHEN and THEN)
# Group 2: the THEN text (inside the double quotes, supports \" escapes)
_WHEN_RE = re.compile(
    r'WHEN\s+(.+?)\s+THEN\s+"((?:[^"\\]|\\.)*)"\s*;?',
    re.DOTALL,
)


def _evaluate_conditionals(template: str, kwargs: dict) -> str:
    """Replace all WHEN...THEN "text"; blocks with their resolved text or ''.

    The THEN text is returned as-is (with {variable} references intact)
    so the final format_map() pass can fill them in.
    """
    def _replace(m: re.Match) -> str:
        condition = m.group(1)
        then_text = m.group(2).replace('\\"', '"')
        return then_text if _eval_condition(condition, kwargs) else ""

    return _WHEN_RE.sub(_replace, template)
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestEvaluateConditionals -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/voicelines.py tests/test_voicelines_template.py
git commit -m "feat: add _evaluate_conditionals() — inline WHEN...THEN template blocks (#96)"
```

---

## Task 4: `_expand_includes()` — fragment expansion

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Modify: `tests/test_voicelines_template.py`

- [ ] **Step 1: Write failing tests**

```python
class TestExpandIncludes:
    def test_explicit_include_replaced_with_fragment(self):
        lines_map = {"_greeting": ["Hello, {commander}."]}
        result = _expand_includes("{include:_greeting} Arrived.", lines_map, {"commander": "Kernic"})
        assert result == "Hello, {commander}. Arrived."

    def test_shorthand_include_replaced_with_fragment(self):
        lines_map = {"_greeting": ["Hello, {commander}."]}
        result = _expand_includes("{_greeting} Arrived.", lines_map, {})
        assert result == "Hello, {commander}. Arrived."

    def test_shorthand_and_explicit_equivalent(self):
        lines_map = {"_frag": ["X"]}
        assert _expand_includes("{include:_frag}", lines_map, {}) == \
               _expand_includes("{_frag}", lines_map, {})

    def test_missing_explicit_include_replaced_with_empty(self):
        result = _expand_includes("{include:_missing} Text.", {}, {})
        assert result == " Text."

    def test_missing_shorthand_replaced_with_empty(self):
        result = _expand_includes("{_missing} Text.", {}, {})
        assert result == " Text."

    def test_no_include_unchanged(self):
        result = _expand_includes("Arrived in {system}.", {}, {"system": "Sol"})
        assert result == "Arrived in {system}."

    def test_include_not_starting_with_underscore_treated_as_missing(self):
        # Only _ prefix keys are fragments (explicit syntax)
        lines_map = {"greeting": ["Hello."]}
        result = _expand_includes("{include:greeting} Text.", lines_map, {})
        assert result == " Text."

    def test_circular_include_resolved_as_empty(self):
        lines_map = {"_loop": ["{include:_loop}"]}
        result = _expand_includes("{include:_loop}", lines_map, {})
        assert result == ""

    def test_circular_shorthand_resolved_as_empty(self):
        lines_map = {"_loop": ["{_loop}"]}
        result = _expand_includes("{_loop}", lines_map, {})
        assert result == ""

    def test_nested_include(self):
        lines_map = {
            "_b": ["world"],
            "_a": ["hello {include:_b}"],
        }
        result = _expand_includes("{include:_a}", lines_map, {})
        assert result == "hello world"

    def test_nested_shorthand(self):
        lines_map = {
            "_b": ["world"],
            "_a": ["hello {_b}"],
        }
        result = _expand_includes("{_a}", lines_map, {})
        assert result == "hello world"

    def test_multiple_includes_same_line(self):
        lines_map = {"_x": ["X"], "_y": ["Y"]}
        result = _expand_includes("{include:_x} and {_y}", lines_map, {})
        assert result == "X and Y"

    def test_hyphenated_key_via_explicit_syntax(self):
        # Hyphens only supported in explicit {include:_key-name} form
        lines_map = {"_my-frag": ["Hyphenated."]}
        result = _expand_includes("{include:_my-frag}", lines_map, {})
        assert result == "Hyphenated."
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestExpandIncludes -v
```
Expected: FAIL — `_expand_includes` not defined.

- [ ] **Step 3: Add `_expand_includes()` and include regex to `voicelines.py`**

```python
import logging as _logging
_log = _logging.getLogger("nova.voicelines")

# Matches both syntaxes:
#   {include:_KeyName}  — explicit; key may contain hyphens ([\w-]+)
#   {_KeyName}          — shorthand; word characters only (\w+)
# Group 1: explicit key, Group 2: shorthand key
_INCLUDE_RE = re.compile(r'\{include:(_[\w-]+)\}|\{(_\w+)\}')

_INCLUDE_MAX_DEPTH = 5


def _expand_includes(template: str, lines_map: dict, kwargs: dict, depth: int = 0) -> str:
    """Expand include fragments in *template*.

    Supports two syntaxes:
      {include:_KeyName}  — explicit; key may contain hyphens
      {_KeyName}          — shorthand; word characters only

    Looks up each fragment key in *lines_map*, picks a random line, and
    substitutes it inline. Recursively expands nested includes.

    Cycle detection: depth > _INCLUDE_MAX_DEPTH → warning + expand to ''.
    Missing or non-_ keys → warning + expand to ''.
    """
    if depth > _INCLUDE_MAX_DEPTH:
        _log.warning("voicelines: include depth exceeded (circular include?)")
        return _INCLUDE_RE.sub("", template)

    def _replace(m: re.Match) -> str:
        key = m.group(1) or m.group(2)   # explicit group 1, shorthand group 2
        variants = lines_map.get(key)
        if not variants:
            _log.warning("voicelines: include key %r not found", key)
            return ""
        fragment = random.choice(variants)
        return _expand_includes(fragment, lines_map, kwargs, depth + 1)

    return _INCLUDE_RE.sub(_replace, template)
```

- [ ] **Step 4: Run tests**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestExpandIncludes -v
```
Expected: 7 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/voicelines.py tests/test_voicelines_template.py
git commit -m "feat: add _expand_includes() — {include:_KeyName} fragment expansion (#96)"
```

---

## Task 5: Wire everything into `pick()` and update `_load()` for fragment keys

**Files:**
- Modify: `ed_monitor/voicelines.py`
- Modify: `tests/test_voicelines_template.py`

- [ ] **Step 1: Write failing integration tests**

```python
class TestPickIntegration:
    """Integration tests: pick() with includes and conditionals end-to-end."""

    def setup_method(self):
        import ed_monitor.voicelines as vl
        vl._CACHE.clear()
        # Override config dir so no real user files interfere
        vl._CONFIG_DIR = Path("/nonexistent_test_dir")

    def teardown_method(self):
        import ed_monitor.voicelines as vl
        vl._CACHE.clear()
        vl._CONFIG_DIR = None

    def test_pick_with_conditional_true(self, tmp_path, monkeypatch):
        import ed_monitor.voicelines as vl
        vl._CONFIG_DIR = tmp_path
        vl._CACHE["en"] = {
            "MyEvent": ['Scanned. WHEN {terra} IS TRUE THEN "Terraformable.";'],
        }
        result = vl.pick("MyEvent", lang="en", terra="Terraformable")
        assert result == "Scanned. Terraformable."

    def test_pick_with_conditional_false(self, tmp_path, monkeypatch):
        import ed_monitor.voicelines as vl
        vl._CONFIG_DIR = tmp_path
        vl._CACHE["en"] = {
            "MyEvent": ['Scanned. WHEN {terra} IS TRUE THEN "Terraformable.";'],
        }
        result = vl.pick("MyEvent", lang="en", terra="")
        assert result == "Scanned. "

    def test_pick_with_include(self, tmp_path):
        import ed_monitor.voicelines as vl
        vl._CONFIG_DIR = tmp_path
        vl._CACHE["en"] = {
            "_hull_info": ["{hull} hull."],
            "MyEvent":    ["Status: {include:_hull_info}"],
        }
        result = vl.pick("MyEvent", lang="en", hull="80 percent")
        assert result == "Status: 80 percent hull."

    def test_pick_include_with_variable_in_fragment(self, tmp_path):
        import ed_monitor.voicelines as vl
        vl._CONFIG_DIR = tmp_path
        vl._CACHE["en"] = {
            "_summary": ["{system} has {bio_count} bio signals."],
            "FSSAllBodiesFound": ["Scan complete. {include:_summary}"],
        }
        result = vl.pick("FSSAllBodiesFound", lang="en", system="Colonia", bio_count="3")
        assert result == "Scan complete. Colonia has 3 bio signals."

    def test_fragment_keys_not_pickable_directly(self, tmp_path):
        import ed_monitor.voicelines as vl
        vl._CONFIG_DIR = tmp_path
        vl._CACHE["en"] = {"_greeting": ["Hello."]}
        assert vl.pick("_greeting", lang="en") is None

    def test_pick_unknown_variable_returns_template_not_crash(self, tmp_path):
        import ed_monitor.voicelines as vl
        vl._CONFIG_DIR = tmp_path
        vl._CACHE["en"] = {"MyEvent": ["Value: {value_mapped}."]}
        # value_mapped not in kwargs — SafeDict returns ""
        result = vl.pick("MyEvent", lang="en")
        assert result == "Value: ."
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3.12 -m pytest tests/test_voicelines_template.py::TestPickIntegration -v
```
Expected: FAIL — `pick()` doesn't run the render pipeline yet; unknown vars crash.

- [ ] **Step 3: Update `pick()` to use the render pipeline**

Replace the current `pick()` function body:

```python
def pick(key: str, lang: str = "en", **kwargs) -> Optional[str]:
    """Return a random formatted voiceline for *key* in *lang*, or None.

    Render pipeline (in order):
      1. _expand_includes — expands {include:_KeyName} fragments
      2. _evaluate_conditionals — replaces WHEN...THEN blocks
      3. format_map(_SafeDict) — fills {variable} references

    Fallback logic:
      - Key in lang map → use it; empty list → None.
      - Key absent from lang map and lang != "en" → try English built-in.
      - Key absent entirely → None.
    Fragment keys (starting with '_') are excluded from direct lookup.
    """
    if key.startswith("_"):
        return None   # fragment keys are not directly speakable

    lines_map = _load(lang)

    if key in lines_map:
        variants = lines_map[key]
    elif lang != "en":
        variants = _load("en").get(key)
    else:
        variants = None

    if not variants:
        return None

    template = random.choice(variants)
    try:
        template = _expand_includes(template, lines_map, kwargs)
        template = _evaluate_conditionals(template, kwargs)
        return template.format_map(_SafeDict(kwargs))
    except Exception:
        return template
```

- [ ] **Step 4: Update `_load()` to accept `_` prefix keys as fragments**

In `_load()`, the current code silently loads all keys into `lines`. Fragment keys (`_*`) are already loaded alongside regular keys — no structural change needed. The `pick()` guard (`if key.startswith("_"): return None`) and `_expand_includes()` looking up `lines_map` by key handles everything.

Verify fragment keys flow through correctly by checking the `_load()` logic — no changes needed.

- [ ] **Step 5: Run tests**

```bash
python3.12 -m pytest tests/test_voicelines_template.py -v
```
Expected: all pass.

- [ ] **Step 6: Run full test suite**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add ed_monitor/voicelines.py tests/test_voicelines_template.py
git commit -m "feat: wire include/conditional render pipeline into pick(); guard fragment keys (#96)"
```

---

## Task 6: Update built-in TOML comments and user README

**Files:**
- Modify: `ed_monitor/voicelines/en.default.toml`
- Modify: `ed_monitor/voicelines.py` (the `ensure_user_files()` README text)

- [ ] **Step 1: Add template engine authoring docs to `en.default.toml` header**

In the header comment block (after the existing variable groups), add:

```toml
# ── Template Engine Features ──────────────────────────────────────────────────
#
# INCLUDES — reusable phrase fragments
#   Define a fragment key (must start with _) in your user en.toml file:
#
#     [_ship_status]
#     add = ["{ship_name} — hull {hull}, fuel {fuel}."]
#
#   Include it in any line — two equivalent syntaxes:
#
#     [FSDJump]
#     add = ["Arrived in {system}. {include:_ship_status}"]   # explicit
#     add = ["Arrived in {system}. {_ship_status}"]           # shorthand
#
#   The shorthand {_KeyName} works for keys with letters, digits and underscores.
#   Use {include:_key-name} (explicit) for keys that contain hyphens.
#   Circular includes are detected (depth > 5) and expand to empty string.
#   Missing keys expand to empty string.
#
# CONDITIONALS — inline WHEN...THEN blocks
#   Use WHEN condition THEN "text"; inside any line. The block is replaced
#   with "text" when the condition is true, or with "" when false:
#
#     [Scan_Notable]
#     add = ['Scanned {body_short}. WHEN {value_raw} > 500000 THEN "Worth {value}."; WHEN {bio_count} > 0 THEN "{bio_count} bio signals.";']
#
#   Supported operators:
#     IS TRUE / IS FALSE / IS NOT TRUE
#     == != < > <= >=
#     AND  OR
#
#   Truthy: non-empty value that is not "0" or "false" (case-insensitive).
#   Flag variables ({terra}, {landable}, {first_disc} etc.) are "" when absent,
#   non-empty when present — so "WHEN {terra} IS TRUE" works naturally.
```

- [ ] **Step 2: Update the README in `ensure_user_files()`**

Extend the README text to document includes and conditionals. Add a new `## Template Engine` section after the existing `## Rules` section:

```python
readme_text += (
    "\n## Template Engine\n\n"
    "### Includes\n\n"
    "Define a reusable fragment (key must start with `_`) in your user file:\n\n"
    "    [_ship_status]\n"
    "    add = [\"{ship_name} — hull {hull}, fuel {fuel}.\"]\n\n"
    "Use `{include:_ship_status}` anywhere in a line to insert it.\n\n"
    "### Conditionals\n\n"
    "Inline `WHEN condition THEN \"text\";` blocks in any line:\n\n"
    "    [Scan_Notable]\n"
    "    add = ['Scanned {body_short}. WHEN {value_raw} > 500000 THEN \"Worth {value}.\";']\n\n"
    "Condition is true → 'text' is included. False → replaced with ''.\n\n"
    "Supported operators: `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`\n"
)
```

- [ ] **Step 3: Run full test suite**

```bash
python3.12 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add ed_monitor/voicelines/en.default.toml ed_monitor/voicelines.py
git commit -m "docs: add include/conditional authoring guide to voiceline TOML header and README (#96)"
```

---

## Task 7: Bump version and release

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version**

Change `version = "1.34.0"` → `version = "1.35.0"`

- [ ] **Step 2: Run full test suite**

```bash
python3.12 -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 3: Commit, tag, push, release**

```bash
git add pyproject.toml
git commit -m "chore: bump to v1.35.0 — voiceline template engine"
git tag v1.35.0
git push origin feature/issue-96 --tags
```

Create GitHub release with the changelog below.

**Release notes:**

```
## Changelog

### Added — Voiceline Template Engine: Includes & Conditionals (#96)

**Includes** — define reusable phrase fragments in your user voiceline file:

    [_ship_status]
    add = ["{ship_name} — hull {hull}, fuel {fuel}."]

    [FSDJump]
    add = ["Arrived in {system}. {include:_ship_status}"]

Fragment keys must start with `_`. They are never spoken directly — only via `{include:_KeyName}`.
Missing keys expand to `""`. Circular includes are detected and capped at depth 5.

**Conditionals** — inline `WHEN condition THEN "text";` blocks:

    [Scan_Notable]
    add = ['Scanned {body_short}. WHEN {value_raw} > 500000 THEN "Worth {value}."; WHEN {bio_count} > 0 THEN "{bio_count} bio signals.";']

Supported operators: `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`

Truthy check: a value is true when it is non-empty and not `"0"` or `"false"`.
Flag variables like `{terra}`, `{landable}`, `{first_disc}` are `""` when absent, so `IS TRUE` works naturally.

**Safe variable substitution:** Unknown `{variable}` names in templates now expand to `""` instead of crashing.

See `config/voicelines/README.md` and the `default/en.default.toml` header comments for full authoring guide.
```

---

## Exclusions (from issue, explicitly out of scope)

- `[trigger]` sections (vague spec, no examples — tracked separately)
- `{if:var}...{endif}` block-level branching (out of scope per issue)
- Multi-level nesting > 5 (enforced by depth limit)
- New built-in variables (`star_is_scoopable` etc.) — existing variable set is unchanged
