"""Apply accumulated feedback signals to wiki page confidence scores."""

from __future__ import annotations

from kompyla.feedback.store import FeedbackStore
from kompyla.storage.index import MetaIndex
from kompyla.storage.layout import KBLayout

# How much each signal type nudges the confidence
_DELTA = {
    "excellent": +0.10,
    "wrong":     -0.20,
    "outdated":  -0.10,
    "unclear":   -0.05,
}


def apply_feedback(
    layout: KBLayout,
    index: MetaIndex,
    feedback_store: FeedbackStore,
) -> dict:
    """Adjust confidence scores based on feedback signals.

    Returns a summary: {"updated": int, "skipped": int, "flagged_for_research": list[str]}
    """
    pages = {p["title"]: p for p in index.all_pages()}
    updated = 0
    skipped = 0
    flagged: list[str] = []

    all_fb = feedback_store.all_feedback()
    by_page: dict[str, list] = {}
    for row in all_fb:
        by_page.setdefault(row["page_title"], []).append(row)

    for title, entries in by_page.items():
        if title not in pages:
            skipped += 1
            continue

        page = pages[title]
        current_conf: float = page["confidence"] or 0.5

        # Aggregate delta from all feedback entries
        delta = sum(_DELTA.get(e["signal"], 0.0) for e in entries)
        new_conf = max(0.0, min(1.0, current_conf + delta))

        if abs(new_conf - current_conf) < 0.001:
            continue

        # Write back via upsert
        import json
        from pathlib import Path as _Path
        index._conn.execute(
            "UPDATE pages SET confidence=?, updated_at=datetime('now') WHERE title=?",
            (round(new_conf, 3), title),
        )
        index._conn.commit()
        updated += 1

        # Flag low-confidence pages for re-research
        if new_conf < 0.5:
            flagged.append(title)

    return {"updated": updated, "skipped": skipped, "flagged_for_research": flagged}
