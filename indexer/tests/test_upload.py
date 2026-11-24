from indexer.upload import build_d1_insert_statements, stmts_to_raw_sql, _sql_value
from indexer.models import (
    EpisodeMetadata,
    SegmentMetadata,
    ExtractionResult,
    ExtractedFramework,
)


def _insert_stmts(stmts, table):
    """Return statements that INSERT into the given table (any INSERT variant)."""
    return [s for s in stmts if f"INTO {table}" in s["sql"] and "DELETE" not in s["sql"]]


def test_build_episode_insert():
    episode = EpisodeMetadata(
        source_file="test.md",
        title="Test Episode",
        guest="Test Guest",
        episode_number=1,
    )
    stmts = build_d1_insert_statements(
        episode=episode,
        segments=[],
        extractions=[],
    )
    assert len(_insert_stmts(stmts, "episodes")) == 1


def test_build_segment_and_framework_insert():
    episode = EpisodeMetadata(source_file="test.md", title="Test")
    segment = SegmentMetadata(
        segment_id="ep-1-seg-0",
        topic="Test topic",
        speakers=["Lenny"],
        content="Test content",
        token_count=10,
    )
    extraction = ExtractionResult(
        frameworks=[
            ExtractedFramework(
                name="Test Framework",
                description="A test framework",
            )
        ],
        heuristics=[],
        examples=[],
        applicable_to=["growth"],
        key_quote="Test quote",
    )
    stmts = build_d1_insert_statements(
        episode=episode,
        segments=[segment],
        extractions=[extraction],
    )
    assert len(_insert_stmts(stmts, "segments")) == 1
    assert len(_insert_stmts(stmts, "frameworks")) == 1
    assert len(_insert_stmts(stmts, "tags")) == 1
    assert len(_insert_stmts(stmts, "quotes")) == 1


# ── edge-case tests for build_d1_insert_statements ──

from indexer.models import (
    ExtractedHeuristic,
    ExtractedExample,
    ExtractedCommunicationPattern,
)


def test_build_with_communication_patterns():
    """Communication patterns should generate INSERT statements."""
    episode = EpisodeMetadata(source_file="cp.md", title="Comm Patterns Episode")
    segment = SegmentMetadata(
        segment_id="ep-cp-seg-0",
        topic="Communication",
        speakers=["Lenny", "Guest"],
        content="Discussion about pitching.",
        token_count=20,
    )
    extraction = ExtractionResult(
        frameworks=[],
        heuristics=[],
        examples=[],
        communication_patterns=[
            ExtractedCommunicationPattern(
                technique="Lead with the outcome",
                audience="executive",
                example="We increased retention by 30%",
                source_attribution="Guest",
            ),
            ExtractedCommunicationPattern(
                technique="Use customer quotes",
                audience=None,
                example=None,
                source_attribution=None,
            ),
        ],
        applicable_to=["stakeholder-management"],
        key_quote=None,
    )
    stmts = build_d1_insert_statements(
        episode=episode, segments=[segment], extractions=[extraction]
    )
    cp_stmts = _insert_stmts(stmts, "communication_patterns")
    assert len(cp_stmts) == 2
    # First pattern has all fields
    assert cp_stmts[0]["params"][1] == "Lead with the outcome"
    assert cp_stmts[0]["params"][2] == "executive"
    # Second pattern has None for optional fields
    assert cp_stmts[1]["params"][2] is None
    assert cp_stmts[1]["params"][3] is None


def test_build_with_no_segments():
    """Episode with no segments still cleans up old rows, then inserts the episode only."""
    episode = EpisodeMetadata(source_file="empty.md", title="Empty Episode")
    stmts = build_d1_insert_statements(
        episode=episode, segments=[], extractions=[]
    )
    inserts = [s for s in stmts if "DELETE" not in s["sql"]]
    assert len(inserts) == 1
    assert "INTO episodes" in inserts[0]["sql"]
    assert any(s["sql"] == "DELETE FROM episodes WHERE source_file = ?" for s in stmts)


