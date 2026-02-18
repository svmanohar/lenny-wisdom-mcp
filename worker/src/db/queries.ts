import type {
  Episode,
  Segment,
  Framework,
  Heuristic,
  Example,
  CommunicationPattern,
  SearchResult,
} from "../lib/types";

/**
 * Batch-fetch segments and all related data (frameworks, heuristics, examples,
 * communication_patterns, tags, quotes, episodes) for a list of segment IDs.
 */
export async function enrichSegments(
  db: D1Database,
  segmentIds: string[],
  scores?: Map<string, number>
): Promise<SearchResult[]> {
  if (segmentIds.length === 0) return [];

  const placeholders = segmentIds.map(() => "?").join(", ");

  const [
    segmentsRes,
    frameworksRes,
    heuristicsRes,
    examplesRes,
    commsRes,
    tagsRes,
    quotesRes,
  ] = await Promise.all([
    db
      .prepare(
        `SELECT s.*, e.id AS ep_id, e.episode_number, e.title AS ep_title,
                e.guest, e.date, e.source_file, e.topics AS ep_topics
         FROM segments s
         JOIN episodes e ON s.episode_id = e.id
         WHERE s.id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
    db
      .prepare(
        `SELECT * FROM frameworks WHERE segment_id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
    db
      .prepare(
        `SELECT * FROM heuristics WHERE segment_id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
    db
      .prepare(
        `SELECT * FROM examples WHERE segment_id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
    db
      .prepare(
        `SELECT * FROM communication_patterns WHERE segment_id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
    db
      .prepare(
        `SELECT * FROM tags WHERE segment_id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
    db
      .prepare(
        `SELECT * FROM quotes WHERE segment_id IN (${placeholders})`
      )
      .bind(...segmentIds)
      .all(),
  ]);

  // Index related data by segment_id
  const frameworksBySegment = groupBySegmentId<Framework>(
    frameworksRes.results as Record<string, unknown>[]
  );
  const heuristicsBySegment = groupBySegmentId<Heuristic>(
    heuristicsRes.results as Record<string, unknown>[]
  );
  const examplesBySegment = groupBySegmentId<Example>(
    examplesRes.results as Record<string, unknown>[]
  );
  const commsBySegment = groupBySegmentId<CommunicationPattern>(
    commsRes.results as Record<string, unknown>[]
  );

  const tagsBySegment = new Map<string, string[]>();
  for (const row of (tagsRes.results ?? []) as Record<string, unknown>[]) {
    const segId = row["segment_id"] as string;
    const tag = row["tag"] as string;
    const arr = tagsBySegment.get(segId) ?? [];
    arr.push(tag);
    tagsBySegment.set(segId, arr);
  }

  const quoteBySegment = new Map<string, string>();
  for (const row of (quotesRes.results ?? []) as Record<string, unknown>[]) {
    quoteBySegment.set(row["segment_id"] as string, row["quote"] as string);
  }

  // Build SearchResult for each segment, preserving input order
  const segmentMap = new Map<string, Record<string, unknown>>();
  for (const row of (segmentsRes.results ?? []) as Record<string, unknown>[]) {
    segmentMap.set(row["id"] as string, row);
  }

  const results: SearchResult[] = [];

  for (const sid of segmentIds) {
    const row = segmentMap.get(sid);
    if (!row) continue;

    const segment: Segment = {
      id: row["id"] as string,
      episode_id: row["episode_id"] as number,
      segment_index: row["segment_index"] as number,
      topic: row["topic"] as string,
      speakers: JSON.parse((row["speakers"] as string) || "[]"),
      content: row["content"] as string,
      token_count: (row["token_count"] as number) ?? null,
    };

    const episode: Episode = {
      id: row["ep_id"] as number,
      episode_number: (row["episode_number"] as number) ?? null,
      title: row["ep_title"] as string,
      guest: (row["guest"] as string) ?? null,
      date: (row["date"] as string) ?? null,
      source_file: row["source_file"] as string,
      topics: JSON.parse((row["ep_topics"] as string) || "[]"),
    };

    results.push({
      segment,
      episode,
      frameworks: frameworksBySegment.get(sid) ?? [],
      heuristics: heuristicsBySegment.get(sid) ?? [],
      examples: examplesBySegment.get(sid) ?? [],
      communication_patterns: commsBySegment.get(sid) ?? [],
      tags: tagsBySegment.get(sid) ?? [],
      key_quote: quoteBySegment.get(sid) ?? null,
      relevance_score: scores?.get(sid) ?? 0,
    });
  }

  return results;
}

/**
 * LIKE search for frameworks by name or description.
 */
export async function searchFrameworks(
  db: D1Database,
  query: string
): Promise<Framework[]> {
  const pattern = `%${query}%`;
  const res = await db
    .prepare(
      `SELECT * FROM frameworks
       WHERE name LIKE ?1 OR description LIKE ?1
       ORDER BY name
       LIMIT 50`
    )
    .bind(pattern)
    .all();
  return (res.results ?? []) as unknown as Framework[];
}

/**
 * Search examples by company name and/or topic tag.
 */
export async function searchExamples(
  db: D1Database,
  company?: string,
  topic?: string
): Promise<Example[]> {
  if (company && topic) {
    const res = await db
      .prepare(
        `SELECT e.* FROM examples e
         JOIN tags t ON e.segment_id = t.segment_id
         WHERE e.company LIKE ?1 AND t.tag LIKE ?2
         ORDER BY e.company
         LIMIT 50`
      )
      .bind(`%${company}%`, `%${topic}%`)
      .all();
    return (res.results ?? []) as unknown as Example[];
  }
  if (company) {
    const res = await db
      .prepare(
        `SELECT * FROM examples WHERE company LIKE ?1 ORDER BY company LIMIT 50`
      )
      .bind(`%${company}%`)
      .all();
    return (res.results ?? []) as unknown as Example[];
  }
  if (topic) {
    const res = await db
      .prepare(
        `SELECT e.* FROM examples e
         JOIN tags t ON e.segment_id = t.segment_id
         WHERE t.tag LIKE ?1
         ORDER BY e.company
         LIMIT 50`
      )
      .bind(`%${topic}%`)
      .all();
    return (res.results ?? []) as unknown as Example[];
  }
  // No filters — return recent examples
  const res = await db
    .prepare(`SELECT * FROM examples ORDER BY id DESC LIMIT 50`)
    .all();
  return (res.results ?? []) as unknown as Example[];
}

/**
 * Get all segment IDs that have a given tag.
 */
export async function findByTag(
  db: D1Database,
  tag: string
): Promise<string[]> {
  const res = await db
    .prepare(`SELECT segment_id FROM tags WHERE tag = ?1`)
    .bind(tag)
    .all();
  return ((res.results ?? []) as Record<string, unknown>[]).map(
    (r) => r["segment_id"] as string
  );
}

/**
 * List guests with episode counts, optionally filtered by topic.
 */
export async function listGuests(
  db: D1Database,
  topic?: string
): Promise<Array<{ guest: string; episode_count: number; episodes: string[] }>> {
  let sql: string;
  let params: string[];

  if (topic) {
    sql = `SELECT e.guest, e.title
           FROM episodes e
           JOIN segments s ON s.episode_id = e.id
           JOIN tags t ON t.segment_id = s.id
           WHERE e.guest IS NOT NULL AND t.tag LIKE ?1
           GROUP BY e.id, e.guest, e.title
           ORDER BY e.guest`;
    params = [`%${topic}%`];
  } else {
    sql = `SELECT guest, title FROM episodes
           WHERE guest IS NOT NULL
           ORDER BY guest`;
    params = [];
  }

  const res = await db
    .prepare(sql)
    .bind(...params)
    .all();

  const guestMap = new Map<
    string,
    { guest: string; titles: Set<string> }
  >();
  for (const row of (res.results ?? []) as Record<string, unknown>[]) {
    const guest = row["guest"] as string;
    const title = row["title"] as string;
    const entry = guestMap.get(guest) ?? {
      guest,
      titles: new Set<string>(),
    };
    entry.titles.add(title);
    guestMap.set(guest, entry);
  }

  return Array.from(guestMap.values()).map((entry) => ({
    guest: entry.guest,
    episode_count: entry.titles.size,
    episodes: Array.from(entry.titles),
  }));
}

/**
 * Search communication patterns by audience and/or free-text query.
 */
export async function searchCommunicationPatterns(
  db: D1Database,
  audience?: string,
  query?: string
): Promise<CommunicationPattern[]> {
  if (audience && query) {
    const res = await db
      .prepare(
        `SELECT * FROM communication_patterns
         WHERE audience LIKE ?1
           AND (technique LIKE ?2 OR example LIKE ?2)
         ORDER BY id
         LIMIT 50`
      )
      .bind(`%${audience}%`, `%${query}%`)
      .all();
    return (res.results ?? []) as unknown as CommunicationPattern[];
  }
  if (audience) {
    const res = await db
      .prepare(
        `SELECT * FROM communication_patterns
         WHERE audience LIKE ?1
         ORDER BY id
         LIMIT 50`
      )
      .bind(`%${audience}%`)
      .all();
    return (res.results ?? []) as unknown as CommunicationPattern[];
  }
  if (query) {
    const pattern = `%${query}%`;
    const res = await db
      .prepare(
        `SELECT * FROM communication_patterns
         WHERE technique LIKE ?1 OR example LIKE ?1
         ORDER BY id
         LIMIT 50`
      )
      .bind(pattern)
      .all();
    return (res.results ?? []) as unknown as CommunicationPattern[];
  }
  const res = await db
    .prepare(
      `SELECT * FROM communication_patterns ORDER BY id DESC LIMIT 50`
    )
    .all();
  return (res.results ?? []) as unknown as CommunicationPattern[];
}

// ── helpers ──

function groupBySegmentId<T>(
  rows: Record<string, unknown>[]
): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const row of rows) {
    const key = row["segment_id"] as string;
    const arr = map.get(key) ?? [];
    arr.push(row as unknown as T);
    map.set(key, arr);
  }
  return map;
}
