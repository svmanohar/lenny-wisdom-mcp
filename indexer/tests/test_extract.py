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
