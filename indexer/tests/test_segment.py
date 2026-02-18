from indexer.segment import build_segmentation_prompt, parse_segmentation_response, _add_segment_overlap, _estimate_tokens
from indexer.models import SegmentMetadata

SAMPLE_TRANSCRIPT = """
Lenny (00:00:00):
Today I'm talking with Shreyas about prioritization.

Shreyas Doshi (00:00:15):
Thanks for having me. I think the biggest mistake PMs make is treating all tasks equally.

Lenny (00:00:30):
Tell me more about that.

Shreyas Doshi (00:00:35):
I use something I call the LNO framework. L is for Leverage, N is Neutral, O is Overhead.

Lenny (00:01:00):
Let's switch gears and talk about career growth.

Shreyas Doshi (00:01:10):
Sure. I think the most important thing for PMs is to develop taste.
"""

SAMPLE_LLM_RESPONSE = """---SEGMENT---
topic: The LNO prioritization framework
speakers: ["Lenny", "Shreyas Doshi"]
Lenny (00:00:00):
Today I'm talking with Shreyas about prioritization.

Shreyas Doshi (00:00:15):
Thanks for having me. I think the biggest mistake PMs make is treating all tasks equally.

Lenny (00:00:30):
Tell me more about that.

Shreyas Doshi (00:00:35):
I use something I call the LNO framework. L is for Leverage, N is Neutral, O is Overhead.
---SEGMENT---
topic: PM career growth and developing taste
speakers: ["Lenny", "Shreyas Doshi"]
Lenny (00:01:00):
Let's switch gears and talk about career growth.

Shreyas Doshi (00:01:10):
Sure. I think the most important thing for PMs is to develop taste."""


def test_build_prompt_includes_transcript():
    prompt = build_segmentation_prompt(SAMPLE_TRANSCRIPT)
    assert "SEGMENT" in prompt
    assert "prioritization" in prompt


def test_parse_response_returns_segments():
    segments = parse_segmentation_response(SAMPLE_LLM_RESPONSE, episode_id="ep-1")
    assert len(segments) == 2
    assert segments[0].topic == "The LNO prioritization framework"
    assert segments[0].segment_id == "ep-1-seg-0"
    assert segments[1].segment_id == "ep-1-seg-1"
    assert "Lenny" in segments[0].speakers
    assert "LNO framework" in segments[0].content


# ── edge-case tests for parse_segmentation_response ──


def test_parse_malformed_json_like_response():
    """Non-segment text (e.g. preamble) should be treated as content or skipped."""
    malformed = "Here is the segmentation:\n{not json}\n---SEGMENT---\ntopic: A topic\nspeakers: [\"Lenny\"]\nSome content here."
    segments = parse_segmentation_response(malformed, episode_id="ep-x")
    # The preamble before the first ---SEGMENT--- has content so it becomes a segment
    # with default topic "untitled"; the real segment follows.
    assert any(s.topic == "A topic" for s in segments)


def test_parse_missing_topic_field():
    """Segment with no topic: line should get 'untitled' default."""
    response = "---SEGMENT---\nspeakers: [\"Lenny\"]\nSome content without topic."
    segments = parse_segmentation_response(response, episode_id="ep-2")
    assert len(segments) == 1
    assert segments[0].topic == "untitled"


def test_parse_missing_speakers_field():
    """Segment with no speakers: line should get empty speakers list."""
    response = "---SEGMENT---\ntopic: A topic\nSome content without speakers."
    segments = parse_segmentation_response(response, episode_id="ep-3")
    assert len(segments) == 1
    assert segments[0].speakers == []
    assert segments[0].topic == "A topic"


def test_parse_empty_segments_array():
    """Empty string or only whitespace should return no segments."""
    assert parse_segmentation_response("", episode_id="ep-4") == []
    assert parse_segmentation_response("   \n\n  ", episode_id="ep-4") == []


def test_parse_segment_no_content():
    """Segment with topic and speakers but no content lines should be skipped."""
    response = "---SEGMENT---\ntopic: Empty segment\nspeakers: [\"Lenny\"]"
    segments = parse_segmentation_response(response, episode_id="ep-5")
    assert len(segments) == 0


def test_parse_extra_unexpected_fields():
    """Extra fields in the response (not topic/speakers) become content lines."""
    response = (
        "---SEGMENT---\n"
        "topic: Known topic\n"
        "speakers: [\"Lenny\"]\n"
        "confidence: 0.95\n"
        "Actual transcript content here."
    )
    segments = parse_segmentation_response(response, episode_id="ep-6")
    assert len(segments) == 1
    assert segments[0].topic == "Known topic"
    # The extra 'confidence:' line and actual content become the content
    assert "confidence: 0.95" in segments[0].content
    assert "Actual transcript content here." in segments[0].content


