import type { Env } from "../lib/types";
import { enrichSegments, findByTag } from "../db/queries";
import { vectorQuery } from "../lib/vector-search";

export interface CoachMeArgs {
  situation: string;
  goal?: string;
  role?: string;
  max_sources?: number;
}

/**
 * Coaching tool: takes a user's situation and returns a structured coaching
 * scaffold built from semantically relevant Lenny's Podcast wisdom.
 *
 * Uses semantic search with tag boosting for role-specific relevance.
 */
export async function handleCoachMe(
  args: CoachMeArgs,
  env: Env
): Promise<string> {
  const maxSources = Math.min(args.max_sources ?? 5, 10);

  // Build search query from situation + goal
  const searchText = [args.situation, args.goal].filter(Boolean).join(". ");

  // Semantic search
  let matches = await vectorQuery(env, searchText, {
    topK: maxSources * 3,
  });

  // Tag boost: if role is provided, boost segments tagged with that role
  if (args.role) {
    const roleSegmentIds = new Set(await findByTag(env.DB, args.role));
    matches = matches.map((m) => ({
      ...m,
      score: roleSegmentIds.has(m.id) ? m.score * 1.3 : m.score,
    }));
    matches.sort((a, b) => b.score - a.score);
  }

  matches = matches.slice(0, maxSources);

  if (matches.length === 0) {
    return "I couldn't find relevant coaching wisdom for this situation. Try rephrasing your situation or goal.";
  }

  const segmentIds = matches.map((m) => m.id);
  const scores = new Map(matches.map((m) => [m.id, m.score]));
  const results = await enrichSegments(env.DB, segmentIds, scores);

  // Build coaching scaffold
  const lines: string[] = [];

  lines.push(`# Coaching: ${truncate(args.situation, 80)}\n`);

  if (args.goal) {
    lines.push(`**Goal:** ${args.goal}\n`);
  }
  if (args.role) {
    lines.push(`**Role context:** ${args.role}\n`);
  }

  // Key frameworks to apply
  const allFrameworks = results.flatMap((r) => r.frameworks);
  if (allFrameworks.length > 0) {
    lines.push(`## Relevant Frameworks\n`);
    const seen = new Set<string>();
    for (const f of allFrameworks) {
      if (seen.has(f.name)) continue;
      seen.add(f.name);
      lines.push(`### ${f.name}`);
      lines.push(f.description);
      if (f.verbatim_definition) {
        lines.push(`> "${f.verbatim_definition}"`);
      }
      lines.push("");
    }
  }

  // Heuristics as actionable advice
  const allHeuristics = results.flatMap((r) => r.heuristics);
  if (allHeuristics.length > 0) {
    lines.push(`## Rules of Thumb\n`);
    const seen = new Set<string>();
    for (const h of allHeuristics) {
      if (seen.has(h.statement)) continue;
      seen.add(h.statement);
      let item = `- ${h.statement}`;
      if (h.context) item += ` *(${h.context})*`;
      lines.push(item);
    }
    lines.push("");
  }

  // Relevant examples as case studies
  const allExamples = results.flatMap((r) => r.examples);
  if (allExamples.length > 0) {
    lines.push(`## Relevant Case Studies\n`);
    for (const e of allExamples.slice(0, 5)) {
      let item = `- **${e.company}**: ${e.situation}`;
      if (e.outcome) item += ` -> ${e.outcome}`;
      lines.push(item);
    }
    lines.push("");
  }

  // Key quotes for inspiration
  const quotes = results
    .filter((r) => r.key_quote)
    .map((r) => ({
      quote: r.key_quote!,
      guest: r.episode?.guest ?? "Unknown",
    }));
  if (quotes.length > 0) {
    lines.push(`## Words of Wisdom\n`);
    for (const q of quotes.slice(0, 3)) {
      lines.push(`> "${q.quote}" -- ${q.guest}`);
      lines.push("");
    }
  }

  // Coaching prompt
  lines.push(`## Reflection Questions\n`);
  lines.push(`Based on the frameworks and heuristics above, consider:`);
  lines.push(`1. Which framework best maps to your current situation?`);
  lines.push(`2. What would the guests above advise as your first step?`);
  lines.push(
    `3. Which heuristic challenges your current approach most directly?`
  );

  // Source attribution
  lines.push(`\n---\n*Sources: ${formatSources(results)}*`);

  return lines.join("\n");
}

function truncate(s: string, len: number): string {
  return s.length > len ? s.slice(0, len) + "..." : s;
}

function formatSources(
  results: Array<{
    episode: { title: string; guest: string | null } | null;
  }>
): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const r of results) {
    if (!r.episode) continue;
    const label = r.episode.guest
      ? `${r.episode.title} (${r.episode.guest})`
      : r.episode.title;
    if (seen.has(label)) continue;
    seen.add(label);
    parts.push(label);
  }
  return parts.join("; ");
}
