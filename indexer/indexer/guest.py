"""Guest profile extraction from episode intro segments using Claude Haiku."""

import json
import anthropic
from indexer.models import GuestProfile

GUEST_EXTRACTION_PROMPT = """Extract a structured guest profile from this podcast intro segment.

The host (Lenny) typically introduces the guest with their current role, past roles,
notable companies, and areas of expertise in the first 1-2 minutes.

Return JSON with these fields:
- "name": Guest's full name
- "current_role": Their current title/position (e.g., "CPO", "CEO", "Partner")
- "current_company": Company where they currently work
- "notable_companies": Array of well-known companies they've worked at or founded
- "domain_expertise": Array of their areas of expertise. Use concise labels from this list
  when applicable: product, growth, engineering, design, marketing, sales, data,
  ai-ml, leadership, strategy, operations, finance, hiring, culture, founders
- "company_stages": Array of company stages they have experience with.
  Use: "pre-seed", "seed", "series-a", "series-b", "growth", "public", "enterprise"
- "industry_verticals": Array of industries they've worked in.
  Use: "B2B", "B2C", "marketplace", "SaaS", "fintech", "healthcare", "media",
  "e-commerce", "social", "developer-tools", "enterprise", "consumer"
- "bio_summary": One sentence summarizing who they are and why they're notable

Rules:
- Only include information explicitly stated in the text
- If a field isn't mentioned, use null (for strings) or empty array (for arrays)
- For notable_companies, include both current and past companies
- Return ONLY valid JSON, no markdown fencing

Intro segment:

{intro}"""


def build_guest_prompt(intro_content: str) -> str:
    return GUEST_EXTRACTION_PROMPT.format(intro=intro_content)


def parse_guest_response(response: str, fallback_name: str | None = None) -> GuestProfile:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    data = json.loads(cleaned)
    if not data.get("name") and fallback_name:
        data["name"] = fallback_name
    return GuestProfile(**data)


async def extract_guest_profile(
    intro_content: str,
    fallback_name: str | None = None,
) -> GuestProfile:
    """Extract guest profile from the intro segment(s) of an episode."""
    client = anthropic.AsyncAnthropic()
    prompt = build_guest_prompt(intro_content)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_guest_response(message.content[0].text, fallback_name)
