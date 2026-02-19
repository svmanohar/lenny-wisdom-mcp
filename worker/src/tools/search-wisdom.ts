import type { Env, AuthContext } from "../lib/types";
import { enrichSegments, findByTag } from "../db/queries";
import { guardedVectorQuery } from "../lib/guarded-vector-query";
import { formatSearchResults } from "../lib/format";

export interface SearchWisdomArgs {
  query: string;
  tag_filter?: string;
  max_results?: number;
  format?: "concise" | "detailed";
}

/**
 * Semantic search across all Lenny's Podcast wisdom.
 * Embeds the query via Voyage AI, searches VECTORIZE, optionally
 * filters by tag, enriches from D1, and returns formatted markdown.
 */
export async function handleSearchWisdom(
  args: SearchWisdomArgs,
  env: Env,
  authCtx: AuthContext
): Promise<string> {
  const maxResults = Math.min(args.max_results ?? 5, 20);
  const fmt = args.format ?? "concise";

  // Semantic search via AI embedding + Vectorize
  let matches = await guardedVectorQuery(env, authCtx, args.query, {
    topK: maxResults * 2, // over-fetch to allow for tag filtering
  });

  // Optional tag filter — intersect vector results with tag-matching segment IDs
  if (args.tag_filter) {
    const tagSegmentIds = new Set(await findByTag(env.DB, args.tag_filter));
    matches = matches.filter((m) => tagSegmentIds.has(m.id));
  }

  // Trim to max_results
  matches = matches.slice(0, maxResults);

  if (matches.length === 0) {
    return "No matching wisdom found. Try broadening your query or removing the tag filter.";
  }

  const segmentIds = matches.map((m) => m.id);
  const scores = new Map(matches.map((m) => [m.id, m.score]));

  const results = await enrichSegments(env.DB, segmentIds, scores);

  return formatSearchResults(results, fmt);
}
