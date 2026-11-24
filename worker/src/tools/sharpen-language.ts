import { episodeLabel } from "../lib/episode-label";
import type { Env, AuthContext } from "../lib/types";
import { enrichSegments, searchCommunicationPatterns } from "../db/queries";
import { guardedVectorQuery } from "../lib/guarded-vector-query";

export interface SharpenLanguageArgs {
  message: string;
  audience: string;
  context?: string;
  max_sources?: number;
}

/**
 * Audience-aware language coaching using communication patterns
 * from Lenny's Podcast guests. Helps sharpen how you say something
 * based on who you're saying it to.
 */
export async function handleSharpenLanguage(
  args: SharpenLanguageArgs,
  env: Env,
  authCtx: AuthContext
): Promise<string> {
  const maxSources = Math.min(args.max_sources ?? 5, 10);

  // Search for relevant communication patterns and general wisdom
  const [patterns, matches] = await Promise.all([
    searchCommunicationPatterns(env.DB, args.audience, args.context),
    guardedVectorQuery(
      env,
      authCtx,
      `communicating ${args.message} to ${args.audience} ${args.context ?? ""}`,
      { topK: maxSources }
    ),
  ]);

  const segmentIds = matches.map((m) => m.id);

  let results: Awaited<ReturnType<typeof enrichSegments>> = [];
  if (segmentIds.length > 0) {
    const scores = new Map(matches.map((m) => [m.id, m.score]));
    results = await enrichSegments(env.DB, segmentIds, scores);
  }

  const lines: string[] = [];

  lines.push(`# Language Coaching\n`);
  lines.push(`**Your message:** "${args.message}"\n`);
  lines.push(`**Audience:** ${args.audience}\n`);
  if (args.context) {
    lines.push(`**Context:** ${args.context}\n`);
  }

  // Communication patterns matched for this audience
  if (patterns.length > 0) {
    lines.push(`## Communication Patterns for ${args.audience}\n`);
    lines.push(
      `These techniques have been recommended by podcast guests for this type of audience:\n`
    );
    for (const cp of patterns.slice(0, 8)) {
      lines.push(`### ${cp.technique}\n`);
      if (cp.example) {
        lines.push(`**Example:** ${cp.example}`);
      }
      if (cp.source_attribution) {
        lines.push(`*Source: ${cp.source_attribution}*`);
      }
      lines.push("");
    }
  }

  // Relevant heuristics about communication
  const allHeuristics = results.flatMap((r) => r.heuristics);
  if (allHeuristics.length > 0) {
    lines.push(`## Communication Heuristics\n`);
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

  // Additional communication patterns from enriched segments
  const segmentComms = results.flatMap((r) => r.communication_patterns);
  const extraComms = segmentComms.filter(
    (sc) => !patterns.some((p) => p.id === sc.id)
  );
  if (extraComms.length > 0) {
    lines.push(`## Additional Techniques\n`);
    for (const cp of extraComms.slice(0, 5)) {
      let item = `- **${cp.technique}**`;
      if (cp.audience) item += ` (audience: ${cp.audience})`;
      if (cp.example) item += `: ${cp.example}`;
      lines.push(item);
    }
    lines.push("");
  }

  // Quotes about communication
  const quotes = results
    .filter((r) => r.key_quote)
    .map((r) => ({
      quote: r.key_quote!,
      guest: r.episode?.guest ?? "Unknown",
    }));
  if (quotes.length > 0) {
    lines.push(`## Wisdom on Communication\n`);
    for (const q of quotes.slice(0, 3)) {
      lines.push(`> "${q.quote}" -- ${q.guest}\n`);
    }
  }

  // Coaching scaffold
  lines.push(`## Sharpening Checklist\n`);
  lines.push(
    `Apply these questions to refine your message for **${args.audience}**:\n`
  );
  lines.push(`1. **Clarity**: Is the core message obvious in the first sentence?`);
  lines.push(
    `2. **Audience fit**: Does the vocabulary match what ${args.audience} use and expect?`
  );
  lines.push(
    `3. **So what?**: Does the message answer "why should ${args.audience} care?"?`
  );
  lines.push(
    `4. **Action**: Is there a clear next step or ask?`
  );
  lines.push(
    `5. **Proof**: Have you included evidence or examples that resonate with ${args.audience}?`
  );

  // Sources
  const sourceEpisodes = results
    .filter((r) => r.episode)
    .map((r) => {
      const ep = r.episode!;
      return episodeLabel(ep);
    });
  const uniqueSources = [...new Set(sourceEpisodes)];
  if (uniqueSources.length > 0) {
    lines.push(`\n---\n*Sources: ${uniqueSources.join("; ")}*`);
  }

  return lines.join("\n");
}
