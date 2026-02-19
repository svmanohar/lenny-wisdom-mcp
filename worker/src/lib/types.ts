export interface Episode {
  id: number;
  episode_number: number | null;
  title: string;
  guest: string | null;
  date: string | null;
  source_file: string;
  topics: string[];
}

export interface Segment {
  id: string;
  episode_id: number;
  segment_index: number;
  topic: string;
  speakers: string[];
  content: string;
  token_count: number | null;
}

export interface Framework {
  id: number;
  segment_id: string;
  name: string;
  description: string;
  source_attribution: string | null;
  verbatim_definition: string | null;
}

export interface Heuristic {
  id: number;
  segment_id: string;
  statement: string;
  context: string | null;
}

export interface Example {
  id: number;
  segment_id: string;
  company: string;
  situation: string;
  outcome: string | null;
}

export interface CommunicationPattern {
  id: number;
  segment_id: string;
  technique: string;
  audience: string | null;
  example: string | null;
  source_attribution: string | null;
}

export interface Guest {
  id: number;
  name: string;
  current_role: string | null;
  current_company: string | null;
  notable_companies: string[];
  domain_expertise: string[];
  company_stages: string[];
  industry_verticals: string[];
  bio_summary: string | null;
}

export interface SearchResult {
  segment: Segment;
  episode: Episode | null;
  frameworks: Framework[];
  heuristics: Heuristic[];
  examples: Example[];
  communication_patterns: CommunicationPattern[];
  tags: string[];
  key_quote: string | null;
  relevance_score: number;
}

export interface Env {
  DB: D1Database;
  VECTORIZE: VectorizeIndex;
  AI: Ai;
  MCP_AUTH_TOKEN: string;
  VOYAGE_API_KEY: string;
  ENCRYPTION_KEY: string;
  MCP_AGENT: DurableObjectNamespace;
}

export type AuthTier = "free" | "byok" | "admin";

export interface AuthContext {
  tokenId: string;
  tier: AuthTier;
  voyageApiKey: string | null;
  dailyLimit: number;
}

/**
 * Result from our vector search helper.
 */
export interface VectorMatch {
  id: string;
  score: number;
}
