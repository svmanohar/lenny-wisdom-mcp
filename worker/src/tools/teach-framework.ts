import { episodeLabel } from "../lib/episode-label";
import type { Env, AuthContext, Framework, SearchResult } from "../lib/types";
import { enrichSegments, searchFrameworks } from "../db/queries";
import { guardedVectorQuery } from "../lib/guarded-vector-query";

export interface TeachFrameworkArgs {
  framework: string;
  depth?: "overview" | "detailed" | "masterclass";
}

/**
 * Deep-dive teaching module for a specific framework or mental model.
 * Finds the framework, gathers all related segments, and builds a
 * multi-guest teaching module with examples and applications.
 */
export async function handleTeachFramework(
  args: TeachFrameworkArgs,
  env: Env,
  authCtx: AuthContext
): Promise<string> {
  const depth = args.depth ?? "detailed";

  // Step 1: Find the framework(s) matching the query
  const frameworks = await searchFrameworks(env.DB, args.framework);

  if (frameworks.length === 0) {
    // Fall back to semantic search
    return await buildSemanticTeaching(args.framework, depth, env, authCtx);
  }

  // Get unique segment IDs from matching frameworks
  const segmentIds = [...new Set(frameworks.map((f) => f.segment_id))];
  const results = await enrichSegments(env.DB, segmentIds);

  // Also do a semantic search for additional context
  const vectorMatches = await guardedVectorQuery(env, authCtx, args.framework, { topK: 5 });
  const vectorSegmentIds = vectorMatches
    .map((m) => m.id)
    .filter((id) => !segmentIds.includes(id));

  let additionalResults: SearchResult[] = [];
  if (vectorSegmentIds.length > 0) {
    additionalResults = await enrichSegments(
      env.DB,
      vectorSegmentIds.slice(0, 5)
    );
  }

  const allResults = [...results, ...additionalResults];

  // Build the teaching module
  return buildTeachingModule(args.framework, frameworks, allResults, depth);
}

