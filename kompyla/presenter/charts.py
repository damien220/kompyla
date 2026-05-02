"""Matplotlib-based KB stats charts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Headless rendering
import matplotlib.pyplot as plt

from ..storage.index import MetaIndex
from ..storage.layout import KBLayout


def _save_fig(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _confidence_histogram(pages: list, out: Path) -> None:
    confs = [p["confidence"] or 0.0 for p in pages]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(confs, bins=10, range=(0, 1), edgecolor="white", color="#2563eb")
    ax.set_xlabel("Confidence")
    ax.set_ylabel("Pages")
    ax.set_title("Wiki Page Confidence Distribution")
    ax.set_xlim(0, 1)
    _save_fig(fig, out)


def _pages_by_type(pages: list, out: Path) -> None:
    counts = Counter(p["page_type"] or "misc" for p in pages)
    if not counts:
        return
    labels = list(counts.keys())
    values = [counts[k] for k in labels]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(labels, values, color="#10b981")
    ax.set_ylabel("Pages")
    ax.set_title("Wiki Pages by Type")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v, str(v),
                ha="center", va="bottom", fontsize=9)
    _save_fig(fig, out)


def _raw_by_source(raw_docs: list, out: Path) -> None:
    counts = Counter(r["source_type"] or "manual" for r in raw_docs)
    if not counts:
        return
    labels = list(counts.keys())
    values = [counts[k] for k in labels]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, values, color="#f59e0b")
    ax.set_ylabel("Raw documents")
    ax.set_title("Raw Documents by Source")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    _save_fig(fig, out)


def generate_kb_charts(layout: KBLayout, index: MetaIndex) -> list[Path]:
    """Generate the standard KB dashboard charts and return their paths."""
    out_dir = layout.outputs / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = index.all_pages()
    raw_docs = index.all_raw_docs()

    paths = []
    if pages:
        p1 = out_dir / "confidence_histogram.png"
        _confidence_histogram(pages, p1)
        paths.append(p1)

        p2 = out_dir / "pages_by_type.png"
        _pages_by_type(pages, p2)
        paths.append(p2)

    if raw_docs:
        p3 = out_dir / "raw_by_source.png"
        _raw_by_source(raw_docs, p3)
        paths.append(p3)

    return paths
