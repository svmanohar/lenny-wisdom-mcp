-- Episodes: one row per podcast episode
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_number INTEGER,
    title TEXT NOT NULL,
    guest TEXT,
    date TEXT,
    source_file TEXT NOT NULL UNIQUE,
    topics TEXT  -- JSON array of top-level topics
);

-- Segments: topic-based chunks of each episode
CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,  -- e.g., "ep-247-seg-14"
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    segment_index INTEGER NOT NULL,
    topic TEXT NOT NULL,
    speakers TEXT NOT NULL,  -- JSON array
    content TEXT NOT NULL,
    token_count INTEGER,
    UNIQUE(episode_id, segment_index)
);

-- Frameworks: named mental models extracted from segments
CREATE TABLE IF NOT EXISTS frameworks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL REFERENCES segments(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    source_attribution TEXT,
    verbatim_definition TEXT,
    UNIQUE(segment_id, name)
);

-- Heuristics: rules of thumb, decision shortcuts
CREATE TABLE IF NOT EXISTS heuristics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL REFERENCES segments(id),
    statement TEXT NOT NULL,
    context TEXT
);

-- Examples: real company stories and case studies
CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL REFERENCES segments(id),
    company TEXT NOT NULL,
    situation TEXT NOT NULL,
    outcome TEXT
);

-- Communication patterns: framing techniques for different audiences (Mod A)
CREATE TABLE IF NOT EXISTS communication_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL REFERENCES segments(id),
    technique TEXT NOT NULL,
    audience TEXT,
    example TEXT,
    source_attribution TEXT
);

-- Tags: applicable_to taxonomy tags per segment
CREATE TABLE IF NOT EXISTS tags (
    segment_id TEXT NOT NULL REFERENCES segments(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (segment_id, tag)
);

-- Key quotes: one standout quote per segment
CREATE TABLE IF NOT EXISTS quotes (
    segment_id TEXT PRIMARY KEY REFERENCES segments(id),
    quote TEXT NOT NULL,
    speaker TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_segments_episode ON segments(episode_id);
CREATE INDEX IF NOT EXISTS idx_frameworks_name ON frameworks(name);
CREATE INDEX IF NOT EXISTS idx_examples_company ON examples(company);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_episodes_guest ON episodes(guest);
CREATE INDEX IF NOT EXISTS idx_comms_audience ON communication_patterns(audience);
CREATE INDEX IF NOT EXISTS idx_comms_segment ON communication_patterns(segment_id);
