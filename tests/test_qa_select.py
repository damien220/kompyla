"""Tests for keyword-based page selection (deterministic, no LLM)."""

import sqlite3
import tempfile
from pathlib import Path

from kompyla.query.qa import select_relevant_pages, _strip_frontmatter
from kompyla.storage.index import MetaIndex
from kompyla.storage.layout import KBLayout


def _make_index_with(titles: list[str]) -> tuple[KBLayout, MetaIndex]:
    tmp = tempfile.mkdtemp()
    layout = KBLayout(Path(tmp))
    layout.create()
    index = MetaIndex(layout.meta_db)
    for t in titles:
        slug = t.lower().replace(" ", "_")
        wpath = layout.wiki / f"{slug}.md"
        wpath.write_text(f"# {t}\n", encoding="utf-8")
        index.upsert_page(title=t, wiki_path=wpath, page_type="article",
                          sources=[], confidence=0.8, tags=[])
    return layout, index


def test_keyword_matching_ranks_relevant_first():
    _, index = _make_index_with([
        "Tesla Model 3 Battery",
        "Toyota Prius Engine",
        "Tesla Charging Network",
    ])
    pages = index.all_pages()
    selected = select_relevant_pages("How big is the Tesla battery?", pages)
    titles = [p["title"] for p in selected]
    assert titles[0] == "Tesla Model 3 Battery"     # both keywords match
    index.close()


def test_falls_back_when_no_match():
    _, index = _make_index_with(["Page A", "Page B"])
    pages = index.all_pages()
    selected = select_relevant_pages("Nothing related at all here", pages)
    assert len(selected) == 2
    index.close()


def test_strip_frontmatter():
    raw = "---\ntitle: x\n---\n\n# Hello\nbody"
    assert _strip_frontmatter(raw).strip().startswith("# Hello")
    assert "title: x" not in _strip_frontmatter(raw)


def test_strip_frontmatter_no_fm():
    raw = "# No frontmatter here\nbody"
    assert _strip_frontmatter(raw) == raw
