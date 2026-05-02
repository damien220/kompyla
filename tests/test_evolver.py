import tempfile
from pathlib import Path

import pytest

from kompyla.evolver.lint import (
    find_broken_links, find_stale_pages,
    find_low_confidence_pages, find_orphan_pages, lint_kb,
)
from kompyla.evolver.gaps import detect_broken_link_gaps
from kompyla.evolver.confidence import low_confidence_pages
from kompyla.storage.layout import KBLayout
from kompyla.storage.index import MetaIndex


@pytest.fixture
def kb():
    """Build a tmp KB with a few synthetic wiki pages and meta-index entries."""
    with tempfile.TemporaryDirectory() as tmp:
        layout = KBLayout(Path(tmp))
        layout.create()
        index = MetaIndex(layout.meta_db)

        def add(title, content, confidence=0.8):
            slug = title.lower().replace(" ", "_")
            wpath = layout.wiki / f"{slug}.md"
            wpath.write_text(content, encoding="utf-8")
            index.upsert_page(title=title, wiki_path=wpath, page_type="article",
                              sources=["raw/x.md"], confidence=confidence, tags=[])
            return wpath

        add("Tesla Model 3", "# Tesla Model 3\nLinks to [[Battery Pack]] and [[NonExistent Page]].")
        add("Battery Pack", "# Battery Pack\nUsed by [[Tesla Model 3]].")
        add("Orphan Topic", "# Orphan Topic\nNothing links here.", confidence=0.4)

        yield layout, index
        index.close()


def test_broken_links_found(kb):
    layout, index = kb
    broken = find_broken_links(layout, index.all_pages())
    targets = {b[1] for b in broken}
    assert "NonExistent Page" in targets
    assert "Battery Pack" not in targets   # exists


def test_low_confidence_picked_up(kb):
    _, index = kb
    low = find_low_confidence_pages(index.all_pages(), threshold=0.6)
    assert {p["title"] for p in low} == {"Orphan Topic"}


def test_orphan_pages_detected(kb):
    layout, index = kb
    orphans = find_orphan_pages(layout, index.all_pages())
    assert {p["title"] for p in orphans} == {"Orphan Topic"}


def test_lint_writes_report(kb):
    layout, index = kb
    out = lint_kb(layout, index)
    assert out.exists()
    text = out.read_text()
    assert "# Lint Report" in text
    assert "Broken Links" in text
    assert "Orphan Topic" in text


def test_broken_link_gaps_dedups(kb):
    layout, index = kb
    queries = detect_broken_link_gaps(layout, index.all_pages())
    assert "NonExistent Page" in queries
    # Sorted, unique
    assert queries == sorted(set(queries))


def test_low_confidence_pages_helper(kb):
    _, index = kb
    pages = low_confidence_pages(index, threshold=0.5)
    assert len(pages) == 1
    assert pages[0]["title"] == "Orphan Topic"
