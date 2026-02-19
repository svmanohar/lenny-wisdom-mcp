"""Upload indexed data to Cloudflare D1 and Vectorize."""

import asyncio
import json

import httpx

from indexer.models import (
    EpisodeMetadata,
    ExtractionResult,
    GuestProfile,
    SegmentMetadata,
)

CF_API_BASE = "https://api.cloudflare.com/client/v4"

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 3, 10]  # seconds between retries
D1_UPLOAD_CONCURRENCY = 5  # concurrent episode uploads to D1


def _sql_value(v) -> str:
    """Escape a Python value for inline SQL. Returns SQL literal string."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    # Escape single quotes by doubling them
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _build_cleanup_stmts(source_file: str, segment_ids: list[str]) -> list[dict]:
    """Build DELETE statements to remove existing data for an episode.

    Runs before inserts so re-runs are idempotent without duplicating rows.
    Order: child tables first, then segments, then episode.
    """
    stmts: list[dict] = []
    if not segment_ids:
        return stmts

    placeholders = ", ".join("?" for _ in segment_ids)
    for table in ("frameworks", "heuristics", "examples", "communication_patterns", "tags", "quotes"):
        stmts.append({
            "sql": f"DELETE FROM {table} WHERE segment_id IN ({placeholders})",
            "params": list(segment_ids),
        })
    stmts.append({
        "sql": f"DELETE FROM segments WHERE id IN ({placeholders})",
        "params": list(segment_ids),
    })
    stmts.append({
        "sql": "DELETE FROM episodes WHERE source_file = ?",
        "params": [source_file],
    })
    return stmts


def build_d1_insert_statements(
    episode: EpisodeMetadata,
    segments: list[SegmentMetadata],
    extractions: list[ExtractionResult],
) -> list[dict]:
    """Build D1 SQL statements for an episode and its segments.

    Starts with DELETE statements to clean up any existing data for this
    episode, making re-runs idempotent.
    """
    segment_ids = [seg.segment_id for seg in segments]
    stmts = _build_cleanup_stmts(episode.source_file, segment_ids)

    stmts.append({
        "sql": (
            "INSERT OR REPLACE INTO episodes (episode_number, title, guest, date, source_file, topics) "
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
                "INSERT OR REPLACE INTO segments (id, episode_id, segment_index, topic, speakers, content, token_count) "
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
                "sql": "INSERT OR IGNORE INTO tags (segment_id, tag) VALUES (?, ?)",
                "params": [seg.segment_id, tag],
            })

        if ext.key_quote:
            stmts.append({
                "sql": "INSERT OR REPLACE INTO quotes (segment_id, quote, speaker) VALUES (?, ?, ?)",
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


def stmts_to_raw_sql(stmts: list[dict]) -> str:
    """Convert parameterized statements into a raw multi-statement SQL string.

    D1's REST API executes multi-statement SQL (semicolon-separated) atomically
    in a single request, but doesn't support params with multiple statements.
    This inlines all parameter values safely using SQL escaping.
    """
    parts = []
    for stmt in stmts:
        sql = stmt["sql"]
        params = stmt.get("params", [])
        if not params:
            parts.append(sql)
            continue
        # Replace each ? placeholder with the inline value
        result = []
        param_idx = 0
        for char in sql:
            if char == "?" and param_idx < len(params):
                result.append(_sql_value(params[param_idx]))
                param_idx += 1
            else:
                result.append(char)
        parts.append("".join(result))
    return ";\n".join(parts)


async def _send_sql_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    sql: str,
    label: str,
) -> None:
    """Send a raw multi-statement SQL string to D1 with retry."""
    payload = {"sql": sql}
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.is_success:
                # Check for per-statement errors in the response
                results = resp.json().get("result", [])
                for i, r in enumerate(results):
                    if not r.get("success", True):
                        raise RuntimeError(
                            f"D1 statement {i} failed on {label}: {r}"
                        )
                return
            is_server_error = resp.status_code >= 500
            is_d1_transient = (
                resp.status_code == 400
                and '"code":7500' in resp.text
                and "SQLITE_CONSTRAINT" not in resp.text
            )
            if (is_server_error or is_d1_transient) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
                continue
            raise RuntimeError(
                f"D1 API error {resp.status_code} on {label}: {resp.text[:300]}"
            )
        except httpx.TransportError as exc:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
                continue
            raise RuntimeError(f"D1 transport error on {label}: {exc}") from exc


async def upload_episode_stmts(
    stmts: list[dict],
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    episode_label: str,
) -> None:
    """Upload one episode's statements as a single multi-statement SQL call.

    Combines all statements into one semicolon-separated SQL string with
    inline values. D1 executes this atomically, avoiding FK timing issues.
    """
    raw_sql = stmts_to_raw_sql(stmts)
    await _send_sql_with_retry(client, url, headers, raw_sql, episode_label)


async def upload_to_d1(
    episode_stmt_groups: list[list[dict]],
    account_id: str,
    database_id: str,
    api_token: str,
) -> None:
    """Upload structured data to Cloudflare D1 via REST API.

    Takes a list of statement groups (one group per episode). Each group
    is sent as a single multi-statement SQL call (atomic execution).
    Different episodes upload concurrently with a semaphore.
    """
    url = f"{CF_API_BASE}/accounts/{account_id}/d1/database/{database_id}/query"
    headers = {"Authorization": f"Bearer {api_token}"}
    sem = asyncio.Semaphore(D1_UPLOAD_CONCURRENCY)

    async def _upload_group(idx: int, stmts: list[dict]) -> None:
        async with sem:
            await upload_episode_stmts(stmts, client, url, headers, f"episode-{idx}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        await asyncio.gather(
            *[_upload_group(i, group) for i, group in enumerate(episode_stmt_groups)]
        )


async def upload_to_vectorize(
    vectors: list[dict],
    account_id: str,
    index_name: str,
    api_token: str,
) -> None:
    """Upload vectors to Cloudflare Vectorize via NDJSON."""
    url = f"{CF_API_BASE}/accounts/{account_id}/vectorize/v2/indexes/{index_name}/upsert"

    async with httpx.AsyncClient(timeout=60.0) as client:
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            ndjson = "\n".join(json.dumps(v) for v in batch)
            for attempt in range(MAX_RETRIES):
                try:
                    resp = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {api_token}",
                            "Content-Type": "application/x-ndjson",
                        },
                        content=ndjson,
                    )
                    if resp.is_success:
                        break
                    if resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    resp.raise_for_status()
                except httpx.TransportError:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    raise
