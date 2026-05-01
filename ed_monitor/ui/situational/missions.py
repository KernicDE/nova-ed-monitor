from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Group, RenderableType
from rich.text import Text

from ...state import AppState, MissionInfo
from .. import palette as P
from ..panels import (
    _data_table, _section_header, _fmt_cr_compact,
)


# ── Type colour mapping ───────────────────────────────────────────────────────

_TYPE_STYLE: dict[str, str] = {
    "Massacre":      P.HUD_CRIT,
    "Assassination": P.HUD_CRIT,
    "Delivery":      P.AMBER,
    "Mining":        P.AMBER,
    "Courier":       "white",
    "Passengers":    P.PURPLE,
    "Salvage":       P.LABEL,
    "Collect":       P.LABEL,
    "Scan":          P.LABEL,
    "Altruism":      P.LABEL,
    "On-foot":       P.LABEL,
    "Hack":          P.LABEL,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mission_time_remaining(expiry: str) -> str:
    if not expiry:
        return ""
    try:
        # ED timestamps: "2025-03-08T12:34:56Z" or without Z
        ts = expiry.rstrip("Z")
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        secs  = int(delta.total_seconds())
        if secs < 0:
            return "Expired"
        days  = secs // 86400
        hours = (secs % 86400) // 3600
        mins  = (secs % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    except Exception:
        return ""


def _expiry_secs(expiry: str) -> float:
    """Seconds until expiry; inf if no expiry or unparseable."""
    if not expiry:
        return float("inf")
    try:
        ts = expiry.rstrip("Z")
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return float("inf")


def _time_style(remaining: str) -> str:
    if remaining == "Expired":
        return P.HUD_CRIT
    if remaining and "d" not in remaining and "h" not in remaining:
        return P.HUD_WARN   # minutes only → < 1 h
    return P.LABEL


# ── Massacre section ──────────────────────────────────────────────────────────

def _render_massacre_section(s: AppState, parts: list, mp: dict) -> None:
    # Group by faction — keep per-mission data for milestone display
    fac_kills: dict = {}
    for mk in s.massacre_kills.values():
        fac = mk["faction"]
        if fac not in fac_kills:
            fac_kills[fac] = []
        fac_kills[fac].append({"needed": mk["needed"], "done": mk["done"]})

    parts.append(_section_header("MASSACRE PROGRESS", mp["h1"], mp["bg"]))

    for fac, mlist in fac_kills.items():
        # Each kill counts for ALL stacked missions simultaneously.
        # The highest-needed mission caps last, so its done = actual kill count.
        kills_done = max(m["done"] for m in mlist)
        max_needed = max(m["needed"] for m in mlist)
        stacked    = len(mlist)
        filled     = int(10 * kills_done / max_needed) if max_needed > 0 else 0
        bar        = "█" * filled + "░" * (10 - filled)

        row = Text()
        row.append(f"  [{bar}] ", style=P.HUD_CRIT)
        row.append(f"{kills_done}/{max_needed}", style="white")
        if stacked > 1:
            row.append(f" ×{stacked}", style=P.HUD_WARN)
        row.append(f"  {fac}", style=P.LABEL)

        if stacked > 1:
            # Show sorted thresholds so player sees exactly when each mission completes
            thresholds = sorted(set(m["needed"] for m in mlist))
            row.append("  ")
            for t in thresholds:
                if kills_done >= t:
                    row.append(f"{t}✓ ", style="dim green")
                else:
                    row.append(f"→{t} ", style=P.LABEL)

        row.append("\n")
        parts.append(row)


# ── Main renderer ─────────────────────────────────────────────────────────────

def _render_missions(s: AppState, scroll: int = 0, mp: dict | None = None) -> RenderableType:
    mp = mp or P.mp("ship")
    if not s.missions:
        t = Text()
        t.append("No active missions.", style=P.LABEL)
        return t

    parts: list[RenderableType] = []

    if s.massacre_kills:
        _render_massacre_section(s, parts, mp)

    # Sort all missions by expiry (soonest first), then apply scroll
    sorted_all = sorted(s.missions, key=lambda m: _expiry_secs(m.expiry))
    effective_scroll = min(scroll, max(0, len(sorted_all) - 1))
    visible = sorted_all[effective_scroll:]

    # Group visible missions by destination
    groups: dict[str, list[MissionInfo]] = {}
    for m in visible:
        dest = m.destination or "—"
        groups.setdefault(dest, []).append(m)

    # Render each destination group
    for dest, missions in groups.items():
        cargo_total = sum(m.cargo_count for m in missions if m.cargo_count)
        cargo_label = next((m.cargo_type for m in missions if m.cargo_type), "")
        reward_total = sum(m.reward for m in missions)
        count = len(missions)

        # Destination header
        hdr = Text()
        hdr.append(f"  {dest}", style="white")
        if count > 1:
            hdr.append(f"  ×{count}", style=P.HUD_WARN)
        if cargo_total and cargo_label:
            hdr.append(f"  {cargo_total} t {cargo_label}", style=P.AMBER)
        if reward_total:
            hdr.append(f"  {_fmt_cr_compact(reward_total)} Cr", style=P.LABEL)
        parts.append(hdr)

        # Mission rows
        tbl = _data_table(mp["h2"])
        tbl.add_column("Type",    width=12, no_wrap=True)
        tbl.add_column("Mission", no_wrap=True)
        tbl.add_column("Time",    width=9, justify="right")
        tbl.add_column("Reward",  width=7, justify="right")

        for m in missions:
            mtype      = m.mission_type or "—"
            type_style = _TYPE_STYLE.get(mtype, P.LABEL)
            remaining  = _mission_time_remaining(m.expiry)

            name_t = Text(m.name or "—", style="white", no_wrap=True)
            if m.wing:
                name_t.append(" [W]", style=P.GOLD)
            if m.influence in ("++", "+++"):
                name_t.append(f" {m.influence}", style=P.GOLD)

            tbl.add_row(
                Text(mtype, style=type_style),
                name_t,
                Text(remaining, style=f"bold {_time_style(remaining)}"),
                Text(_fmt_cr_compact(m.reward) if m.reward else "—", style=P.LABEL),
            )

        parts.append(tbl)

    return Group(*parts)
