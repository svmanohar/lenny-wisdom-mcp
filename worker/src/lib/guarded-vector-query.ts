import type { Env, AuthContext, VectorMatch } from "./types";
import { vectorQuery } from "./vector-search";
import { checkAndIncrement } from "./rate-limit";

export class RateLimitError extends Error {
  remaining: number;
  limit: number;
  resetAt: string;

  constructor(result: { remaining: number; limit: number; resetAt: string }) {
    super(
      `Rate limit exceeded (${result.limit} vector searches/day). ` +
        `Resets at ${result.resetAt}. ` +
        `Bring your own Voyage AI key for unlimited access: ` +
        `POST /register with {"label": "...", "voyage_api_key": "pa-..."}`
    );
    this.name = "RateLimitError";
    this.remaining = result.remaining;
    this.limit = result.limit;
    this.resetAt = result.resetAt;
  }
}

/**
 * Rate-limited wrapper around vectorQuery.
 * Checks rate limits for free-tier users, uses BYOK key when available.
 */
export async function guardedVectorQuery(
  env: Env,
  authCtx: AuthContext,
  text: string,
  options: { topK?: number; filter?: Record<string, string> } = {}
): Promise<VectorMatch[]> {
  // Check rate limit (admin/byok always pass)
  const result = await checkAndIncrement(
    env.DB,
    authCtx.tokenId,
    authCtx.tier,
    authCtx.dailyLimit
  );

  if (!result.allowed) {
    throw new RateLimitError(result);
  }

  // Use BYOK key if available
  return vectorQuery(env, text, {
    ...options,
    voyageApiKey: authCtx.voyageApiKey ?? undefined,
  });
}
