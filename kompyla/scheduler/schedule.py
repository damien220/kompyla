"""Persistent schedule config stored inside kompyla.yaml."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from kompyla.storage.layout import KBLayout


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schedule(layout: KBLayout) -> dict:
    """Return the 'schedule' sub-dict from kompyla.yaml (with defaults)."""
    if not layout.kb_config.exists():
        return _defaults()
    data = yaml.safe_load(layout.kb_config.read_text()) or {}
    sched = data.get("schedule", {})
    return {**_defaults(), **sched}


def save_schedule(layout: KBLayout, sched: dict) -> None:
    """Merge `sched` into kompyla.yaml under the 'schedule' key."""
    data: dict = {}
    if layout.kb_config.exists():
        data = yaml.safe_load(layout.kb_config.read_text()) or {}
    data["schedule"] = sched
    layout.kb_config.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))


def is_due(sched: dict) -> bool:
    """Return True if the schedule is enabled and interval has elapsed."""
    if not sched.get("enabled"):
        return False
    last = sched.get("last_run_at")
    if not last:
        return True
    interval_seconds = sched.get("interval_hours", 24) * 3600
    last_dt = datetime.fromisoformat(last)
    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
    return elapsed >= interval_seconds


def mark_ran(layout: KBLayout, sched: dict) -> None:
    """Update last_run_at to now and persist."""
    sched["last_run_at"] = _now_iso()
    save_schedule(layout, sched)


def _defaults() -> dict:
    return {"enabled": False, "interval_hours": 24, "last_run_at": None}
