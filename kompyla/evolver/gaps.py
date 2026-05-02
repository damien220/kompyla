"""Gap detection — broken-link gaps (deterministic) + LLM-suggested topic gaps."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ..llm.base import LLMProvider, Message
from ..schema.models import DomainSchema
from ..storage.index import MetaIndex
from ..storage.layout import KBLayout

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def detect_broken_link_gaps(layout: KBLayout, pages: list[sqlite3.Row]) -> list[str]:
    """Unique missing page titles, usable as search queries."""
    existing = {p["title"].lower() for p in pages}
    missing: set[str] = set()
    for page in pages:
        wpath = Path(page["wiki_path"])
        if wpath.exists():
            for m in _LINK_RE.finditer(wpath.read_text(encoding="utf-8")):
                target = m.group(1).strip()
                if target.lower() not in existing:
                    missing.add(target)
    return sorted(missing)


_TOPIC_GAP_SYSTEM = (
    "You analyze a knowledge base and identify missing topics. "
    "Respond with valid JSON only — no markdown, no commentary."
)

_TOPIC_GAP_TEMPLATE = """\
Domain: {domain}
Description: {description}
Page types: {page_types}
Entity categories: {categories}

Existing pages ({n}):
{titles}

Identify 3-8 important topics that this knowledge base is missing — topics
that should exist but currently don't. Each suggestion must be specific and
phrased as a searchable query.

Respond with JSON:
{{"missing_topics": ["specific topic 1", "specific topic 2"]}}\
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    return text


def suggest_topic_gaps(
    pages: list[sqlite3.Row],
    schema: DomainSchema,
    llm: LLMProvider,
) -> list[str]:
    titles = "\n".join(f"- {p['title']}" for p in pages[:80]) or "(none yet)"
    prompt = _TOPIC_GAP_TEMPLATE.format(
        domain=schema.domain,
        description=schema.description,
        page_types=", ".join(pt.name for pt in schema.page_types),
        categories=", ".join(ec.name for ec in schema.entity_categories),
        n=len(pages),
        titles=titles,
    )
    try:
        response = llm.chat(
            messages=[Message(role="user", content=prompt)],
            system=_TOPIC_GAP_SYSTEM,
        )
        data = json.loads(_strip_fences(response))
        return [str(t) for t in data.get("missing_topics", [])]
    except (json.JSONDecodeError, RuntimeError, ValueError):
        return []


def detect_gaps(
    layout: KBLayout,
    index: MetaIndex,
    schema: DomainSchema,
    llm: LLMProvider | None = None,
) -> dict:
    """Run both deterministic and LLM-based gap detection."""
    pages = index.all_pages()
    return {
        "broken_link_queries": detect_broken_link_gaps(layout, pages),
        "topic_gap_queries": suggest_topic_gaps(pages, schema, llm) if llm else [],
    }
