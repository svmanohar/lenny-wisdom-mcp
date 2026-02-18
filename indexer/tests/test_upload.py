from indexer.upload import build_d1_insert_statements
from indexer.models import (
    EpisodeMetadata,
    SegmentMetadata,
    ExtractionResult,
    ExtractedFramework,
)


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
    assert any("INSERT INTO episodes" in s["sql"] for s in stmts)


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
    sql_strings = [s["sql"] for s in stmts]
    assert any("INSERT INTO segments" in s for s in sql_strings)
    assert any("INSERT INTO frameworks" in s for s in sql_strings)
    assert any("INSERT INTO tags" in s for s in sql_strings)
    assert any("INSERT INTO quotes" in s for s in sql_strings)


# ── edge-case tests for build_d1_insert_statements ──

from indexer.models import (
    ExtractedHeuristic,
    ExtractedExample,
    ExtractedCommunicationPattern,
)


def test_build_with_communication_patterns():
    """Communication patterns should generate INSERT INTO communication_patterns."""
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
    sql_strings = [s["sql"] for s in stmts]
    cp_stmts = [s for s in stmts if "communication_patterns" in s["sql"]]
    assert len(cp_stmts) == 2
    # First pattern has all fields
    assert cp_stmts[0]["params"][1] == "Lead with the outcome"
    assert cp_stmts[0]["params"][2] == "executive"
    # Second pattern has None for optional fields
    assert cp_stmts[1]["params"][2] is None
    assert cp_stmts[1]["params"][3] is None


def test_build_with_no_segments():
    """Episode with no segments should only produce the episode INSERT."""
    episode = EpisodeMetadata(source_file="empty.md", title="Empty Episode")
    stmts = build_d1_insert_statements(
        episode=episode, segments=[], extractions=[]
    )
    assert len(stmts) == 1
    assert "INSERT INTO episodes" in stmts[0]["sql"]


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
    # Should have episode INSERT + segment INSERT, no enrichment inserts
    sql_strings = [s["sql"] for s in stmts]
    assert any("INSERT INTO episodes" in s for s in sql_strings)
    assert any("INSERT INTO segments" in s for s in sql_strings)
    # No frameworks, heuristics, examples, tags, quotes, or communication_patterns
    assert not any("INSERT INTO frameworks" in s for s in sql_strings)
    assert not any("INSERT INTO heuristics" in s for s in sql_strings)
    assert not any("INSERT INTO examples" in s for s in sql_strings)
    assert not any("INSERT INTO tags" in s for s in sql_strings)
    assert not any("INSERT INTO quotes" in s for s in sql_strings)
    assert not any("INSERT INTO communication_patterns" in s for s in sql_strings)
    # Episode params should have None for optional fields
    ep_stmt = next(s for s in stmts if "INSERT INTO episodes" in s["sql"])
    assert ep_stmt["params"][0] is None  # episode_number
    assert ep_stmt["params"][1] is None  # title
    assert ep_stmt["params"][2] is None  # guest


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
    sql_strings = [s["sql"] for s in stmts]
    assert any("INSERT INTO frameworks" in s for s in sql_strings)
    assert any("INSERT INTO heuristics" in s for s in sql_strings)
    assert any("INSERT INTO examples" in s for s in sql_strings)
    assert any("INSERT INTO communication_patterns" in s for s in sql_strings)
    assert sum(1 for s in sql_strings if "INSERT INTO tags" in s) == 2
    assert any("INSERT INTO quotes" in s for s in sql_strings)
