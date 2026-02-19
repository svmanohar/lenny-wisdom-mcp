import type { AuthTier } from "./types";

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  limit: number;
  resetAt: string; // ISO date of next reset (midnight UTC)
}

/**
 * Check and atomically increment a token's daily vector search count.
 * Admin and BYOK tiers are always allowed.
 */
export async function checkAndIncrement(
  db: D1Database,
  tokenId: string,
  tier: AuthTier,
  dailyLimit: number
): Promise<RateLimitResult> {
  // Admin and BYOK bypass rate limiting
  if (tier === "admin" || tier === "byok") {
    return { allowed: true, remaining: Infinity, limit: Infinity, resetAt: "" };
  }

  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD UTC
  const tomorrow = nextDay(today);

  // Atomic upsert: insert or increment
  await db
    .prepare(
      `INSERT INTO rate_limits (token_id, date, vector_search_count)
       VALUES (?, ?, 1)
       ON CONFLICT (token_id, date)
       DO UPDATE SET vector_search_count = vector_search_count + 1`
    )
    .bind(tokenId, today)
    .run();

  // Read current count
  const row = await db
    .prepare(
      "SELECT vector_search_count FROM rate_limits WHERE token_id = ? AND date = ?"
    )
    .bind(tokenId, today)
    .first<{ vector_search_count: number }>();

  const count = row?.vector_search_count ?? 1;
  const allowed = count <= dailyLimit;
  const remaining = Math.max(0, dailyLimit - count);

  return {
    allowed,
    remaining,
    limit: dailyLimit,
    resetAt: `${tomorrow}T00:00:00Z`,
  };
}

function nextDay(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}
