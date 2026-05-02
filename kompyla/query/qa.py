"""Natural-language Q&A over the wiki, with optional feedback-loop save."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..llm.base import LLMProvider, Message
from ..schema.models import DomainSchema
from ..storage.index import MetaIndex
from ..storage.layout import KBLayout

_PAGE_BUDGET = 8
_PER_PAGE_CHARS = 2_000


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip() if len(parts) >= 3 else text


def select_relevant_pages(
    question: str,
    pages: list[sqlite3.Row],
    max_pages: int = _PAGE_BUDGET,
) -> list[sqlite3.Row]:
    """Keyword-overlap ranking against page titles. Falls back to recent pages."""
    q_words = set(re.findall(r"\w+", question.lower()))
    if not q_words:
        return list(pages)[:max_pages]
    scored = []
    for p in pages:
        t_words = set(re.findall(r"\w+", p["title"].lower()))
        score = len(q_words & t_words)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [p for _, p in scored[:max_pages]]
    return list(pages)[:max_pages]


_QA_SYSTEM = (
    "You answer questions using only the provided wiki pages. "
    "Cite each fact inline with [[Page Title]]. "
    "If the wiki does not contain the answer, say so explicitly. "
    "Do not invent facts."
)

_QA_TEMPLATE = """\
Question: {question}

Wiki pages (excerpts):

{pages}

---

Answer the question using only the information above.
End with a "Sources:" line listing each cited [[Page Title]].\
"""


def _slug(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s[:limit] or "query"


def _save_query_as_page(
    question: str,
    answer: str,
    sources: list[sqlite3.Row],
    layout: KBLayout,
    index: MetaIndex,
) -> Path:
    title = f"Q: {question.rstrip('?').strip()}"[:80]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fm = {
        "title": title,
        "type": "synthesis",
        "sources": [Path(p["wiki_path"]).name for p in sources],
        "created": today,
        "updated": today,
        "confidence": 0.7,
        "tags": ["query-feedback"],
        "question": question,
    }
    fm_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
    body = (
        f"# {title}\n\n"
        f"## Question\n\n{question}\n\n"
        f"## Answer\n\n{answer}\n"
    )
    wiki_path = layout.wiki / f"q_{_slug(question)}.md"
    wiki_path.write_text(f"---\n{fm_text}\n---\n\n{body}", encoding="utf-8")
    index.upsert_page(
        title=title,
        wiki_path=wiki_path,
        page_type="synthesis",
        sources=[Path(p["wiki_path"]).name for p in sources],
        confidence=0.7,
        tags=["query-feedback"],
    )
    return wiki_path


def answer_question(
    question: str,
    layout: KBLayout,
    index: MetaIndex,
    schema: DomainSchema,
    llm: LLMProvider,
    save_as_page: bool = False,
) -> tuple[str, Path | None]:
    """Answer a question. Returns (answer_markdown, saved_page_path_or_None)."""
    pages = index.all_pages()
    if not pages:
        return ("The knowledge base is empty — run `kompyla compile` first.", None)

    selected = select_relevant_pages(question, pages)
    page_blocks: list[str] = []
    for p in selected:
        wpath = Path(p["wiki_path"])
        if not wpath.exists():
            continue
        text = _strip_frontmatter(wpath.read_text(encoding="utf-8"))
        page_blocks.append(f"## [[{p['title']}]]\n\n{text[:_PER_PAGE_CHARS]}")

    prompt = _QA_TEMPLATE.format(
        question=question,
        pages="\n\n".join(page_blocks) or "(no relevant pages found)",
    )
    answer = llm.chat(
        messages=[Message(role="user", content=prompt)],
        system=_QA_SYSTEM,
    )

    saved = _save_query_as_page(question, answer, selected, layout, index) if save_as_page else None
    return answer, saved
