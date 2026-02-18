import type { Env, VectorMatch } from "./types";

const EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5";

/**
 * Perform a semantic search: embed the text query via Workers AI,
 * then query the Vectorize index with the resulting vector.
 */
export async function vectorQuery(
  env: Env,
  text: string,
  options: { topK?: number; filter?: Record<string, string> } = {}
): Promise<VectorMatch[]> {
  const topK = options.topK ?? 10;

  // Generate embedding for the query text
  const embeddingResponse = await env.AI.run(EMBEDDING_MODEL, {
    text: [text],
  });

  // The response is a union; narrow to the data-bearing variant
  if (!("data" in embeddingResponse) || !embeddingResponse.data) {
    return [];
  }

  const embedding = embeddingResponse.data[0];
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
