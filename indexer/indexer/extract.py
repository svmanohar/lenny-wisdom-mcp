"""Framework and heuristic extraction using Claude Sonnet."""

import json
import anthropic
from indexer.models import ExtractionResult
from indexer.taxonomy import taxonomy_as_prompt_list, validate_tags

EXTRACTION_PROMPT = """You are extracting structured knowledge from a podcast segment.

For this segment, extract the following as JSON:

1. "frameworks": Named mental models, frameworks, or methodologies discussed.
   Each has: "name", "description", "source_attribution" (who created it),
   "verbatim_definition" (in the guest's own words, if given).

2. "heuristics": Rules of thumb, decision shortcuts, or "if X then Y" guidance.
   These are often unstated — the guest gives advice without naming it.
   Each has: "statement", "context".

3. "examples": Real company stories, case studies, or anecdotes.
   Each has: "company", "situation", "outcome".

4. "communication_patterns": Techniques for explaining, framing, or pitching
   product concepts. These are communication advice — how to say something,
   not what to decide. Each has: "technique" (the advice), "audience"
   (who it's for: executive, engineering, customer, peer-pm, investor, or null
   if general), "example" (verbatim example if given), "source_attribution".
   Look for: storytelling techniques, pitch structures, "don't say X, say Y"
   advice, audience-specific framing, presentation guidance.

5. "applicable_to": Which product decisions this segment helps with.
   Use ONLY tags from this taxonomy: [{taxonomy}]
   Select 1-5 most relevant tags.

6. "key_quote": The single most quotable, reusable line from this segment.
   If nothing stands out, use null.

Rules:
- Be precise. Do NOT invent frameworks that aren't actually discussed.
- For verbatim_definition, use the guest's actual words, not a paraphrase.
- If a category has nothing meaningful, return an empty array.
- Return ONLY valid JSON, no markdown fencing.

Segment to analyze:

{segment}"""


def build_extraction_prompt(segment_content: str) -> str:
    return EXTRACTION_PROMPT.format(
        taxonomy=taxonomy_as_prompt_list(),
        segment=segment_content,
    )


def parse_extraction_response(response: str) -> ExtractionResult:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    data = json.loads(cleaned)
    data["applicable_to"] = validate_tags(data.get("applicable_to", []))
    return ExtractionResult(**data)


async def extract_from_segment(segment_content: str) -> ExtractionResult:
    client = anthropic.AsyncAnthropic()
    prompt = build_extraction_prompt(segment_content)
    message = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_extraction_response(message.content[0].text)
