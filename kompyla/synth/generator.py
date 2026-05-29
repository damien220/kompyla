"""Synthetic Q&A training data generator from mature wiki pages."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from kompyla.llm.base import Message
from kompyla.utils.json_utils import parse_llm_json
from kompyla.storage.index import MetaIndex
from kompyla.storage.layout import KBLayout

_PROMPT_TMPL = """\
You are a training-data generator.  Given the wiki article below, generate {n} \
question-answer pairs that a student might ask and that the article directly answers.

Rules:
- Each question must be answerable using only the text provided.
- Answers should be concise (1-3 sentences) and use the article's own words where natural.
- Return ONLY a JSON array, no markdown fences.  Format:
  [{{"question": "...", "answer": "..."}}]

Article title: {title}

{body}
"""


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip() if len(parts) >= 3 else text


def generate_training_data(
    layout: KBLayout,
    index: MetaIndex,
    llm,
    *,
    min_confidence: float = 0.7,
    pairs_per_page: int = 3,
) -> list[dict]:
    """Generate Q&A pairs from high-confidence wiki pages.

    Each returned dict has keys: prompt, completion, source, confidence.
    """
    pages = [p for p in index.all_pages() if (p["confidence"] or 0) >= min_confidence]
    records: list[dict] = []

    for page in pages:
        wpath = Path(page["wiki_path"])
        if not wpath.exists():
            continue
        body = _strip_frontmatter(wpath.read_text(encoding="utf-8")).strip()
        if len(body) < 200:
            continue

        prompt_text = _PROMPT_TMPL.format(
            n=pairs_per_page,
            title=page["title"],
            body=body[:4000],
        )
        try:
            raw = llm.chat([Message(role="user", content=prompt_text)])
            pairs = _parse_pairs(raw)
        except Exception:
            continue

        for pair in pairs:
            if not pair.get("question") or not pair.get("answer"):
                continue
            records.append({
                "prompt": pair["question"].strip(),
                "completion": pair["answer"].strip(),
                "source": page["title"],
                "confidence": page["confidence"],
            })

    return records


def save_training_data(records: list[dict], out_path: Path) -> Path:
    """Write records to a JSONL file (one JSON object per line)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path


def _parse_pairs(text: str) -> list[dict]:
    return parse_llm_json(text, expect_list=True)  # type: ignore[return-value]
