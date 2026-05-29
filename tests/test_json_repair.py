"""Tests for JSON repair across all LLM-parsing modules (no LLM, no network)."""

from __future__ import annotations

import pytest

from kompyla.utils.json_utils import parse_llm_json
from kompyla.schema.generator import _parse_json
from kompyla.compiler.compile import _parse_llm_json as compile_parse
from kompyla.evolver.gaps import _parse_llm_json as gaps_parse
from kompyla.filter.relevance import _parse_llm_json as relevance_parse
from kompyla.synth.generator import _parse_pairs


# ---------------------------------------------------------------------------
# Shared helper — run the same malformed-JSON suite against any parser func
# ---------------------------------------------------------------------------

def _run_object_suite(parse_fn) -> None:
    """Assert parse_fn recovers a dict from every known LLM quirk."""

    # 1. Valid JSON — fast path must not corrupt it
    result = parse_fn('{"key": "value", "num": 42}')
    assert result == {"key": "value", "num": 42}

    # 2. Trailing comma before closing brace
    result = parse_fn('{"a": 1, "b": 2,}')
    assert result["a"] == 1 and result["b"] == 2

    # 3. Trailing comma before closing bracket (nested array)
    result = parse_fn('{"items": ["x", "y",]}')
    assert result["items"] == ["x", "y"]

    # 4. Deeply nested trailing commas
    result = parse_fn('{"outer": {"inner": [1, 2,],},}')
    assert result["outer"]["inner"] == [1, 2]

    # 5. Single-quoted strings
    result = parse_fn("{'key': 'value'}")
    assert result["key"] == "value"

    # 6. Unquoted keys
    result = parse_fn('{key: "value", num: 1}')
    assert result["key"] == "value"

    # 7. Single-line // comments
    result = parse_fn('{\n  "a": 1, // this is a comment\n  "b": 2\n}')
    assert result["a"] == 1 and result["b"] == 2

    # 8. Block /* */ comments
    result = parse_fn('{"a": /* comment */ 1}')
    assert result["a"] == 1

    # 9. Python None / True / False literals
    result = parse_fn('{"flag": True, "missing": None, "ok": False}')
    assert result["flag"] is True
    assert result["missing"] is None
    assert result["ok"] is False

    # 10. Markdown fences around JSON
    result = parse_fn('```json\n{"score": 0.9}\n```')
    assert result["score"] == pytest.approx(0.9)

    # 11. Prose before the JSON object
    result = parse_fn('Sure! Here is the JSON:\n{"title": "Test"}')
    assert result["title"] == "Test"

    # 12. Extra text / markdown AFTER the closing brace ("Extra data" case)
    result = parse_fn(
        '{"title": "Anime"}\n\n**Anime and manga** are forms of mass media...'
    )
    assert result["title"] == "Anime"

    # 13. Combination: fences + trailing commas + single quotes
    result = parse_fn("```\n{'key': 'val', 'list': [1, 2,],}\n```")
    assert result["key"] == "val"
    assert result["list"] == [1, 2]


# ---------------------------------------------------------------------------
# kompyla/utils/json_utils.parse_llm_json  — the single source of truth
# ---------------------------------------------------------------------------

class TestParseJsonUtils:
    def test_all_llm_quirks(self):
        _run_object_suite(parse_llm_json)

    def test_expect_list_valid(self):
        result = parse_llm_json('[{"q": "Q?", "a": "A."}]', expect_list=True)
        assert isinstance(result, list) and len(result) == 1

    def test_expect_list_trailing_comma(self):
        result = parse_llm_json('[{"q": "Q",},]', expect_list=True)
        assert isinstance(result, list)

    def test_expect_list_returns_empty_on_garbage(self):
        result = parse_llm_json("not json", expect_list=True)
        assert result == []

    def test_object_returns_empty_dict_on_garbage(self):
        result = parse_llm_json("not json at all")
        assert result == {}


# ---------------------------------------------------------------------------
# schema/generator._parse_json
# ---------------------------------------------------------------------------

