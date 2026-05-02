"""Bundle the whole KB into a single concatenated markdown file."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..storage.index import MetaIndex
from ..storage.layout import KBLayout


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip() if len(parts) >= 3 else text


def bundle_kb_markdown(layout: KBLayout, index: MetaIndex) -> str:
    """Concatenate all wiki pages into one markdown document with a TOC."""
    pages = index.all_pages()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts = [
        f"# {layout.root.name} — Knowledge Base Bundle",
        f"\n*{len(pages)} page(s) · exported {ts}*\n",
        "\n## Table of Contents\n",
    ]
    for p in sorted(pages, key=lambda r: r["title"].lower()):
        slug = Path(p["wiki_path"]).stem
        parts.append(f"- [{p['title']}](#{slug})")

    parts.append("\n---\n")
    for p in sorted(pages, key=lambda r: r["title"].lower()):
        wpath = Path(p["wiki_path"])
        if not wpath.exists():
            continue
        body = _strip_frontmatter(wpath.read_text(encoding="utf-8"))
        slug = wpath.stem
        parts.append(f"\n<a id='{slug}'></a>\n")
        parts.append(body.rstrip())
        parts.append("\n\n---\n")

    return "\n".join(parts)
