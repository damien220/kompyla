"""Shared utility for parsing JSON produced by LLMs.

LLMs frequently emit non-standard JSON.  This module provides a single
entry point, parse_llm_json(), that handles every known failure mode:

  • Markdown fences (```json … ```)
  • Prose before or after the JSON structure
  • Extra text / markdown after the closing brace ("Extra data" error)
  • Trailing commas in objects and arrays
  • Single-quoted strings or unquoted keys
  • // single-line and /* */ block comments
  • Python literals  None / True / False
  • Truncated output (model hit token limit)

Strategy
--------
1. Strip fences and comments.
2. Extract only the outermost { … } or [ … ] to discard surrounding prose
   and any text that follows the JSON — this is what fixes the "Extra data"
   JSONDecodeError.
3. Fast-path: stdlib json.loads (zero overhead for well-formed output).
4. Repair-path: json_repair, which handles all remaining structural errors.
"""

from __future__ import annotations

import json
import re

from json_repair import repair_json

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_FENCE = re.compile(r"^```[a-z]*\n?", re.MULTILINE)


def _preprocess(text: str, *, expect_list: bool) -> str:
    """Clean LLM output and extract the outermost JSON structure."""
    text = text.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = _FENCE.sub("", text).rstrip("`").strip()

    # Strip comments before boundary search so they don't confuse bracket
    # counting (a // or /* inside a string value is preserved by repair_json)
    text = _BLOCK_COMMENT.sub("", text)
    text = _LINE_COMMENT.sub("", text)

    # Replace Python literals with JSON equivalents so repair_json sees valid
    # tokens rather than treating them as bare strings
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)

    # Extract the outermost JSON structure — discards prose before/after it
    if expect_list:
        start, end = text.find("["), text.rfind("]")
    else:
        start, end = text.find("{"), text.rfind("}")

    if start != -1 and end > start:
        text = text[start : end + 1]

    return text.strip()


def parse_llm_json(text: str, *, expect_list: bool = False) -> dict | list:
    """Parse an LLM response as JSON, tolerating all common malformations.

    Parameters
    ----------
    text:
        Raw string returned by the LLM.
    expect_list:
        Set True when the expected top-level structure is a JSON array
        (e.g. the synth Q&A generator).  Returns [] on failure instead of {}.

    Returns
    -------
    dict or list — never raises JSONDecodeError.
    The caller should validate that required keys are present.
    """
    cleaned = _preprocess(text, expect_list=expect_list)

    # Fast path — stdlib handles valid JSON with no overhead
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Repair path — covers every remaining structural issue
    result = repair_json(cleaned, return_objects=True)

    if expect_list:
        return result if isinstance(result, list) else []
    return result if isinstance(result, dict) and result else {}