function buildTeachingModule(
  frameworkQuery: string,
  frameworks: Framework[],
  results: SearchResult[],
  depth: "overview" | "detailed" | "masterclass"
): string {
  const lines: string[] = [];

  // Primary framework
  const primary = frameworks[0];
  if (!primary) {
    return `No framework found matching "${frameworkQuery}".`;
  }

  lines.push(`# Framework Deep-Dive: ${primary.name}\n`);

  // Definition
  lines.push(`## Definition\n`);
  lines.push(primary.description);
  if (primary.verbatim_definition) {
    lines.push(`\n> "${primary.verbatim_definition}"`);
  }
  if (primary.source_attribution) {
    lines.push(`\n*Attributed to: ${primary.source_attribution}*`);
  }
  lines.push("");

  // Related/variant frameworks
  if (frameworks.length > 1) {
    lines.push(`## Related Frameworks\n`);
    for (const f of frameworks.slice(1)) {
      lines.push(`- **${f.name}**: ${f.description}`);
    }
    lines.push("");
  }

  if (depth === "overview") {
    // Short version: key heuristics + one example
    const heuristics = results.flatMap((r) => r.heuristics).slice(0, 3);
    if (heuristics.length > 0) {
      lines.push(`## Key Takeaways\n`);
      for (const h of heuristics) {
        lines.push(`- ${h.statement}`);
      }
      lines.push("");
    }
    const example = results.flatMap((r) => r.examples)[0];
    if (example) {
      lines.push(
        `## Example: ${example.company}\n${example.situation}${example.outcome ? ` -> ${example.outcome}` : ""}\n`
      );
    }
    return lines.join("\n");
  }

  // Detailed and masterclass: multi-guest perspectives
  const guestPerspectives = new Map<
    string,
    Array<{ topic: string; content: string; quote: string | null }>
  >();
  for (const r of results) {
    const guest = r.episode?.guest ?? "Lenny Rachitsky";
    const arr = guestPerspectives.get(guest) ?? [];
    arr.push({
      topic: r.segment.topic,
      content:
        depth === "masterclass"
          ? r.segment.content
          : r.segment.content.slice(0, 500),
      quote: r.key_quote,
    });
    guestPerspectives.set(guest, arr);
  }

  if (guestPerspectives.size > 0) {
    lines.push(`## Perspectives from Guests\n`);
    for (const [guest, perspectives] of guestPerspectives) {
      lines.push(`### ${guest}\n`);
      for (const p of perspectives) {
        lines.push(`**On "${p.topic}":**`);
        if (p.quote) {
          lines.push(`> "${p.quote}"`);
        }
        if (depth === "masterclass") {
          lines.push(`\n${p.content}\n`);
        }
      }
      lines.push("");
    }
  }

  // Heuristics
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

  // Examples
  const allExamples = results.flatMap((r) => r.examples);
  if (allExamples.length > 0) {
    lines.push(`## Real-World Applications\n`);
    for (const e of allExamples.slice(0, depth === "masterclass" ? 10 : 5)) {
      lines.push(`### ${e.company}`);
      lines.push(`**Situation:** ${e.situation}`);
      if (e.outcome) lines.push(`**Outcome:** ${e.outcome}`);
      lines.push("");
    }
  }

  // Communication patterns
  const allComms = results.flatMap((r) => r.communication_patterns);
  if (allComms.length > 0) {
    lines.push(`## How to Communicate This Framework\n`);
    for (const cp of allComms.slice(0, 5)) {
      let item = `- **${cp.technique}**`;
      if (cp.audience) item += ` (for ${cp.audience})`;
      if (cp.example) item += `: ${cp.example}`;
      lines.push(item);
    }
    lines.push("");
  }

  // Application exercise (masterclass only)
  if (depth === "masterclass") {
    lines.push(`## Application Exercise\n`);
    lines.push(`To internalize the **${primary.name}** framework:`);
    lines.push(`1. Identify a current challenge where this framework applies.`);
    lines.push(
      `2. Apply each heuristic above to your specific situation.`
    );
    lines.push(
      `3. Find the closest case study and note what's similar and different.`
    );
    lines.push(
      `4. Write a one-paragraph memo using the communication patterns above.\n`
    );
  }

  // Sources
  const sourceEpisodes = results
    .filter((r) => r.episode)
    .map((r) => {
      const ep = r.episode!;
      return episodeLabel(ep);
    });
  const uniqueSources = [...new Set(sourceEpisodes)];
  if (uniqueSources.length > 0) {
    lines.push(`---\n*Sources: ${uniqueSources.join("; ")}*`);
  }

  return lines.join("\n");
}

async function buildSemanticTeaching(
  query: string,
  depth: "overview" | "detailed" | "masterclass",
  env: Env,
  authCtx: AuthContext
): Promise<string> {
  const matches = await guardedVectorQuery(env, authCtx, `framework mental model ${query}`, {
    topK: 8,
  });

  if (matches.length === 0) {
    return `No framework or wisdom found for "${query}". Try a different search term.`;
  }

  const segmentIds = matches.map((m) => m.id);
  const results = await enrichSegments(env.DB, segmentIds);

  // Extract any frameworks from these segments
  const frameworks = results.flatMap((r) => r.frameworks);

  if (frameworks.length > 0) {
    return buildTeachingModule(query, frameworks, results, depth);
  }

  // No named frameworks, build a general teaching from the content
  const lines: string[] = [];
  lines.push(`# Teaching Module: ${query}\n`);
  lines.push(
    `*No exact framework match found, but here is relevant wisdom:*\n`
  );

  for (const r of results.slice(0, 5)) {
    const guest = r.episode?.guest ?? "Unknown";
    lines.push(`## ${r.segment.topic} (${guest})\n`);
    if (r.key_quote) {
      lines.push(`> "${r.key_quote}"\n`);
    }
    const content =
      depth === "masterclass"
        ? r.segment.content
        : r.segment.content.slice(0, 400) + "...";
    lines.push(content);
    lines.push("");
  }

  return lines.join("\n");
}
