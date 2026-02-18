import type { Env } from "../lib/types";
import { listGuests } from "../db/queries";

export interface ListGuestsArgs {
  topic?: string;
  max_results?: number;
}

/**
 * List podcast guests with episode counts, optionally filtered by topic.
 */
export async function handleListGuests(
  args: ListGuestsArgs,
  env: Env
): Promise<string> {
  const maxResults = Math.min(args.max_results ?? 25, 100);

  const guests = await listGuests(env.DB, args.topic);
  const trimmed = guests.slice(0, maxResults);

  if (trimmed.length === 0) {
    const qualifier = args.topic ? ` related to "${args.topic}"` : "";
    return `No guests found${qualifier}.`;
  }

  const topicLabel = args.topic ? ` (topic: "${args.topic}")` : "";
  const lines: string[] = [
    `# Podcast Guests${topicLabel} — ${trimmed.length} results\n`,
  ];

  for (const g of trimmed) {
    const episodeList = g.episodes.map((t) => `"${t}"`).join(", ");
    lines.push(
      `- **${g.guest}** — ${g.episode_count} episode${g.episode_count !== 1 ? "s" : ""}: ${episodeList}`
    );
  }

  return lines.join("\n");
}
