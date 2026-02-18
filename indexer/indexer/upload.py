"""Upload indexed data to Cloudflare D1 and Vectorize."""

import json

import httpx

from indexer.models import (
    EpisodeMetadata,
    ExtractionResult,
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


async def upload_to_d1(
    stmts: list[dict],
    account_id: str,
    database_id: str,
    api_token: str,
) -> None:
    """Upload structured data to Cloudflare D1 via REST API."""
    url = f"{CF_API_BASE}/accounts/{account_id}/d1/database/{database_id}/query"

    async with httpx.AsyncClient() as client:
        batch_size = 100
        for i in range(0, len(stmts), batch_size):
            batch = stmts[i : i + batch_size]
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_token}"},
                json=batch,
            )
            resp.raise_for_status()


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
