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
