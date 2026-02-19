import type { Env, AuthContext } from "./types";

/**
 * SHA-256 hash a string and return hex.
 * Uses the Web Crypto API available in CF Workers.
 */
export async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Authenticate a request. Returns an AuthContext on success,
 * or a 403 Response if authentication fails.
 *
 * Fast path: checks env.MCP_AUTH_TOKEN first (admin, no DB hit).
 * Otherwise: hashes the bearer token and looks it up in api_tokens.
 */
export async function authenticate(
  request: Request,
  env: Env
): Promise<AuthContext | Response> {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return forbidden("Missing bearer token");
  }

  const token = authHeader.slice(7);

  // Fast path: admin token (no DB lookup)
  if (token === env.MCP_AUTH_TOKEN) {
    return {
      tokenId: "admin",
      tier: "admin",
      voyageApiKey: null,
      dailyLimit: Infinity,
    };
  }

  // Look up hashed token in D1
  const hash = await sha256(token);
  const row = await env.DB.prepare(
    "SELECT id, tier, voyage_api_key, daily_limit, is_active FROM api_tokens WHERE token_hash = ?"
  )
    .bind(hash)
    .first<{
      id: string;
      tier: string;
      voyage_api_key: string | null;
      daily_limit: number;
      is_active: number;
    }>();

  if (!row || !row.is_active) {
    return forbidden("Invalid or deactivated token");
  }

  // Fire-and-forget: update last_used_at
  env.DB.prepare("UPDATE api_tokens SET last_used_at = datetime('now') WHERE id = ?")
    .bind(row.id)
    .run()
    .catch(() => {});

  return {
    tokenId: row.id,
    tier: row.tier as AuthContext["tier"],
    voyageApiKey: row.voyage_api_key,
    dailyLimit: row.daily_limit,
  };
}

function forbidden(message: string): Response {
  return new Response(JSON.stringify({ error: "forbidden", message }), {
    status: 403,
    headers: { "Content-Type": "application/json" },
  });
}
