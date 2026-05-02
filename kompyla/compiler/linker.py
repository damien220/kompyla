from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..storage.index import MetaIndex
from ..storage.layout import KBLayout


def rebuild_master_index(layout: KBLayout, index: MetaIndex) -> None:
    """Rewrite index/index.md from the current state of the metadata index."""
    pages = index.all_pages()
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# {layout.root.name} — Knowledge Base Index\n",
        f"*{len(pages)} page(s) · last updated {updated}*\n",
    ]

    by_type: dict[str, list] = {}
    for page in pages:
        ptype = page["page_type"] or "misc"
        by_type.setdefault(ptype, []).append(page)

    for ptype in sorted(by_type):
        lines.append(f"\n## {ptype.replace('_', ' ').title()}\n")
        for page in sorted(by_type[ptype], key=lambda r: r["title"].lower()):
            rel = Path(page["wiki_path"]).name
            conf = page["confidence"]
            lines.append(f"- [[{page['title']}]] (`wiki/{rel}`) — confidence {conf:.0%}")

    layout.index_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
