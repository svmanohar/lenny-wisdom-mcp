import { episodeTitle } from "./episode-label";
import type { SearchResult, Framework, Example } from "./types";

/**
 * Format enriched search results as markdown.
 */
export function formatSearchResults(
  results: SearchResult[],
  format: "concise" | "detailed" = "concise"
): string {
  if (results.length === 0) {
    return "No results found.";
  }

  const sections = results.map((r, i) => {
    const header = formatResultHeader(r, i + 1);
    if (format === "concise") {
      return formatConciseResult(r, header);
    }
    return formatDetailedResult(r, header);
  });

  return sections.join("\n\n---\n\n");
}

/**
 * Format a list of frameworks as markdown.
 */
export function formatFrameworks(frameworks: Framework[]): string {
  if (frameworks.length === 0) {
    return "No frameworks found.";
  }

  return frameworks
    .map((f) => {
      let out = `### ${f.name}\n\n${f.description}`;
      if (f.verbatim_definition) {
        out += `\n\n> "${f.verbatim_definition}"`;
      }
      if (f.source_attribution) {
        out += `\n\n*Source: ${f.source_attribution}*`;
      }
      return out;
    })
    .join("\n\n---\n\n");
}

/**
 * Format a list of examples as markdown.
 */
export function formatExamples(examples: Example[]): string {
  if (examples.length === 0) {
    return "No examples found.";
  }

  return examples
    .map((e) => {
      let out = `### ${e.company}\n\n**Situation:** ${e.situation}`;
      if (e.outcome) {
        out += `\n\n**Outcome:** ${e.outcome}`;
      }
      return out;
    })
    .join("\n\n---\n\n");
}

// ── internal helpers ──

function formatResultHeader(r: SearchResult, index: number): string {
  const ep = r.episode;
  const epLabel = ep
    ? `Episode${ep.episode_number ? ` #${ep.episode_number}` : ""}: ${episodeTitle(ep)}`
    : "Unknown episode";
  const guest = ep?.title && ep.guest ? ` (${ep.guest})` : "";
  const score =
    r.relevance_score > 0 ? ` — relevance: ${r.relevance_score.toFixed(2)}` : "";
  return `## ${index}. ${epLabel}${guest}${score}`;
}

function formatConciseResult(r: SearchResult, header: string): string {
  const lines: string[] = [header];

  lines.push(`**Topic:** ${r.segment.topic}`);

  if (r.key_quote) {
    lines.push(`\n> "${r.key_quote}"`);
  }

  if (r.frameworks.length > 0) {
    const names = r.frameworks.map((f) => f.name).join(", ");
    lines.push(`\n**Frameworks:** ${names}`);
  }

  if (r.heuristics.length > 0) {
    lines.push(`\n**Key heuristics:**`);
    for (const h of r.heuristics.slice(0, 3)) {
      lines.push(`- ${h.statement}`);
    }
  }

  if (r.tags.length > 0) {
    lines.push(`\n*Tags: ${r.tags.join(", ")}*`);
  }

  return lines.join("\n");
}

function formatDetailedResult(r: SearchResult, header: string): string {
  const lines: string[] = [header];

  lines.push(`**Topic:** ${r.segment.topic}`);
  lines.push(`**Speakers:** ${r.segment.speakers.join(", ")}`);

  if (r.key_quote) {
    lines.push(`\n> "${r.key_quote}"`);
  }

  // Content excerpt
  const contentPreview =
    r.segment.content.length > 800
      ? r.segment.content.slice(0, 800) + "..."
      : r.segment.content;
  lines.push(`\n**Content:**\n${contentPreview}`);

  // Frameworks
  if (r.frameworks.length > 0) {
    lines.push(`\n### Frameworks`);
    for (const f of r.frameworks) {
      lines.push(`- **${f.name}**: ${f.description}`);
      if (f.verbatim_definition) {
        lines.push(`  > "${f.verbatim_definition}"`);
      }
    }
  }

  // Heuristics
  if (r.heuristics.length > 0) {
    lines.push(`\n### Heuristics`);
    for (const h of r.heuristics) {
      let item = `- ${h.statement}`;
      if (h.context) {
        item += ` *(${h.context})*`;
      }
      lines.push(item);
    }
  }

  // Examples
  if (r.examples.length > 0) {
    lines.push(`\n### Examples`);
    for (const e of r.examples) {
      let item = `- **${e.company}**: ${e.situation}`;
      if (e.outcome) {
        item += ` → ${e.outcome}`;
      }
      lines.push(item);
    }
  }

  // Communication patterns
  if (r.communication_patterns.length > 0) {
    lines.push(`\n### Communication Patterns`);
    for (const cp of r.communication_patterns) {
      let item = `- **${cp.technique}**`;
      if (cp.audience) {
        item += ` (audience: ${cp.audience})`;
      }
      if (cp.example) {
        item += `: ${cp.example}`;
      }
      lines.push(item);
    }
  }

  if (r.tags.length > 0) {
    lines.push(`\n*Tags: ${r.tags.join(", ")}*`);
  }

  return lines.join("\n");
}
