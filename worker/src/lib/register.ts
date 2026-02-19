import type { Env, AuthTier } from "./types";
import { sha256 } from "./auth";

const VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings";

interface RegisterBody {
  label: string;
  voyage_api_key?: string;
}

interface RegisterResponse {
  token: string;
  tier: AuthTier;
  daily_vector_limit: number | "unlimited";
  setup_command: string;
}

/**
 * Handle POST /register — self-service token registration.
 * Returns a raw token once (never stored), plus setup instructions.
 */
export async function handleRegister(
  request: Request,
  env: Env
): Promise<Response> {
  if (request.method !== "POST") {
    return json({ error: "Method not allowed. Use POST." }, 405);
  }

  let body: RegisterBody;
  try {
    body = (await request.json()) as RegisterBody;
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  if (!body.label || typeof body.label !== "string" || body.label.trim().length === 0) {
    return json({ error: "Missing required field: label" }, 400);
  }

  const label = body.label.trim().slice(0, 100);

  // Determine tier
  let tier: AuthTier = "free";
  let dailyLimit = 20;

  if (body.voyage_api_key) {
    // Validate the Voyage API key with a minimal test call
    const valid = await validateVoyageKey(body.voyage_api_key);
    if (!valid) {
      return json(
        { error: "Invalid Voyage AI API key. Get one at https://dash.voyageai.com/" },
        400
      );
    }
    tier = "byok";
    dailyLimit = 999999; // effectively unlimited
  }

  // Generate token: lw_ + 32 random hex bytes (64 chars)
  const rawBytes = new Uint8Array(32);
  crypto.getRandomValues(rawBytes);
  const token =
    "lw_" +
    Array.from(rawBytes)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

  const tokenHash = await sha256(token);
  const id = crypto.randomUUID();

  // Store in D1
  await env.DB.prepare(
    `INSERT INTO api_tokens (id, token_hash, label, tier, voyage_api_key, daily_limit)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(id, tokenHash, label, tier, body.voyage_api_key ?? null, dailyLimit)
    .run();

  const serverUrl = new URL(request.url).origin;
  const setupCommand = `claude mcp add lenny-wisdom --transport http --url ${serverUrl}/mcp --header "Authorization: Bearer ${token}"`;

  const response: RegisterResponse = {
    token,
    tier,
    daily_vector_limit: tier === "byok" ? "unlimited" : dailyLimit,
    setup_command: setupCommand,
  };

  return json(response, 201);
}

/**
 * Validate a Voyage AI API key by making a minimal embedding request.
 */
async function validateVoyageKey(key: string): Promise<boolean> {
  try {
    const resp = await fetch(VOYAGE_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        input: ["test"],
        model: "voyage-3",
        input_type: "query",
      }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