class TestSchemaGeneratorParseJson:
    def test_valid_json(self):
        assert _parse_json('{"domain": "ev"}') == {"domain": "ev"}

    def test_all_llm_quirks(self):
        _run_object_suite(_parse_json)

    def test_raises_on_unparseable(self):
        with pytest.raises((ValueError, Exception)):
            _parse_json("this is not json at all !!!")


# ---------------------------------------------------------------------------
# compiler/compile._parse_llm_json
# ---------------------------------------------------------------------------

class TestCompileParseJson:
    def test_valid_json(self):
        result = compile_parse('{"title": "EV Battery", "confidence": 0.8}')
        assert result["title"] == "EV Battery"

    def test_all_llm_quirks(self):
        _run_object_suite(compile_parse)

    def test_extra_data_after_brace(self):
        """The exact failure mode that triggered the bug report."""
        raw = (
            '{"title": "Anime and Manga", "confidence": 0.9}\n\n'
            "**Anime and manga**, or **animanga**[a] for short, are forms of "
            "mass media produced by the Japanese animation industry."
        )
        result = compile_parse(raw)
        assert result["title"] == "Anime and Manga"

    def test_raises_on_unparseable(self):
        with pytest.raises((ValueError, Exception)):
            compile_parse("not json at all !!!")


# ---------------------------------------------------------------------------
# evolver/gaps._parse_llm_json
# ---------------------------------------------------------------------------

class TestGapsParseJson:
    def test_valid_json(self):
        result = gaps_parse('{"missing_topics": ["topic a", "topic b"]}')
        assert result["missing_topics"] == ["topic a", "topic b"]

    def test_all_llm_quirks(self):
        _run_object_suite(gaps_parse)

    def test_returns_empty_dict_on_empty_repair(self):
        # repair_json on a bare string returns "" → our wrapper returns {}
        result = gaps_parse("{}")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# filter/relevance._parse_llm_json
# ---------------------------------------------------------------------------

class TestRelevanceParseJson:
    def test_valid_json(self):
        result = relevance_parse('{"score": 0.75, "reason": "relevant"}')
        assert result["score"] == pytest.approx(0.75)

    def test_all_llm_quirks(self):
        _run_object_suite(relevance_parse)

    def test_trailing_comma_score(self):
        result = relevance_parse('{"score": 0.6, "reason": "ok",}')
        assert result["score"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# synth/generator._parse_pairs  (expects a JSON *array*)
# ---------------------------------------------------------------------------

class TestSynthParsePairs:
    def test_valid_array(self):
        raw = '[{"question": "What?", "answer": "This."}]'
        pairs = _parse_pairs(raw)
        assert len(pairs) == 1
        assert pairs[0]["question"] == "What?"

    def test_trailing_comma_in_array(self):
        raw = '[{"question": "Q1", "answer": "A1"},]'
        pairs = _parse_pairs(raw)
        assert len(pairs) == 1

    def test_multiple_pairs(self):
        raw = (
            '[{"question": "Q1", "answer": "A1"},'
            ' {"question": "Q2", "answer": "A2",}]'
        )
        pairs = _parse_pairs(raw)
        assert len(pairs) == 2

    def test_fenced_array(self):
        raw = '```json\n[{"question": "Q?", "answer": "A."}]\n```'
        pairs = _parse_pairs(raw)
        assert len(pairs) == 1

    def test_array_embedded_in_prose(self):
        raw = (
            'Here are the Q&A pairs:\n'
            '[{"question": "What is EV?", "answer": "Electric vehicle."}]\n'
            'Hope that helps!'
        )
        pairs = _parse_pairs(raw)
        assert len(pairs) == 1
        assert pairs[0]["answer"] == "Electric vehicle."

    def test_single_quoted_pairs(self):
        raw = "[{'question': 'Q?', 'answer': 'A.'}]"
        pairs = _parse_pairs(raw)
        assert len(pairs) == 1

    def test_returns_empty_list_on_garbage(self):
        pairs = _parse_pairs("this is not json")
        assert pairs == []

    def test_returns_empty_list_on_empty_string(self):
        assert _parse_pairs("") == []
