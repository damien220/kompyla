"""Multi-KB cross-referencing: surface shared topics across separate domain KBs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from kompyla.storage.index import MetaIndex
from kompyla.storage.layout import KBLayout

# Common English stop-words to exclude from term overlap
_STOP = frozenset(
    "the a an and or but in on at to of for with by from is are was were be been "
    "being have has had do does did will would could should may might shall can "
    "this that these those it its we you he she they them their our your his her "
    "not no nor so yet both either neither each every all any few more most some "
    "such only own same than then once here there when where why how which who whom "
    "what about into through during before after above below between into out off "
    "over under again further then once".split()
)


@dataclass
class CrossRefResult:
    source_title: str
    target_title: str
    shared_terms: list[str]
    similarity: float
    note: str = ""


def _significant_terms(text: str) -> set[str]:
    """Extract lower-cased words of length ≥ 4 that are not stop-words."""
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return {w for w in words if w not in _STOP}


def _page_terms(layout: KBLayout, wiki_path_str: str) -> set[str]:
    p = Path(wiki_path_str)
    if not p.exists():
        return set()
    return _significant_terms(p.read_text(encoding="utf-8"))


def find_connections(
    source_layout: KBLayout,
    source_index: MetaIndex,
    target_layout: KBLayout,
    target_index: MetaIndex,
    *,
    threshold: float = 0.15,
    llm=None,
) -> list[CrossRefResult]:
    """Compare all pages in source KB against all pages in target KB.

    Returns pairs whose Jaccard term-overlap >= threshold.
    If an LLM is provided, each connection gets a one-sentence note.
    """
    source_pages = source_index.all_pages()
    target_pages = target_index.all_pages()

    # Pre-build term sets for target pages
    target_terms: list[tuple[dict, set[str]]] = [
        (tp, _page_terms(target_layout, tp["wiki_path"])) for tp in target_pages
    ]

    results: list[CrossRefResult] = []
    for sp in source_pages:
        s_terms = _page_terms(source_layout, sp["wiki_path"])
        if not s_terms:
            continue
        for tp, t_terms in target_terms:
            if not t_terms:
                continue
            shared = s_terms & t_terms
            union = s_terms | t_terms
            jaccard = len(shared) / len(union) if union else 0.0
            if jaccard < threshold:
                continue
            top_shared = sorted(shared, key=lambda w: -len(w))[:10]
            results.append(CrossRefResult(
                source_title=sp["title"],
                target_title=tp["title"],
                shared_terms=top_shared,
                similarity=round(jaccard, 3),
            ))

    # Sort strongest connections first
    results.sort(key=lambda r: -r.similarity)

    if llm and results:
        _annotate_with_llm(results[:20], llm)

    return results


def _annotate_with_llm(results: list[CrossRefResult], llm) -> None:
    """Add a one-sentence note to each CrossRefResult via LLM."""
    from kompyla.llm.base import Message

    for r in results:
        prompt = (
            f'Two wiki pages share overlapping topics.\n'
            f'Page A: "{r.source_title}"\n'
            f'Page B: "{r.target_title}"\n'
            f'Shared terms: {", ".join(r.shared_terms[:8])}\n\n'
            'In one sentence, describe how these pages are related.'
        )
        try:
            r.note = llm.chat([Message(role="user", content=prompt)]).strip()
        except Exception:
            r.note = ""


def write_crossref_report(
    results: list[CrossRefResult],
    source_layout: KBLayout,
    target_domain: str,
) -> Path:
    """Write a markdown cross-reference report to outputs/ of the source KB."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", target_domain.lower()).strip("_")
    out = source_layout.outputs / f"crossref_{slug}_{ts}.md"
    source_layout.outputs.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Cross-Reference Report: {source_layout.root.name} ↔ {target_domain}",
        f"_Generated {ts}_\n",
        f"**Connections found:** {len(results)}\n",
    ]
    if not results:
        lines.append("_No overlapping pages found above the similarity threshold._")
    else:
        lines.append("| Source Page | Target Page | Similarity | Shared Terms |")
        lines.append("|---|---|---|---|")
        for r in results:
            terms_str = ", ".join(r.shared_terms[:6])
            lines.append(f"| {r.source_title} | {r.target_title} | {r.similarity:.0%} | {terms_str} |")
        if any(r.note for r in results):
            lines.append("\n## Notable Connections\n")
            for r in results:
                if r.note:
                    lines.append(f"- **{r.source_title}** ↔ **{r.target_title}**: {r.note}")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
