"""Upload indexed data to Cloudflare D1 and Vectorize."""

import json

import httpx

from indexer.models import (
    EpisodeMetadata,
    ExtractionResult,
    GuestProfile,
    SegmentMetadata,
)

CF_API_BASE = "https://api.cloudflare.com/client/v4"


def build_d1_insert_statements(
    episode: EpisodeMetadata,
    segments: list[SegmentMetadata],
    extractions: list[ExtractionResult],
) -> list[dict]:
    """Build D1 SQL insert statements for an episode and its segments."""
    stmts: list[dict] = []

    stmts.append({
        "sql": (
            "INSERT INTO episodes (episode_number, title, guest, date, source_file, topics) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        "params": [
            episode.episode_number,
            episode.title,
            episode.guest,
            episode.date,
            episode.source_file,
            json.dumps(episode.topics),
        ],
    })

    for seg, ext in zip(segments, extractions):
        stmts.append({
            "sql": (
                "INSERT INTO segments (id, episode_id, segment_index, topic, speakers, content, token_count) "
                "VALUES (?, (SELECT id FROM episodes WHERE source_file = ?), ?, ?, ?, ?, ?)"
            ),
            "params": [
                seg.segment_id,
                episode.source_file,
                int(seg.segment_id.split("-seg-")[1]),
                seg.topic,
                json.dumps(seg.speakers),
                seg.content,
                seg.token_count,
            ],
        })

        for fw in ext.frameworks:
            stmts.append({
                "sql": (
                    "INSERT INTO frameworks (segment_id, name, description, source_attribution, verbatim_definition) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                "params": [seg.segment_id, fw.name, fw.description, fw.source_attribution, fw.verbatim_definition],
            })

        for h in ext.heuristics:
            stmts.append({
                "sql": "INSERT INTO heuristics (segment_id, statement, context) VALUES (?, ?, ?)",
                "params": [seg.segment_id, h.statement, h.context],
            })

        for ex in ext.examples:
            stmts.append({
                "sql": "INSERT INTO examples (segment_id, company, situation, outcome) VALUES (?, ?, ?, ?)",
                "params": [seg.segment_id, ex.company, ex.situation, ex.outcome],
            })

        for cp in ext.communication_patterns:
            stmts.append({
                "sql": (
                    "INSERT INTO communication_patterns (segment_id, technique, audience, example, source_attribution) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                "params": [seg.segment_id, cp.technique, cp.audience, cp.example, cp.source_attribution],
            })

        for tag in ext.applicable_to:
            stmts.append({
                "sql": "INSERT INTO tags (segment_id, tag) VALUES (?, ?)",
                "params": [seg.segment_id, tag],
            })

        if ext.key_quote:
            stmts.append({
                "sql": "INSERT INTO quotes (segment_id, quote, speaker) VALUES (?, ?, ?)",
                "params": [seg.segment_id, ext.key_quote, None],
            })

    return stmts


def build_guest_insert_statement(guest: GuestProfile) -> dict:
    """Build a D1 INSERT OR IGNORE statement for a guest profile."""
    return {
        "sql": (
            "INSERT OR IGNORE INTO guests "
            "(name, current_role, current_company, notable_companies, "
            "domain_expertise, company_stages, industry_verticals, bio_summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        "params": [
            guest.name,
            guest.current_role,
            guest.current_company,
            json.dumps(guest.notable_companies),
            json.dumps(guest.domain_expertise),
            json.dumps(guest.company_stages),
            json.dumps(guest.industry_verticals),
            guest.bio_summary,
        ],
    }


async def upload_to_d1(
    stmts: list[dict],
    account_id: str,
    database_id: str,
    api_token: str,
) -> None:
    """Upload structured data to Cloudflare D1 via REST API.

    The D1 REST API /query endpoint accepts a single {sql, params} object
    per request (not an array). Statements are sent sequentially to
    respect ordering (episode INSERT before dependent segment INSERTs).
    """
    url = f"{CF_API_BASE}/accounts/{account_id}/d1/database/{database_id}/query"
    headers = {"Authorization": f"Bearer {api_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, stmt in enumerate(stmts):
            resp = await client.post(url, headers=headers, json=stmt)
            if not resp.is_success:
                body = resp.text
                raise RuntimeError(
                    f"D1 API error {resp.status_code} on statement {i + 1}/{len(stmts)}: "
                    f"{stmt['sql'][:80]}... — {body}"
                )


async def upload_to_vectorize(
    vectors: list[dict],
    account_id: str,
    index_name: str,
    api_token: str,
) -> None:
    """Upload vectors to Cloudflare Vectorize via NDJSON."""
    url = f"{CF_API_BASE}/accounts/{account_id}/vectorize/v2/indexes/{index_name}/upsert"

    async with httpx.AsyncClient() as client:
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            ndjson = "\n".join(json.dumps(v) for v in batch)
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/x-ndjson",
                },
                content=ndjson,
            )
            resp.raise_for_status()
