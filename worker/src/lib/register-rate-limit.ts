import type { Env } from "./types";

const MAX_REGISTRATIONS_PER_DAY = 5;

/**
 * Check whether an IP has exceeded the daily registration limit.
 * Uses a D1 counter keyed on IP + UTC date.
 * Returns null if allowed, or a 429 Response if rate-limited.
 */
export async function checkRegisterRateLimit(
  request: Request,
  env: Env
): Promise<Response | null> {
  const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

  // Upsert: increment counter for this IP+date, return new count
  const result = await env.DB.prepare(
    `INSERT INTO register_rate_limits (ip, date, count)
     VALUES (?, ?, 1)
     ON CONFLICT (ip, date) DO UPDATE SET count = count + 1
     RETURNING count`
  )
    .bind(ip, today)
    .first<{ count: number }>();

  const count = result?.count ?? 1;

  if (count > MAX_REGISTRATIONS_PER_DAY) {
    return new Response(
      JSON.stringify({
        error: `Rate limit exceeded. Max ${MAX_REGISTRATIONS_PER_DAY} registrations per day.`,
      }),
      {
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": secondsUntilMidnightUTC().toString(),
        },
      }
    );
  }

  return null;
}

function secondsUntilMidnightUTC(): number {
  const now = new Date();
  const midnight = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() + 1
  ));
  return Math.ceil((midnight.getTime() - now.getTime()) / 1000);
}
