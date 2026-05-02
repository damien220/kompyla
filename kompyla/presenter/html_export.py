"""Markdown → HTML rendering for individual pages and the whole KB."""

from __future__ import annotations

from pathlib import Path

import markdown as md_lib

from ..storage.index import MetaIndex
from ..storage.layout import KBLayout

_MD_EXTENSIONS = ["extra", "toc", "tables", "fenced_code"]

_PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 760px;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
h1 {{ border-bottom: 2px solid #eee; padding-bottom: .3rem; }}
h2 {{ margin-top: 2rem; }}
code {{ background: #f4f4f4; padding: 0 .25rem; border-radius: 3px; }}
pre code {{ display: block; padding: .8rem; overflow-x: auto; }}
a {{ color: #2563eb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.meta {{ color: #666; font-size: .9rem; margin-bottom: 1.5rem; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip() if len(parts) >= 3 else text


def md_to_html(markdown_text: str) -> str:
    """Markdown body → HTML fragment (no <html>/<body> wrapper)."""
    return md_lib.markdown(markdown_text, extensions=_MD_EXTENSIONS)


def render_page_html(wiki_path: Path) -> str:
    """Single wiki page → standalone HTML document."""
    raw = wiki_path.read_text(encoding="utf-8")
    body_md = _strip_frontmatter(raw)
    body_html = md_to_html(body_md)
    title = wiki_path.stem.replace("_", " ").title()
    return _PAGE_TEMPLATE.format(title=title, body=body_html)


def render_kb_html(layout: KBLayout, index: MetaIndex) -> str:
    """Index page listing all wiki pages, grouped by type."""
    pages = index.all_pages()
    groups: dict[str, list] = {}
    for p in pages:
        groups.setdefault(p["page_type"] or "misc", []).append(p)

    sections = []
    for ptype in sorted(groups):
        items = sorted(groups[ptype], key=lambda r: r["title"].lower())
        lis = "\n".join(
            f'<li><a href="{Path(p["wiki_path"]).stem}.html">{p["title"]}</a> '
            f'<span style="color:#999">— {(p["confidence"] or 0):.0%}</span></li>'
            for p in items
        )
        sections.append(f"<h2>{ptype.replace('_', ' ').title()}</h2>\n<ul>\n{lis}\n</ul>")

    body = (
        f'<h1>{layout.root.name} — Knowledge Base</h1>\n'
        f'<p class="meta">{len(pages)} page(s)</p>\n'
        + "\n".join(sections)
    )
    return _PAGE_TEMPLATE.format(title=f"{layout.root.name} — KB", body=body)
