"""LLM-based relevance scoring of fetched documents against a domain schema."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..llm.base import LLMProvider, Message
from ..utils.json_utils import parse_llm_json
from ..schema.models import DomainSchema

if TYPE_CHECKING:
    from ..retriever.base import FetchedDoc

_MAX_PEEK_CHARS = 2_000

_SYSTEM = (
    "You score how relevant a document is to a research domain. "
    "Respond with valid JSON only — no markdown, no commentary."
)

_TEMPLATE = """\
Domain: {domain}
Domain description: {description}
Page types: {page_types}

Document title: {title}
Document URL: {url}
Document excerpt:
--- BEGIN ---
{excerpt}
--- END ---

Score this document's relevance to the domain on a 0.0 to 1.0 scale.
Respond with JSON only:
{{"score": <float>, "reason": "<one short sentence>"}}\
"""


def _parse_llm_json(response: str) -> dict:
    return parse_llm_json(response)


class RelevanceScorer:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def score(self, doc: "FetchedDoc", schema: DomainSchema) -> float:
        prompt = _TEMPLATE.format(
            domain=schema.domain,
            description=schema.description,
            page_types=", ".join(pt.name for pt in schema.page_types),
            title=doc.title,
            url=doc.url,
            excerpt=doc.content[:_MAX_PEEK_CHARS],
        )
        try:
            response = self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                system=_SYSTEM,
                json_mode=True,
            )
            data = _parse_llm_json(response)
            score = float(data.get("score", 0.0))
        except (json.JSONDecodeError, ValueError, RuntimeError):
            return 0.0
        return max(0.0, min(1.0, score))
