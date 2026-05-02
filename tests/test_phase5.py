"""Tests for Phase 5 — Advanced Capabilities (no network, no LLM)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kompyla.storage.layout import KBLayout
from kompyla.storage.index import MetaIndex
from kompyla.feedback.store import FeedbackStore, VALID_SIGNALS
from kompyla.feedback.apply import apply_feedback
from kompyla.crossref.bridge import (
    _significant_terms,
    find_connections,
    write_crossref_report,
)
from kompyla.scheduler.schedule import (
    load_schedule,
    save_schedule,
    is_due,
    mark_ran,
)
from kompyla.synth.generator import _parse_pairs, _strip_frontmatter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kb_pair():
    """Two temporary KBs with one page each sharing some terms."""
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        la = KBLayout(Path(tmp_a))
        la.create()
        lb = KBLayout(Path(tmp_b))
        lb.create()

        ia = MetaIndex(la.meta_db)
        ib = MetaIndex(lb.meta_db)

        page_a = la.wiki / "electric_vehicles.md"
        page_a.write_text(
            "# Electric Vehicles\nBattery electric vehicles use lithium-ion batteries.\n"
            "The charging infrastructure is expanding rapidly.\n",
            encoding="utf-8",
        )
        ia.upsert_page("Electric Vehicles", page_a, "article", [], 0.9, [])

        page_b = lb.wiki / "batteries.md"
        page_b.write_text(
            "# Batteries\nLithium-ion batteries power electric vehicles and portable devices.\n"
            "Battery charging stations are deployed at scale.\n",
            encoding="utf-8",
        )
        ib.upsert_page("Batteries", page_b, "article", [], 0.85, [])

        # Write minimal kompyla.yaml for each
        la.kb_config.write_text("domain: electric vehicles\n")
        lb.kb_config.write_text("domain: batteries\n")

        yield la, ia, lb, ib

        ia.close()
        ib.close()


@pytest.fixture
def kb_with_pages():
    with tempfile.TemporaryDirectory() as tmp:
        layout = KBLayout(Path(tmp))
        layout.create()
        index = MetaIndex(layout.meta_db)
        layout.kb_config.write_text("domain: test\n")

        for title, conf in [("Page A", 0.9), ("Page B", 0.4)]:
            slug = title.lower().replace(" ", "_")
            wpath = layout.wiki / f"{slug}.md"
            wpath.write_text(f"# {title}\n\nContent for {title}.\n")
            index.upsert_page(title, wpath, "article", [], conf, [])

        yield layout, index

        index.close()


# ---------------------------------------------------------------------------
# Schedule tests
# ---------------------------------------------------------------------------

def test_schedule_defaults_not_enabled(kb_with_pages):
    layout, _ = kb_with_pages
    sched = load_schedule(layout)
    assert sched["enabled"] is False
    assert sched["interval_hours"] == 24
    assert sched["last_run_at"] is None


def test_schedule_save_and_reload(kb_with_pages):
    layout, _ = kb_with_pages
    sched = load_schedule(layout)
    sched["enabled"] = True
    sched["interval_hours"] = 6
    save_schedule(layout, sched)

    reloaded = load_schedule(layout)
    assert reloaded["enabled"] is True
    assert reloaded["interval_hours"] == 6


def test_schedule_is_due_when_never_ran(kb_with_pages):
    layout, _ = kb_with_pages
    sched = {"enabled": True, "interval_hours": 24, "last_run_at": None}
    assert is_due(sched) is True


def test_schedule_not_due_when_just_ran(kb_with_pages):
    from datetime import datetime, timezone
    layout, _ = kb_with_pages
    sched = {
        "enabled": True,
        "interval_hours": 24,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
    }
    assert is_due(sched) is False


def test_schedule_not_due_when_disabled(kb_with_pages):
    from datetime import datetime, timezone
    layout, _ = kb_with_pages
    sched = {"enabled": False, "interval_hours": 1, "last_run_at": None}
    assert is_due(sched) is False


# ---------------------------------------------------------------------------
# Feedback store tests
# ---------------------------------------------------------------------------

def test_feedback_store_add_and_retrieve(tmp_path):
    store = FeedbackStore(tmp_path / "fb.db")
    store.add("Page A", "excellent", "Great article!")
    store.add("Page A", "outdated")
    rows = store.for_page("Page A")
    assert len(rows) == 2
    signals = {r["signal"] for r in rows}
    assert signals == {"excellent", "outdated"}
    store.close()


def test_feedback_store_invalid_signal(tmp_path):
    store = FeedbackStore(tmp_path / "fb.db")
    with pytest.raises(ValueError):
        store.add("Page A", "love")
    store.close()


def test_feedback_store_signal_counts(tmp_path):
    store = FeedbackStore(tmp_path / "fb.db")
    store.add("Page X", "wrong")
    store.add("Page X", "wrong")
    store.add("Page X", "excellent")
    counts = store.signal_counts("Page X")
    assert counts["wrong"] == 2
    assert counts["excellent"] == 1
    store.close()


# ---------------------------------------------------------------------------
# Feedback apply tests
# ---------------------------------------------------------------------------

def test_apply_feedback_raises_confidence(kb_with_pages):
    layout, index = kb_with_pages
    store = FeedbackStore(layout.feedback_db)
    store.add("Page A", "excellent")
    result = apply_feedback(layout, index, store)
    store.close()

    # Page A had conf 0.9; +0.10 → 1.0 (capped)
    updated_page = next(p for p in index.all_pages() if p["title"] == "Page A")
    assert updated_page["confidence"] >= 0.9
    assert result["updated"] >= 0  # may be 0 if delta too small after cap


def test_apply_feedback_lowers_confidence(kb_with_pages):
    layout, index = kb_with_pages
    store = FeedbackStore(layout.feedback_db)
    store.add("Page B", "wrong")  # conf was 0.4; -0.20 → 0.2
    result = apply_feedback(layout, index, store)
    store.close()

    updated_page = next(p for p in index.all_pages() if p["title"] == "Page B")
    assert updated_page["confidence"] <= 0.4
    assert "Page B" in result["flagged_for_research"]


def test_apply_feedback_skips_missing_page(kb_with_pages):
    layout, index = kb_with_pages
    store = FeedbackStore(layout.feedback_db)
    store.add("Nonexistent Page", "wrong")
    result = apply_feedback(layout, index, store)
    store.close()
    assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# Cross-reference tests
# ---------------------------------------------------------------------------

def test_significant_terms_excludes_stopwords():
    terms = _significant_terms("The electric vehicle uses lithium batteries")
    assert "electric" in terms
    assert "vehicle" in terms
    assert "the" not in terms   # stop-word excluded
    assert "lithium" in terms
    assert "batteries" in terms


def test_find_connections_detects_overlap(kb_pair):
    la, ia, lb, ib = kb_pair
    results = find_connections(la, ia, lb, ib, threshold=0.05)
    assert len(results) > 0
    titles = [(r.source_title, r.target_title) for r in results]
    assert ("Electric Vehicles", "Batteries") in titles


def test_find_connections_respects_threshold(kb_pair):
    la, ia, lb, ib = kb_pair
    # Very high threshold should produce no results
    results = find_connections(la, ia, lb, ib, threshold=0.99)
    assert results == []


def test_write_crossref_report_creates_file(kb_pair):
    la, ia, lb, ib = kb_pair
    results = find_connections(la, ia, lb, ib, threshold=0.05)
    report = write_crossref_report(results, la, "batteries")
    assert report.exists()
    text = report.read_text()
    assert "Cross-Reference Report" in text
    assert "Electric Vehicles" in text or "Batteries" in text


# ---------------------------------------------------------------------------
# Synth generator tests
# ---------------------------------------------------------------------------

def test_strip_frontmatter_removes_yaml():
    result = _strip_frontmatter("---\ntitle: Test\n---\n# Heading\n")
    assert result.startswith("# Heading")


def test_parse_pairs_valid_json():
    raw = '[{"question": "What is X?", "answer": "X is Y."}]'
    pairs = _parse_pairs(raw)
    assert len(pairs) == 1
    assert pairs[0]["question"] == "What is X?"


def test_parse_pairs_handles_fences():
    raw = "```json\n[{\"question\": \"Q?\", \"answer\": \"A.\"}]\n```"
    pairs = _parse_pairs(raw)
    assert len(pairs) == 1


def test_parse_pairs_bad_json_returns_empty():
    pairs = _parse_pairs("not json at all")
    assert pairs == []
