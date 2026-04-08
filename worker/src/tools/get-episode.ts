import type { Env, Episode, Segment } from "../lib/types";
import { enrichSegments, escapeLike } from "../db/queries";
import { formatSearchResults } from "../lib/format";

export interface GetEpisodeArgs {
  episode_number?: number;
  guest?: string;
  title?: string;
}

/**
 * Retrieve a full episode by number, guest name, or title keyword.
 * Returns all segments enriched with frameworks, heuristics, etc.
 */
export async function handleGetEpisode(
  args: GetEpisodeArgs,
  env: Env
): Promise<string> {
  if (!args.episode_number && !args.guest && !args.title) {
    return "Please provide an episode number, guest name, or title keyword.";
  }

  // Find the episode
  let episode: Episode | null = null;

  if (args.episode_number) {
    const res = await env.DB
      .prepare(`SELECT * FROM episodes WHERE episode_number = ?1 LIMIT 1`)
      .bind(args.episode_number)
      .first();
    if (res) {
      episode = rowToEpisode(res);
    }
  } else if (args.guest) {
    const res = await env.DB
      .prepare(`SELECT * FROM episodes WHERE guest LIKE ?1 ESCAPE '\\' LIMIT 1`)
      .bind(`%${escapeLike(args.guest)}%`)
      .first();
    if (res) {
      episode = rowToEpisode(res);
    }
  } else if (args.title) {
    const res = await env.DB
      .prepare(`SELECT * FROM episodes WHERE title LIKE ?1 ESCAPE '\\' LIMIT 1`)
      .bind(`%${escapeLike(args.title)}%`)
      .first();
    if (res) {
      episode = rowToEpisode(res);
    }
  }

  if (!episode) {
    return "Episode not found. Try a different search term.";
  }

  // Get all segments for this episode
  const segmentsRes = await env.DB
    .prepare(
      `SELECT id FROM segments WHERE episode_id = ?1 ORDER BY segment_index`
    )
    .bind(episode.id)
    .all();

  const segmentIds = ((segmentsRes.results ?? []) as Array<{ id: string }>).map(
    (r) => r.id
  );

  if (segmentIds.length === 0) {
    return formatEpisodeHeader(episode) + "\n\n*No segments found for this episode.*";
  }

  const results = await enrichSegments(env.DB, segmentIds);

  const header = formatEpisodeHeader(episode);
  const body = formatSearchResults(results, "detailed");

  return `${header}\n\n${body}`;
}

function formatEpisodeHeader(ep: Episode): string {
  const num = ep.episode_number ? ` #${ep.episode_number}` : "";
  const guest = ep.guest ? ` with ${ep.guest}` : "";
  const date = ep.date ? ` (${ep.date})` : "";
  return `# Episode${num}: ${ep.title}${guest}${date}`;
}

function rowToEpisode(row: Record<string, unknown>): Episode {
  return {
    id: row.id as number,
    episode_number: (row.episode_number as number) ?? null,
    title: row.title as string,
    guest: (row.guest as string) ?? null,
    date: (row.date as string) ?? null,
    source_file: row.source_file as string,
    topics: JSON.parse((row.topics as string) || "[]"),
  };
}
