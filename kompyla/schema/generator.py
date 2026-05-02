from __future__ import annotations

import json

from ..llm.base import LLMProvider, Message
from .models import DomainSchema

_SYSTEM = (
    "You are a knowledge architect. When given a research domain you produce a "
    "structured schema for organizing knowledge about that domain. "
    "Always respond with valid JSON only — no markdown, no extra text."
)

_USER_TEMPLATE = """\
Create a knowledge base schema for the research domain: "{domain}"

Respond with JSON that matches this structure exactly:
{{
  "domain": "<domain name>",
  "description": "<1-2 sentence description>",
  "page_types": [
    {{
      "name": "<type name>",
      "description": "<what this page covers>",
      "required_sections": ["Section1", "Section2"]
    }}
  ],
  "entity_categories": [
    {{
      "name": "<category name>",
      "description": "<what entities belong here>",
      "examples": ["example1", "example2"]
    }}
  ],
  "relationship_types": [
    {{
      "name": "<relation name>",
      "from_type": "<entity or page type>",
      "to_type": "<entity or page type>",
      "description": "<what this relation means>"
    }}
  ],
  "seed_queries": ["<search query 1>", "<search query 2>"]
}}

Requirements:
- 4–6 page types
- 4–8 entity categories
- 4–8 relationship types
- 8–12 seed queries
Be specific and concrete for the given domain.\
"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown fences if the model adds them despite instructions
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
    return json.loads(text)


def generate_schema(domain: str, llm: LLMProvider) -> DomainSchema:
    response = llm.chat(
        messages=[Message(role="user", content=_USER_TEMPLATE.format(domain=domain))],
        system=_SYSTEM,
    )
    data = _parse_json(response)
    return DomainSchema(**data)
