"""Framework and heuristic extraction using Claude Sonnet."""

import asyncio
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


# Module-level shared client — created once, reused across all coroutines.
# anthropic.AsyncAnthropic is thread-safe and asyncio-safe for concurrent use.
_anthropic_client: anthropic.AsyncAnthropic | None = None


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic()
    return _anthropic_client


async def extract_from_segment(
    segment_content: str,
    semaphore: asyncio.Semaphore | None = None,
) -> ExtractionResult:
    """Extract structured knowledge from a single segment.

    Args:
        segment_content: The transcript segment text.
        semaphore: Optional semaphore to cap concurrent Sonnet calls across
                   all episodes. Pass the same semaphore instance to every
                   call so the limit is global, not per-episode.
    """
    client = get_anthropic_client()
    prompt = build_extraction_prompt(segment_content)

    async def _call() -> ExtractionResult:
        message = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_extraction_response(message.content[0].text)

    if semaphore is not None:
        async with semaphore:
            return await _call()
    return await _call()


async def extract_all_segments(
    segment_contents: list[str],
    semaphore: asyncio.Semaphore | None = None,
) -> list[ExtractionResult]:
    """Extract from all segments in an episode concurrently.

    All segment calls for this episode run in parallel (subject to the shared
    semaphore). With 5 segments per episode this cuts per-episode Sonnet time
    from ~5 × 4s = 20s down to ~4s (one Sonnet RTT).
    """
    tasks = [
        extract_from_segment(content, semaphore)
        for content in segment_contents
    ]
    return list(await asyncio.gather(*tasks))
