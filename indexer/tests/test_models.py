import json

from indexer.models import (
    SegmentMetadata,
    ExtractedFramework,
    ExtractedHeuristic,
    ExtractedExample,
    ExtractedCommunicationPattern,
    ExtractionResult,
    EpisodeMetadata,
)


def test_episode_metadata_from_filename():
    meta = EpisodeMetadata(source_file="transcript_042.md")
    assert meta.source_file == "transcript_042.md"
    assert meta.title is None


def test_segment_metadata_creation():
    seg = SegmentMetadata(
        segment_id="ep-1-seg-0",
        topic="prioritization frameworks",
        speakers=["Lenny", "Shreyas Doshi"],
        content="The LNO framework helps PMs...",
        token_count=150,
    )
    assert seg.segment_id == "ep-1-seg-0"
    assert len(seg.speakers) == 2


def test_extraction_result_with_communication_patterns():
    result = ExtractionResult(
        frameworks=[
            ExtractedFramework(name="LNO", description="Categorize as L, N, or O")
        ],
        heuristics=[ExtractedHeuristic(statement="Small delta means overhead")],
        examples=[
            ExtractedExample(company="Stripe", situation="Treated docs as leverage")
        ],
        communication_patterns=[
            ExtractedCommunicationPattern(
                technique="Lead with the job, not the feature",
                audience="executive",
                example="Instead of 'AI generates drafts', say 'Cut first-draft time by 80%'",
            )
        ],
        applicable_to=["prioritization"],
        key_quote="The best PMs figure out which work actually matters.",
    )
    assert len(result.frameworks) == 1
    assert len(result.communication_patterns) == 1
    assert result.communication_patterns[0].audience == "executive"


def test_extraction_result_to_json():
    result = ExtractionResult(
        frameworks=[],
        heuristics=[],
        examples=[],
        communication_patterns=[],
        applicable_to=["growth"],
        key_quote="Ship it.",
    )
    data = json.loads(result.model_dump_json())
    assert data["key_quote"] == "Ship it."
