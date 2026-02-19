-- Migration: Rate-limit the unauthenticated /register endpoint by IP

CREATE TABLE IF NOT EXISTS register_rate_limits (
    ip TEXT NOT NULL,
    date TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ip, date)
);
