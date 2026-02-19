-- Migration: Add self-service API tokens and rate limiting tables

CREATE TABLE IF NOT EXISTS api_tokens (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'free',
    voyage_api_key TEXT,
    daily_limit INTEGER NOT NULL DEFAULT 20,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rate_limits (
    token_id TEXT NOT NULL REFERENCES api_tokens(id),
    date TEXT NOT NULL,
    vector_search_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_id, date)
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
