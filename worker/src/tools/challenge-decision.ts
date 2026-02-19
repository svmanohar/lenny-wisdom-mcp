import type { Env, AuthContext } from "../lib/types";
import { enrichSegments } from "../db/queries";
import { guardedVectorQuery } from "../lib/guarded-vector-query";

export interface ChallengeDecisionArgs {
  decision: string;
  context?: string;
  alternatives?: string[];
  max_sources?: number;
}

/**
 * Red-team a product or business decision using podcast wisdom.
 * Searches for relevant counterarguments, failure modes, and cautionary tales.
 */
export async function handleChallengeDecision(
  args: ChallengeDecisionArgs,
  env: Env,
  authCtx: AuthContext
): Promise<string> {
  const maxSources = Math.min(args.max_sources ?? 6, 12);

  // Search for wisdom relevant to the decision
  const decisionQuery = `risks problems mistakes failures ${args.decision}`;
  const contextQuery = args.context
    ? `${args.decision} ${args.context}`
    : args.decision;

  // Run two searches: one for counterarguments, one for direct relevance
  const [challengeMatches, contextMatches] = await Promise.all([
    guardedVectorQuery(env, authCtx, decisionQuery, { topK: maxSources }),
    guardedVectorQuery(env, authCtx, contextQuery, { topK: maxSources }),
  ]);

  // Merge and deduplicate
  const allMatches = new Map<string, { id: string; score: number }>();
  for (const m of [...challengeMatches, ...contextMatches]) {
    const existing = allMatches.get(m.id);
    if (!existing || m.score > existing.score) {
      allMatches.set(m.id, { id: m.id, score: m.score });
    }
  }

  const sortedMatches = Array.from(allMatches.values())
    .sort((a, b) => b.score - a.score)
    .slice(0, maxSources);

  if (sortedMatches.length === 0) {
    return "Could not find relevant wisdom to challenge this decision. Try providing more context.";
  }

  const segmentIds = sortedMatches.map((m) => m.id);
  const scores = new Map(sortedMatches.map((m) => [m.id, m.score]));
  const results = await enrichSegments(env.DB, segmentIds, scores);

  // Build red-team analysis
  const lines: string[] = [];

  lines.push(`# Decision Challenge: ${args.decision}\n`);

  if (args.context) {
    lines.push(`**Context:** ${args.context}\n`);
  }

  if (args.alternatives && args.alternatives.length > 0) {
    lines.push(`**Alternatives considered:** ${args.alternatives.join(", ")}\n`);
  }

  // Counterarguments from heuristics
  const allHeuristics = results.flatMap((r) => r.heuristics);
  if (allHeuristics.length > 0) {
    lines.push(`## Potential Blindspots\n`);
    lines.push(
      `These heuristics from experienced operators may challenge your assumptions:\n`
    );
    const seen = new Set<string>();
    for (const h of allHeuristics) {
      if (seen.has(h.statement)) continue;
      seen.add(h.statement);
      let item = `- **"${h.statement}"**`;
      if (h.context) item += ` -- ${h.context}`;
      lines.push(item);
    }
    lines.push("");
  }

  // Cautionary examples
  const allExamples = results.flatMap((r) => r.examples);
  if (allExamples.length > 0) {
    lines.push(`## Cautionary Case Studies\n`);
    lines.push(
      `Real examples that may illuminate risks in your approach:\n`
    );
    for (const e of allExamples.slice(0, 5)) {
      lines.push(`### ${e.company}`);
      lines.push(`**Situation:** ${e.situation}`);
      if (e.outcome) {
        lines.push(`**Outcome:** ${e.outcome}`);
      }
      lines.push("");
    }
  }

  // Relevant frameworks for structured thinking
  const allFrameworks = results.flatMap((r) => r.frameworks);
  if (allFrameworks.length > 0) {
    lines.push(`## Frameworks to Pressure-Test With\n`);
    const seen = new Set<string>();
    for (const f of allFrameworks) {
      if (seen.has(f.name)) continue;
      seen.add(f.name);
      lines.push(`- **${f.name}**: ${f.description}`);
    }
    lines.push("");
  }

  // Key quotes as devil's advocate
  const quotes = results
    .filter((r) => r.key_quote)
    .map((r) => ({
      quote: r.key_quote!,
      guest: r.episode?.guest ?? "Unknown",
    }));
  if (quotes.length > 0) {
    lines.push(`## Devil's Advocate Quotes\n`);
    for (const q of quotes.slice(0, 3)) {
      lines.push(`> "${q.quote}" -- ${q.guest}\n`);
    }
  }

  // Red-team summary
  lines.push(`## Pre-Mortem Prompt\n`);
  lines.push(
    `Imagine it's 6 months from now and this decision has failed. Based on the wisdom above:`
  );
  lines.push(`1. What was the most likely cause of failure?`);
  lines.push(`2. Which heuristic did you ignore that you shouldn't have?`);
  lines.push(`3. What would the guests above have done differently?`);
  if (args.alternatives && args.alternatives.length > 0) {
    lines.push(
      `4. Would any of your alternatives (${args.alternatives.join(", ")}) have avoided this failure?`
    );
  }

  // Source attribution
  const sourceEpisodes = results
    .filter((r) => r.episode)
    .map((r) => {
      const ep = r.episode!;
      return ep.guest ? `${ep.title} (${ep.guest})` : ep.title;
    });
  const uniqueSources = [...new Set(sourceEpisodes)];
  lines.push(`\n---\n*Sources: ${uniqueSources.join("; ")}*`);

  return lines.join("\n");
}
