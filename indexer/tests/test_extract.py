import json
from indexer.extract import build_extraction_prompt, parse_extraction_response

def test_build_extraction_prompt_includes_taxonomy():
    prompt = build_extraction_prompt("Shreyas explains the LNO framework...")
    assert "prioritization" in prompt
    assert "communication_patterns" in prompt

def test_parse_extraction_response():
    mock_response = json.dumps({
        "frameworks": [{"name": "LNO Framework", "description": "Categorize tasks as Leverage, Neutral, or Overhead",
            "source_attribution": "Shreyas Doshi", "verbatim_definition": "If I do this at A+ vs B-, what's the delta?"}],
        "heuristics": [{"statement": "Small delta means overhead work", "context": "Helping PMs stop over-investing"}],
        "examples": [{"company": "Stripe", "situation": "Treated API documentation as Leverage work", "outcome": "Documentation became competitive moat"}],
        "communication_patterns": [{"technique": "Frame prioritization as impact delta, not importance",
            "audience": "peer-pm", "example": "What's the delta between A+ and B-?", "source_attribution": "Shreyas Doshi"}],
        "applicable_to": ["prioritization", "decision-making", "developer-tools"],
        "key_quote": "That single decision changed how the entire team allocated time.",
    })
    result = parse_extraction_response(mock_response)
    assert result.frameworks[0].name == "LNO Framework"
    assert result.examples[0].company == "Stripe"
    assert len(result.communication_patterns) == 1
    assert "prioritization" in result.applicable_to


# ── edge-case tests for parse_extraction_response ──

import pytest


def test_parse_partial_data_no_frameworks():
    """Response with no frameworks should produce empty list."""
    response = json.dumps({
        "frameworks": [],
        "heuristics": [{"statement": "Ship fast", "context": "early stage"}],
        "examples": [],
        "applicable_to": ["growth"],
        "key_quote": None,
    })
    result = parse_extraction_response(response)
    assert result.frameworks == []
    assert len(result.heuristics) == 1
    assert result.heuristics[0].statement == "Ship fast"


def test_parse_partial_data_no_heuristics():
    """Response with no heuristics should produce empty list."""
    response = json.dumps({
        "frameworks": [{"name": "RICE", "description": "Scoring model"}],
        "heuristics": [],
        "examples": [],
        "applicable_to": [],
        "key_quote": None,
    })
    result = parse_extraction_response(response)
    assert result.heuristics == []
    assert result.frameworks[0].name == "RICE"


def test_parse_empty_extraction():
    """Completely empty extraction (all empty arrays/null)."""
    response = json.dumps({
        "frameworks": [],
        "heuristics": [],
        "examples": [],
        "communication_patterns": [],
        "applicable_to": [],
        "key_quote": None,
    })
    result = parse_extraction_response(response)
    assert result.frameworks == []
    assert result.heuristics == []
    assert result.examples == []
    assert result.communication_patterns == []
    assert result.applicable_to == []
    assert result.key_quote is None


def test_parse_malformed_json():
    """Malformed JSON should raise an error."""
    with pytest.raises(Exception):
        parse_extraction_response("{not valid json}")


def test_parse_json_with_markdown_fencing():
    """Response wrapped in markdown code fences should be cleaned."""
    inner = json.dumps({
        "frameworks": [],
        "heuristics": [],
        "examples": [],
        "applicable_to": ["growth"],
        "key_quote": "Test quote",
    })
    fenced = f"```json\n{inner}\n```"
    result = parse_extraction_response(fenced)
    assert result.key_quote == "Test quote"
    assert "growth" in result.applicable_to


def test_parse_communication_patterns_present():
    """Communication patterns should be fully parsed when present."""
    response = json.dumps({
        "frameworks": [],
        "heuristics": [],
        "examples": [],
        "communication_patterns": [
            {
                "technique": "Use analogies to explain complex concepts",
                "audience": "executive",
                "example": "Think of it like a flywheel",
                "source_attribution": "Guest Name",
            },
            {
                "technique": "Lead with the outcome",
                "audience": None,
                "example": None,
                "source_attribution": None,
            },
        ],
        "applicable_to": ["stakeholder-management"],
        "key_quote": None,
    })
    result = parse_extraction_response(response)
    assert len(result.communication_patterns) == 2
    assert result.communication_patterns[0].technique == "Use analogies to explain complex concepts"
    assert result.communication_patterns[0].audience == "executive"
    assert result.communication_patterns[1].audience is None
    assert result.communication_patterns[1].example is None


def test_parse_invalid_tags_are_filtered():
    """Tags not in the taxonomy should be filtered out by validate_tags."""
    response = json.dumps({
        "frameworks": [],
        "heuristics": [],
        "examples": [],
        "applicable_to": ["prioritization", "not-a-real-tag", "growth"],
        "key_quote": None,
    })
    result = parse_extraction_response(response)
    assert "not-a-real-tag" not in result.applicable_to
    assert "prioritization" in result.applicable_to
