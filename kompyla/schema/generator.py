from __future__ import annotations

from ..llm.base import LLMProvider, Message
from ..utils.json_utils import parse_llm_json
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

_RETRY_PROMPT = (
    "Your previous response could not be parsed as JSON. Error: {error}\n\n"
    "Return ONLY the raw JSON object — no markdown fences, no comments, no trailing commas, "
    "no explanation. Start your response with {{ and end with }}."
)


def _parse_json(text: str) -> dict:
    result = parse_llm_json(text)
    if not result:
        raise ValueError(
            f"LLM response could not be parsed as a JSON object.\n"
            f"First 400 chars:\n{text[:400]}"
        )
    return result


def generate_schema(domain: str, llm: LLMProvider) -> DomainSchema:
    messages: list[Message] = [
        Message(role="user", content=_USER_TEMPLATE.format(domain=domain))
    ]

    last_exc: Exception = RuntimeError("LLM returned no response")
    for attempt in range(3):
        response = llm.chat(messages=messages, system=_SYSTEM, json_mode=True)
        try:
            data = _parse_json(response)
            return DomainSchema(**data)
        except (ValueError, TypeError) as exc:
            last_exc = exc
            if attempt < 2:
                messages = [
                    *messages,
                    Message(role="assistant", content=response),
                    Message(
                        role="user",
                        content=_RETRY_PROMPT.format(error=exc),
                    ),
                ]

    raise last_exc