def test_parse_multiple_segments_ids_are_sequential():
    """Segment IDs should be sequential starting from 0."""
    response = (
        "---SEGMENT---\ntopic: First\nspeakers: [\"A\"]\nContent 1\n"
        "---SEGMENT---\ntopic: Second\nspeakers: [\"B\"]\nContent 2\n"
        "---SEGMENT---\ntopic: Third\nspeakers: [\"C\"]\nContent 3"
    )
    segments = parse_segmentation_response(response, episode_id="ep-7")
    assert len(segments) == 3
    assert segments[0].segment_id == "ep-7-seg-0"
    assert segments[1].segment_id == "ep-7-seg-1"
    assert segments[2].segment_id == "ep-7-seg-2"


def test_parse_token_count_estimated():
    """Token count should be roughly content length / 4."""
    response = "---SEGMENT---\ntopic: Test\nspeakers: [\"A\"]\n" + ("word " * 100)
    segments = parse_segmentation_response(response, episode_id="ep-8")
    assert len(segments) == 1
    content_len = len(segments[0].content)
    assert segments[0].token_count == content_len // 4


# ── tests for segment overlap ──


def _make_segment(content: str, idx: int = 0) -> SegmentMetadata:
    return SegmentMetadata(
        segment_id=f"ep-test-seg-{idx}",
        topic=f"topic {idx}",
        speakers=["A"],
        content=content,
        token_count=_estimate_tokens(content),
    )


def test_overlap_prepends_tail_of_previous_segment():
    """Second segment should start with text from end of first segment."""
    long_content = "word " * 200  # ~1000 chars, well above 300 threshold
    seg0 = _make_segment(long_content.strip(), idx=0)
    seg1 = _make_segment("Next topic content here.", idx=1)
    original_seg1_content = seg1.content

    result = _add_segment_overlap([seg0, seg1])
    assert result[1].content.endswith(original_seg1_content)
    assert len(result[1].content) > len(original_seg1_content)
    # Overlap text should come from the tail of seg0
    assert "word" in result[1].content.split("\n")[0]


def test_overlap_skips_first_segment():
    """First segment should never be modified."""
    long_content = "word " * 200
    seg0 = _make_segment(long_content.strip(), idx=0)
    seg1 = _make_segment("Second segment.", idx=1)
    original_seg0_content = seg0.content

    _add_segment_overlap([seg0, seg1])
    assert seg0.content == original_seg0_content


def test_overlap_skips_when_previous_too_short():
    """No overlap if previous segment content is shorter than overlap_chars."""
    short_content = "Short."  # ~6 chars, well below 300
    seg0 = _make_segment(short_content, idx=0)
    seg1 = _make_segment("Second segment.", idx=1)
    original_seg1_content = seg1.content

    _add_segment_overlap([seg0, seg1])
    assert seg1.content == original_seg1_content


def test_overlap_updates_token_count():
    """Token count should be recalculated after overlap is added."""
    long_content = "word " * 200
    seg0 = _make_segment(long_content.strip(), idx=0)
    seg1 = _make_segment("Next topic.", idx=1)

    _add_segment_overlap([seg0, seg1])
    assert seg1.token_count == _estimate_tokens(seg1.content)


def test_overlap_single_segment_unchanged():
    """A single segment should be returned unchanged."""
    seg0 = _make_segment("Only segment content.", idx=0)
    original = seg0.content

    result = _add_segment_overlap([seg0])
    assert len(result) == 1
    assert result[0].content == original


def test_overlap_empty_list():
    """Empty list should return empty."""
    assert _add_segment_overlap([]) == []


def test_overlap_breaks_at_word_boundary():
    """Overlap text should not start mid-word."""
    # Create content where the 300-char boundary falls mid-word
    long_content = "abcdefghij " * 50  # 550 chars, each word 10 chars + space
    seg0 = _make_segment(long_content.strip(), idx=0)
    seg1 = _make_segment("Next.", idx=1)

    _add_segment_overlap([seg0, seg1])
    # The overlap text should start at a word boundary (first char not mid-word)
    overlap_part = seg1.content.split("\n")[0]
    assert not overlap_part[0].islower() or overlap_part.startswith("abcdefghij")


def test_overlap_applied_in_parse_response():
    """parse_segmentation_response should apply overlap to multi-segment results."""
    # Build a response with two segments, first one long enough for overlap
    first_content = "word " * 200
    response = (
        f"---SEGMENT---\ntopic: First\nspeakers: [\"A\"]\n{first_content}\n"
        f"---SEGMENT---\ntopic: Second\nspeakers: [\"B\"]\nSecond segment content."
    )
    segments = parse_segmentation_response(response, episode_id="ep-overlap")
    assert len(segments) == 2
    # Second segment should contain overlap from first
    assert "Second segment content." in segments[1].content
    assert len(segments[1].content) > len("Second segment content.")
