"""Tests for deterministic presenter modules (no network, no LLM)."""

import tempfile
from pathlib import Path

import pytest

from kompyla.presenter.html_export import md_to_html, _strip_frontmatter
from kompyla.presenter.markdown_bundle import bundle_kb_markdown
from kompyla.presenter.slides import page_to_marp, _split_into_slides
from kompyla.presenter.docx_export import md_to_docx
from kompyla.presenter.pptx_export import md_to_pptx, _split_slides
from kompyla.storage.layout import KBLayout
from kompyla.storage.index import MetaIndex


@pytest.fixture
def kb_with_pages():
    with tempfile.TemporaryDirectory() as tmp:
        layout = KBLayout(Path(tmp))
        layout.create()
        index = MetaIndex(layout.meta_db)

        page_md = """\
---
title: Tesla Model 3
type: article
confidence: 0.85
---

# Tesla Model 3

## Summary

The Model 3 is an electric sedan.

## Battery

- 75 kWh long range pack
- LFP standard range pack

## History

Production started in 2017.
"""
        wpath = layout.wiki / "tesla_model_3.md"
        wpath.write_text(page_md, encoding="utf-8")
        index.upsert_page(
            title="Tesla Model 3", wiki_path=wpath, page_type="article",
            sources=["raw/x.md"], confidence=0.85, tags=["ev"],
        )

        yield layout, index, wpath
        index.close()


def test_md_to_html_renders_headings():
    html = md_to_html("# Hello\n\nWorld\n")
    assert "Hello</h1>" in html         # toc extension adds id="..." attribute
    assert "<p>World</p>" in html


def test_strip_frontmatter():
    assert _strip_frontmatter("---\ntitle: x\n---\n# H\n").startswith("# H")
    assert _strip_frontmatter("# No FM").startswith("# No FM")


def test_bundle_kb_markdown(kb_with_pages):
    layout, index, _ = kb_with_pages
    bundle = bundle_kb_markdown(layout, index)
    assert "# tmp" in bundle or "Knowledge Base Bundle" in bundle
    assert "Tesla Model 3" in bundle
    assert "## Battery" in bundle  # body content included


def test_split_slides_h2_creates_separate_slides(kb_with_pages):
    _, _, wpath = kb_with_pages
    body = wpath.read_text()
    slides = _split_into_slides(body.split("---", 2)[-1])
    titles = [s[0] for s in slides]
    assert "Tesla Model 3" in titles[0]
    assert "Summary" in titles
    assert "Battery" in titles
    assert "History" in titles


def test_page_to_marp_has_frontmatter(kb_with_pages):
    _, _, wpath = kb_with_pages
    marp = page_to_marp(wpath)
    assert marp.startswith("---\nmarp: true")
    assert "\n---\n" in marp   # at least one slide separator


def test_md_to_docx_writes_file(kb_with_pages, tmp_path):
    _, _, wpath = kb_with_pages
    out = tmp_path / "out.docx"
    md_to_docx(wpath.read_text(), out, title="Test")
    assert out.exists()
    assert out.stat().st_size > 1000   # docx has minimum size


def test_pptx_split_slides_has_one_per_h2():
    md = "# Title\n\nIntro.\n\n## First\n- a\n- b\n\n## Second\nbody"
    slides = _split_slides(md)
    titles = [s[0] for s in slides]
    assert "Title" in titles
    assert "First" in titles
    assert "Second" in titles


def test_md_to_pptx_writes_file(kb_with_pages, tmp_path):
    _, _, wpath = kb_with_pages
    out = tmp_path / "deck.pptx"
    md_to_pptx(wpath.read_text(), out, deck_title="Tesla Deck")
    assert out.exists()
    assert out.stat().st_size > 5000
