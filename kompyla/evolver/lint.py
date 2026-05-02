"""Health check / lint pass over the wiki — deterministic checks plus a report."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..storage.index import MetaIndex
from ..storage.layout import KBLayout

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _extract_links(text: str) -> set[str]:
    return {m.group(1).strip() for m in _LINK_RE.finditer(text)}


def find_broken_links(layout: KBLayout, pages: list[sqlite3.Row]) -> list[tuple[str, str]]:
    """Return (source_page_title, target_link) pairs for unresolved [[wiki links]]."""
    existing = {p["title"].lower() for p in pages}
    broken: list[tuple[str, str]] = []
    for page in pages:
        wpath = Path(page["wiki_path"])
        if not wpath.exists():
            continue
        for link in _extract_links(wpath.read_text(encoding="utf-8")):
            if link.lower() not in existing:
                broken.append((page["title"], link))
    return broken


def find_stale_pages(pages: list[sqlite3.Row], days: int = 180) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return [p for p in pages if (p["updated_at"] or "") < cutoff]


def find_low_confidence_pages(pages: list[sqlite3.Row], threshold: float = 0.6) -> list[sqlite3.Row]:
    return [p for p in pages if (p["confidence"] or 0.0) < threshold]


def find_orphan_pages(layout: KBLayout, pages: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Pages that no other page references via [[...]]."""
    referenced: set[str] = set()
    for page in pages:
        wpath = Path(page["wiki_path"])
        if wpath.exists():
            for link in _extract_links(wpath.read_text(encoding="utf-8")):
                referenced.add(link.lower())
    return [p for p in pages if p["title"].lower() not in referenced]


def lint_kb(
    layout: KBLayout,
    index: MetaIndex,
    *,
    days_stale: int = 180,
    conf_threshold: float = 0.6,
) -> Path:
    """Run all checks and write a markdown report to outputs/. Returns the path."""
    pages = index.all_pages()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = [f"# Lint Report — {ts}\n", f"*Total pages:* {len(pages)}"]

    if not pages:
        parts.append("\nKB is empty.")
    else:
        broken = find_broken_links(layout, pages)
        low_conf = find_low_confidence_pages(pages, threshold=conf_threshold)
        stale = find_stale_pages(pages, days=days_stale)
        orphans = find_orphan_pages(layout, pages)

        parts.append(f"\n## Broken Links ({len(broken)})\n")
        if broken:
            for src, target in broken:
                parts.append(f"- **{src}** → `[[{target}]]`")
        else:
            parts.append("_No broken links._")

        parts.append(f"\n## Low-confidence Pages ({len(low_conf)}, < {conf_threshold:.0%})\n")
        if low_conf:
            for p in low_conf:
                parts.append(f"- **{p['title']}** — {(p['confidence'] or 0):.0%}")
        else:
            parts.append(f"_All pages above {conf_threshold:.0%}._")

        parts.append(f"\n## Stale Pages ({len(stale)}, > {days_stale} days)\n")
        if stale:
            for p in stale:
                date = (p["updated_at"] or "")[:10]
                parts.append(f"- **{p['title']}** — last updated {date or 'unknown'}")
        else:
            parts.append("_No stale pages._")

        parts.append(f"\n## Orphan Pages ({len(orphans)})\n")
        if orphans:
            for p in orphans:
                parts.append(f"- **{p['title']}**")
        else:
            parts.append("_No orphan pages._")

    layout.outputs.mkdir(parents=True, exist_ok=True)
    out = layout.outputs / f"lint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return out
