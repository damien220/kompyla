"""Generate Marp slide decks from a wiki page (or arbitrary markdown)."""

from __future__ import annotations

import re
from pathlib import Path

import markdown as md_lib

_MARP_FRONTMATTER = """\
---
marp: true
theme: default
paginate: true
size: 16:9
---
"""


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip() if len(parts) >= 3 else text


def _split_into_slides(body_md: str) -> list[tuple[str, str]]:
    """Split markdown into (title, content) pairs.

    Splits on `## ` headers. The leading H1 (if present) becomes the cover slide;
    everything before the first `## ` becomes the cover slide content.
    """
    lines = body_md.splitlines()

    # Cover slide: H1 + intro until first H2
    cover_title = ""
    cover_body: list[str] = []
    i = 0
    while i < len(lines) and not lines[i].startswith("## "):
        line = lines[i]
        if line.startswith("# ") and not cover_title:
            cover_title = line[2:].strip()
        elif line.strip():
            cover_body.append(line)
        i += 1

    slides: list[tuple[str, str]] = [(cover_title or "Slides", "\n".join(cover_body).strip())]

    # Subsequent slides: each `## ` header
    current_title: str | None = None
    current_body: list[str] = []
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            if current_title is not None:
                slides.append((current_title, "\n".join(current_body).strip()))
            current_title = line[3:].strip()
            current_body = []
        else:
            current_body.append(line)
        i += 1
    if current_title is not None:
        slides.append((current_title, "\n".join(current_body).strip()))

    return slides


def page_to_marp(wiki_path: Path) -> str:
    """Convert a wiki page to Marp-flavoured markdown."""
    raw = wiki_path.read_text(encoding="utf-8")
    body = _strip_frontmatter(raw)
    slides = _split_into_slides(body)

    parts = [_MARP_FRONTMATTER]
    for idx, (title, content) in enumerate(slides):
        if idx > 0:
            parts.append("\n---\n")
        parts.append(f"# {title}\n" if idx == 0 else f"## {title}\n")
        if content:
            parts.append(content + "\n")
    return "\n".join(parts)


_MARP_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ margin: 0; padding: 0; background: #222; font-family: -apple-system, sans-serif; }}
.slide {{ width: 1280px; height: 720px; margin: 2rem auto; background: white;
         padding: 4rem; box-sizing: border-box; box-shadow: 0 4px 20px rgba(0,0,0,.4);
         page-break-after: always; overflow: hidden; }}
.slide h1 {{ font-size: 3rem; }}
.slide h2 {{ font-size: 2.2rem; margin-top: 0; }}
.slide h3 {{ font-size: 1.5rem; }}
.slide p, .slide li {{ font-size: 1.3rem; line-height: 1.5; }}
@media print {{
  body {{ background: white; }}
  .slide {{ margin: 0; box-shadow: none; }}
}}
</style>
</head>
<body>
{slides_html}
</body>
</html>
"""


def render_marp_html(marp_md: str) -> str:
    """Render Marp-flavoured markdown to a viewable / printable HTML deck.

    Pure-Python alternative to marp-cli — won't reproduce every Marp directive
    but works for the standard slide-per-`---`/`## ` flow we generate.
    """
    body = re.sub(r"^---\nmarp:.*?---\n", "", marp_md, count=1, flags=re.S)
    raw_slides = re.split(r"\n---\n", body)

    rendered = []
    for idx, slide_md in enumerate(raw_slides):
        slide_html = md_lib.markdown(slide_md.strip(), extensions=["extra", "tables", "fenced_code"])
        rendered.append(f'<div class="slide">{slide_html}</div>')

    return _MARP_HTML_TEMPLATE.format(
        title="Kompyla Slides",
        slides_html="\n".join(rendered),
    )
