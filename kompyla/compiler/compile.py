from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..llm.base import LLMProvider, Message
from ..schema.models import DomainSchema
from ..storage.index import MetaIndex
from ..storage.layout import KBLayout

# Characters fed to the LLM; keeps context within limits of smaller offline models
_MAX_SOURCE_CHARS = 8_000

_SYSTEM = (
    "You are a knowledge compiler. You transform raw source documents into "
    "structured wiki pages in markdown format. "
    "Always respond with valid JSON only — no markdown fences, no extra text."
)

_USER_TEMPLATE = """\
Domain: {domain}
Available page types: {page_types}

Source document path: {source_path}
--- BEGIN SOURCE ---
{content}
--- END SOURCE ---

Compile this source into a wiki page. Respond with JSON:
{{
  "title": "<concise, specific title — no generic words like 'Overview'>",
  "page_type": "<one of the available page types>",
  "confidence": <float 0.0–1.0, based on source completeness and clarity>,
  "tags": ["<tag1>", "<tag2>"],
  "summary": "<2–4 sentence factual summary>",
  "sections": {{
    "<Section Name>": "<markdown content>",
    "<Another Section>": "<markdown content>"
  }},
  "related_topics": ["<topic or likely page title>"]
}}

Be factual. Extract only what is in the source — do not invent information.\
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    return text


def _parse_llm_json(response: str) -> dict:
    return json.loads(_strip_fences(response))


def _wiki_page(
    title: str,
    page_type: str,
    confidence: float,
    tags: list[str],
    summary: str,
    sections: dict[str, str],
    related_topics: list[str],
    sources: list[str],
    created: str | None = None,
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fm: dict = {
        "title": title,
        "type": page_type,
        "sources": sources,
        "created": created or today,
        "updated": today,
        "confidence": round(confidence, 2),
        "tags": tags,
    }
    frontmatter = yaml.dump(fm, default_flow_style=False, allow_unicode=True).strip()
    parts = [f"---\n{frontmatter}\n---\n", f"# {title}\n", f"## Summary\n\n{summary}\n"]
    for sec_name, sec_body in sections.items():
        parts.append(f"## {sec_name}\n\n{sec_body}\n")
    if related_topics:
        links = "\n".join(f"- [[{t}]]" for t in related_topics)
        parts.append(f"## Related Pages\n\n{links}\n")
    return "\n".join(parts)


def _slug(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s[:60].strip("_")


_MERGE_SYSTEM = (
    "You merge new information into an existing wiki page. "
    "Always respond with valid JSON only — no markdown, no commentary."
)

_MERGE_TEMPLATE = """\
You are updating a wiki page with new source material.

EXISTING PAGE (markdown, frontmatter stripped):
--- BEGIN ---
{existing}
--- END ---

NEW SOURCE:
--- BEGIN ---
{new_content}
--- END ---

Available page types: {page_types}

Produce a merged page that:
1. Preserves all unique facts from the existing page
2. Incorporates new facts from the new source
3. Resolves contradictions explicitly (note them in the relevant section)
4. Refreshes the summary to reflect the combined content

Respond with JSON:
{{
  "title": "<keep existing title unless clearly wrong>",
  "page_type": "<one of the available page types>",
  "confidence": <float 0.0-1.0>,
  "tags": ["..."],
  "summary": "<2-4 sentence updated summary>",
  "sections": {{
    "<Section>": "<merged markdown>"
  }},
  "related_topics": ["..."]
}}\
"""


def _existing_page_at(wiki_path: Path) -> dict | None:
    """If a wiki page already exists, return its frontmatter + content; else None."""
    if not wiki_path.exists():
        return None
    import frontmatter as _fm
    post = _fm.load(wiki_path)
    return {
        "metadata": dict(post.metadata),
        "content": post.content,
    }


def compile_document(
    raw_path: Path,
    layout: KBLayout,
    schema: DomainSchema,
    llm: LLMProvider,
    index: MetaIndex,
) -> Path | None:
    content = raw_path.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        return None

    page_types = ", ".join(pt.name for pt in schema.page_types)
    source_rel = str(raw_path.relative_to(layout.root))

    # Step 1 — first-pass compile of the new source
    response = llm.chat(
        messages=[Message(
            role="user",
            content=_USER_TEMPLATE.format(
                domain=schema.domain,
                page_types=page_types,
                source_path=source_rel,
                content=content[:_MAX_SOURCE_CHARS],
            ),
        )],
        system=_SYSTEM,
    )
    data = _parse_llm_json(response)

    # Step 2 — does an existing page on this topic exist? If so, merge.
    wiki_path = layout.wiki / f"{_slug(data['title'])}.md"
    existing = _existing_page_at(wiki_path)

    if existing is not None:
        merge_prompt = _MERGE_TEMPLATE.format(
            existing=existing["content"][:_MAX_SOURCE_CHARS],
            new_content=content[:_MAX_SOURCE_CHARS],
            page_types=page_types,
        )
        merge_response = llm.chat(
            messages=[Message(role="user", content=merge_prompt)],
            system=_MERGE_SYSTEM,
        )
        try:
            data = _parse_llm_json(merge_response)
        except (ValueError, json.JSONDecodeError):
            # Fall back to the first-pass output if merge JSON fails
            pass
        prior_sources = existing["metadata"].get("sources", []) or []
        merged_sources = list(dict.fromkeys([*prior_sources, source_rel]))
        created = existing["metadata"].get("created")
    else:
        merged_sources = [source_rel]
        created = None

    page_md = _wiki_page(
        title=data["title"],
        page_type=data.get("page_type", "article"),
        confidence=float(data.get("confidence", 0.5)),
        tags=data.get("tags", []),
        summary=data["summary"],
        sections=data.get("sections", {}),
        related_topics=data.get("related_topics", []),
        sources=merged_sources,
        created=created,
    )
    wiki_path.write_text(page_md, encoding="utf-8")

    index.upsert_page(
        title=data["title"],
        wiki_path=wiki_path,
        page_type=data.get("page_type", "article"),
        sources=merged_sources,
        confidence=float(data.get("confidence", 0.5)),
        tags=data.get("tags", []),
    )
    index.mark_compiled(raw_path)
    return wiki_path
