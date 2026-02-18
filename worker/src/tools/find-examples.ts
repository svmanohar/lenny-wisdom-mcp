import type { Env } from "../lib/types";
import { searchExamples } from "../db/queries";
import { formatExamples } from "../lib/format";

export interface FindExamplesArgs {
  company?: string;
  topic?: string;
  max_results?: number;
}

/**
 * Search for real company stories and case studies.
 * Filter by company name and/or topic tag.
 */
export async function handleFindExamples(
  args: FindExamplesArgs,
  env: Env
): Promise<string> {
  const maxResults = Math.min(args.max_results ?? 10, 50);

  if (!args.company && !args.topic) {
    return "Please provide at least a company name or topic to search for examples.";
  }

  const examples = await searchExamples(env.DB, args.company, args.topic);
  const trimmed = examples.slice(0, maxResults);

  if (trimmed.length === 0) {
    const filters: string[] = [];
    if (args.company) filters.push(`company="${args.company}"`);
    if (args.topic) filters.push(`topic="${args.topic}"`);
    return `No examples found for ${filters.join(" and ")}. Try broader search terms.`;
  }

  const filterDesc: string[] = [];
  if (args.company) filterDesc.push(`company: "${args.company}"`);
  if (args.topic) filterDesc.push(`topic: "${args.topic}"`);
  const header = `# Examples (${filterDesc.join(", ")}) — ${trimmed.length} results\n\n`;

  return header + formatExamples(trimmed);
}
