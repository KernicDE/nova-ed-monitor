# NOVA v2.0.0 — Senior Architect Audit

Issue: [#101](https://github.com/KernicDE/nova-ed-monitor/issues/101). Baseline: v1.36.0, 171 tests passing.

This document is the Phase-1 deliverable — a concrete punch list of every finding, mapped to the phase that ships the fix. Each commit during phases 2-5 points back to an item here.

---

## Hot paths (Phase 2)

| ID | File | Item | Plan |
|----|------|------|------|
| P-1 | state.py · `AppState.upsert_body` | Inserts into a sorted list with `bisect` but then calls `_rebuild_body_index` (full reindex) for every new body. | Patch the two indices in place — shift values ≥ `pos` by +1, add the new entry. O(N) → O(K) where K = bodies with `id ≥ pos`. |
| P-2 | journal.py · `_rebuild_body_db` / `_process_backlog` / `_init_scan` | Journal replay fires `state.upsert_body` thousands of times on startup (combines with P-1 to form O(N²)). | P-1 alone fixes the worst case. Additionally: batch re-build the index once at the end of replay instead of incrementally. |
| P-3 | journal.py · `_save_current_bodies` / `_save_bodies_only` | Writes the entire bodies list after every single scan event (5 event kinds). | Debounce body writes: gather dirty flag, flush on heartbeat (≥ 1 s since last change). Keep immediate flush on system-changing events. |
| P-4 | status.py · `_check_bio_distance` | Nested haversine loop over comp × foot samples per bio scan; runs at 5 Hz on foot. | Precompute per-sample lat/lon radians once; use flat lookups. Early-exit when `sc.complete` or `sc.samples == 0`. Cache `on_surface` outside the scan loop. |
| P-5 | ui/app.py · `_refresh_all._snapshot` | Deep-copies every tick even when fingerprint matches. | Compute fingerprint *before* cloning collections; if unchanged, only FooterBar needs the (much smaller) cheap fields. |
| P-6 | ui/panels.py · `_render_overview` / `_render_system_map` | Per-body `_body_value` called 2-3× per render; notable filter + sort re-run per tick. | Cache derived body values + notable list keyed on `(system, bodies_version, notable_value_threshold)`. |
| P-7 | ui/panels.py · `_render_bio` | Three O(N) scans of `s.bodies` per render to categorise scanned/prescan/predicted. | Single-pass categorisation; reuse cached short-name. |
| P-8 | ui/panels.py · `SituationalPanel.update` | Allocates a `tuple(... for sc in snap.bio_scans)` every tick for change detection. | Use `(bio_scans_version, len)` — expose a counter in state. |
| P-9 | tts.py module-level logger | `FileHandler(mode='w')` opens unconditionally on import, truncates `/tmp/nova-audio-debug.log` every run. | Lazy-initialise only when `debug_log = true`; `NullHandler` by default. |
| P-10 | journal.py · `_fetch_route_bodies_live` | Sequential `/bodies` calls with `sleep(0.5)` between each — 30-hop route blocks for 15 s. | Add a cancellation token wired to the current route; early-exit when route changes. Limit to max 20 fresh fetches per route update (oldest-first). |

---

## Resilience & edge cases (Phase 3)

| ID | File | Item | Plan |
|----|------|------|------|
| R-1 | events.py · `ApproachBody` handler | Spawns `threading.Timer` for repeat G-warnings, never cancelled on `LeaveBody`. | Track timers on `state`; cancel on LeaveBody / SupercruiseEntry / jump. |
| R-2 | db.py · `_migrate_stats_v2` / `_migrate_bio_scans_v2` | `except Exception: pass` — sentinel never set on failure, state left half-migrated. | Wrap in explicit transaction; log failure with specific exception; only write sentinel on success; keep retry semantics. |
| R-3 | db.py · `save_bio_scans` | `DELETE … WHERE system=…` + `executemany` are two statements, one commit. On constraint error the system loses every scan. | Wrap both inside an explicit `BEGIN IMMEDIATE`; on error rollback. |
| R-4 | status.py · `_check_bio_distance` (default radius `3_389_500`) vs events.py · `ScanOrganic Log` (default `3_000_000`) | Two conflicting fallbacks for unknown body radius produce off-by-13% distance. | Single constant `_DEFAULT_BODY_RADIUS_M = 3_389_500` in state.py, both sites import it. |
| R-5 | journal.py · `_follow` exception path | On handler exception, offset is still flushed — poison events silently skipped forever. | Don't advance past unknown errors; log traceback, advance only after `_CRITICAL_EVENTS` or a second identical failure. |
| R-6 | twitch.py | `sock.send()` assumes full write; no partial-send handling. | Use `sendall()`. |
| R-7 | youtube.py | Regex scraping silently fails — user has no visibility when YouTube breaks integration. | Surface a single "YouTube scraping failed — integration may need update" event when regex returns no match for a channel known to be live. |
| R-8 | config.py · `load()` | Rewrites `config.toml` during load (appending new sections); trips config_watcher → double reload. | Debounce config_watcher against our own writes using a 3 s "quiet window" after every `config.load()`/`config.save()`. |
| R-9 | journal.py · `_fetch_route_edsm_live` / `_fetch_route_bodies_live` | Lock `acquire(blocking=False)` means new trigger during in-flight fetch silently drops. | Use an `Event` + "dirty route version" counter; worker re-runs until no new version seen. |
| R-10 | Silent `except Exception: pass` (~60 sites across journal/events/status/edsm) | Violates issue #101 "no silent failures" constraint. | Pass 1: classify each — legitimate (skip-one-bad-row) vs needs logging. Pass 2: log via module logger at WARNING, keep control flow. |
| R-11 | events.py · `MassLocked` / `Scanned` / chat channel `_` fallback | Event body schema assumed without type check at handler boundaries. | The generic helpers `_s/_f/_u/_b/_loc` already guard most reads. Add one schema guard at `handle()` entry: `ev` must be dict with str "event". |
| R-12 | spansh.py · `_fetch_carriers` | No HTTP timeout on `urlopen` retry path is fine; but no schema validation on response. | Reject records missing `system_name` or with negative coords; skip not raise. |
| R-13 | HTTP user-agent discipline | Mixed UA strings across edsm/edsm_dumps/neutron/spansh. | One `_UA` constant in a new `ed_monitor/_http.py` helper; all clients import it. |
| R-14 | tts.py · dedup window cleanup only when queue idle | If always busy, old keys accumulate in `_recent_messages`. | Move cleanup to a time-check before queue poll, not only after. |

---

## Dead code / bloat (Phase 4)

| ID | Location | Action |
|----|----------|--------|
| D-1 | panels.py · `BioPanel`, `MaterialsPanel`, `MissionsPanel`, `EngineersPanel` | Delete — never instantiated. |
| D-2 | db.py · `Database.prune_events` | Keep signature + add a scheduled periodic call at startup (retain events for 180 days, documented default) rather than delete. Wire it up at startup behind a config flag `prune_events_days` (0 = disabled by default so existing behaviour is preserved). |
| D-3 | events.py · `natural_key` | Delete — unused. |
| D-4 | panels.py · `_ENGINEER_STATIC` | Remove duplicate "Yarden Bond" entry. |
| D-5 | edsm.py · `_now_hms` | Inline the one call site. |
| D-6 | events.py · `_BIO_SPECIES_VALUES_LC` | Keep (used by fallback path); add one-line comment explaining why we duplicate. |
| D-7 | ui/app.py CSS | Remove the duplicate `Screen.combat-mode SystemPanel { border-title-color }` rule (already covered by the combined rule above). |
| D-8 | voicelines.py · `_migrate_user_voiceline_file` | Gate behind `.migrated_template_v1` sentinel so it only runs once. |
| D-9 | events.py · hard-coded event-name lists (`_BODY_EVENTS`, `_CRITICAL_EVENTS` duplication with journal.py) | Move constants to a shared `events_catalog.py`. |
| D-10 | screenshots.py · `seen` set grows unbounded | Cap to last 1000 entries (LRU). |

---

## Test coverage gaps (Phase 5)

New tests to add:
1. `tests/test_journal_follow.py` — handler exception does not advance past critical events; offset resume round-trip; commander switch clears state.
2. `tests/test_status_distance.py` — haversine correctness, default radius constant, supercruise suppression, COMP-vs-foot priority.
3. `tests/test_upsert_body_perf.py` — inserting 1 000 bodies in random order completes < 100 ms; indices stay consistent.
4. `tests/test_edsm.py` — mock httpx to test `_merge_bodies` dedup, `_fmt_err` paths.
5. `tests/test_spansh.py` — malformed responses are skipped, cache TTL, sort-by-distance.
6. `tests/test_tts_dedup.py` — dedup window, backend reset on fail, path escaping.
7. `tests/test_config_hot_reload.py` — quiet-window debounce; verifies self-write doesn't re-trigger.
8. `tests/test_approach_body_timer.py` — repeat G-warnings cancel on LeaveBody.
9. `tests/test_db_atomic.py` — `save_bio_scans` rolls back on failure (preserves existing rows).
10. `tests/test_http_ua.py` — shared UA used by all clients.

Target: add ~60 tests, raising the overall count to ~230.

---

## Versioning & docs (Phase 6)

- Bump `pyproject.toml` to `2.0.0`.
- Update `README.md`, `docs/Installation.md`, `docs/Settings.md`, `docs/Usage.md` with any externally-visible changes (prune-events flag, TTS log file gated on debug_log, cancellable route fetches).
- Update `CLAUDE.md` with new invariants (index-in-place upsert, body save debounce, shared HTTP helper, migration sentinels).
- Release notes in the PR body (*not* in a docs file).

---

## Ground rules

1. **Every commit keeps the test suite green.** Run `python3.12 -m pytest tests/ -q` after each commit.
2. **No feature creep.** Every change traces back to an ID in this document.
3. **No silent failures introduced.** Replacements for `except Exception: pass` must log at WARNING with the module logger, or convert to a specific exception class.
4. **Atomic commit groups.** One ID per commit (small fixes may be grouped by theme if they share a file).
