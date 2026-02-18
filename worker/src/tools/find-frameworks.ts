import type { Env } from "../lib/types";
import { searchFrameworks } from "../db/queries";
import { formatFrameworks } from "../lib/format";

export interface FindFrameworksArgs {
  query: string;
  max_results?: number;
}

/**
 * Search for named frameworks and mental models by keyword.
 * Uses LIKE search on framework name and description.
 */
export async function handleFindFrameworks(
  args: FindFrameworksArgs,
  env: Env
): Promise<string> {
  const maxResults = Math.min(args.max_results ?? 10, 50);

  const frameworks = await searchFrameworks(env.DB, args.query);
  const trimmed = frameworks.slice(0, maxResults);

  if (trimmed.length === 0) {
    return `No frameworks found matching "${args.query}". Try a broader search term.`;
  }

  const header = `# Frameworks matching "${args.query}" (${trimmed.length} results)\n\n`;
  return header + formatFrameworks(trimmed);
}