def test_build_with_all_optional_fields_none():
    """Extraction with all optional fields as None should still produce valid SQL."""
    episode = EpisodeMetadata(
        source_file="none.md",
        title=None,
        guest=None,
        episode_number=None,
        date=None,
    )
    segment = SegmentMetadata(
        segment_id="ep-none-seg-0",
        topic="Minimal segment",
        speakers=[],
        content="Minimal content.",
        token_count=None,
    )
    extraction = ExtractionResult(
        frameworks=[],
        heuristics=[],
        examples=[],
        communication_patterns=[],
        applicable_to=[],
        key_quote=None,
    )
    stmts = build_d1_insert_statements(
        episode=episode, segments=[segment], extractions=[extraction]
    )
    sql_strings = [s["sql"] for s in stmts]
    # Should have cleanup DELETEs + episode INSERT + segment INSERT
    assert len(_insert_stmts(stmts, "episodes")) == 1
    assert len(_insert_stmts(stmts, "segments")) == 1
    # No enrichment inserts
    assert len(_insert_stmts(stmts, "frameworks")) == 0
    assert len(_insert_stmts(stmts, "heuristics")) == 0
    assert len(_insert_stmts(stmts, "examples")) == 0
    assert len(_insert_stmts(stmts, "tags")) == 0
    assert len(_insert_stmts(stmts, "quotes")) == 0
    assert len(_insert_stmts(stmts, "communication_patterns")) == 0
    # Episode params should have None for optional fields
    ep_stmt = _insert_stmts(stmts, "episodes")[0]
    assert ep_stmt["params"][0] is None  # episode_number
    assert ep_stmt["params"][1] is None  # title
    assert ep_stmt["params"][2] is None  # guest


def test_sql_value_escaping():
    """Verify _sql_value handles None, numbers, and strings with quotes."""
    assert _sql_value(None) == "NULL"
    assert _sql_value(42) == "42"
    assert _sql_value(3.14) == "3.14"
    assert _sql_value("hello") == "'hello'"
    assert _sql_value("it's a test") == "'it''s a test'"
    assert _sql_value("O'Brien's \"quote\"") == "'O''Brien''s \"quote\"'"


def test_stmts_to_raw_sql():
    """Verify multi-statement SQL generation with inline params."""
    stmts = [
        {"sql": "DELETE FROM episodes WHERE source_file = ?", "params": ["test.md"]},
        {"sql": "INSERT INTO episodes (title, guest) VALUES (?, ?)", "params": ["It's a show", None]},
    ]
    raw = stmts_to_raw_sql(stmts)
    assert "DELETE FROM episodes WHERE source_file = 'test.md'" in raw
    assert "VALUES ('It''s a show', NULL)" in raw
    assert ";\n" in raw


def test_build_with_full_enrichment():
    """Exercise all enrichment types in a single segment."""
    episode = EpisodeMetadata(source_file="full.md", title="Full Episode")
    segment = SegmentMetadata(
        segment_id="ep-full-seg-0",
        topic="Everything",
        speakers=["Lenny"],
        content="Full content.",
        token_count=10,
    )
    extraction = ExtractionResult(
        frameworks=[ExtractedFramework(name="F1", description="D1")],
        heuristics=[ExtractedHeuristic(statement="H1", context="C1")],
        examples=[ExtractedExample(company="Co", situation="S1", outcome="O1")],
        communication_patterns=[
            ExtractedCommunicationPattern(technique="T1")
        ],
        applicable_to=["growth", "retention"],
        key_quote="A great quote",
    )
    stmts = build_d1_insert_statements(
        episode=episode, segments=[segment], extractions=[extraction]
    )
    assert len(_insert_stmts(stmts, "frameworks")) == 1
    assert len(_insert_stmts(stmts, "heuristics")) == 1
    assert len(_insert_stmts(stmts, "examples")) == 1
    assert len(_insert_stmts(stmts, "communication_patterns")) == 1
    assert len(_insert_stmts(stmts, "tags")) == 2
    assert len(_insert_stmts(stmts, "quotes")) == 1


def test_cleanup_deletes_all_existing_segments_for_episode():
    """Re-segmenting into fewer segments must still remove the old extras.

    Regression: cleanup only deleted the new segment IDs, so leftover
    segments blocked the episode DELETE with a foreign key error.
    """
    import sqlite3
    from pathlib import Path

    schema = (Path(__file__).parents[2] / "worker/src/db/schema.sql").read_text()
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)

    def segs(n):
        return [
            SegmentMetadata(segment_id=f"ep-seg-{i}", topic="t", speakers=["L"], content="c", token_count=1)
            for i in range(n)
        ]

    def exts(n):
        return [
            ExtractionResult(
                frameworks=[ExtractedFramework(name="F", description="d")],
                heuristics=[], examples=[], applicable_to=["growth"], key_quote="q",
            )
            for _ in range(n)
        ]

    episode = EpisodeMetadata(source_file="ep.txt", title="Ep")
    conn.executescript(stmts_to_raw_sql(build_d1_insert_statements(episode, segs(3), exts(3))))
    conn.executescript(stmts_to_raw_sql(build_d1_insert_statements(episode, segs(2), exts(2))))

    assert conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM frameworks").fetchone()[0] == 2
