import type { Env, VectorMatch } from "./types";

const VOYAGE_MODEL = "voyage-3";
const VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings";

/**
 * Perform a semantic search: embed the query text via Voyage AI
 * (matching the indexer's model), then query the Vectorize index.
 */
export async function vectorQuery(
  env: Env,
  text: string,
  options: {
    topK?: number;
    filter?: Record<string, string>;
    voyageApiKey?: string;
  } = {}
): Promise<VectorMatch[]> {
  const topK = options.topK ?? 10;
  const voyageKey = options.voyageApiKey ?? env.VOYAGE_API_KEY;

  // Generate query embedding via Voyage AI REST API
  const response = await fetch(VOYAGE_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${voyageKey}`,
    },
    body: JSON.stringify({
      input: [text],
      model: VOYAGE_MODEL,
      input_type: "query",
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Voyage AI API error ${response.status}: ${body}`);
  }

  const json = (await response.json()) as {
    data: { embedding: number[] }[];
  };

  const embedding = json.data?.[0]?.embedding;
  if (!embedding) {
    return [];
  }

  // Query Vectorize with the embedding vector
  const queryOptions: VectorizeQueryOptions = {
    topK,
    returnMetadata: "all",
  };

  if (options.filter) {
    queryOptions.filter = options.filter;
  }

  const results = await env.VECTORIZE.query(embedding, queryOptions);

  return (results.matches ?? []).map((m) => ({
    id: m.id,
    score: m.score,
  }));
}
