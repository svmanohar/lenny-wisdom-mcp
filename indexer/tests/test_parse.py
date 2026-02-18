from pathlib import Path
from indexer.parse import parse_transcript_metadata, extract_speakers, get_transcript_body

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.md"


def test_parse_returns_episode_metadata():
    meta = parse_transcript_metadata(FIXTURE)
    assert "sample_transcript.md" in meta.source_file or "fixtures" in meta.source_file
    assert meta.title is not None
    assert meta.guest is not None


def test_parse_extracts_guest_from_frontmatter():
    meta = parse_transcript_metadata(FIXTURE)
    assert meta.guest == "Brian Chesky"


def test_parse_extracts_title():
    meta = parse_transcript_metadata(FIXTURE)
    assert "Brian Chesky" in meta.title


def test_parse_extracts_topics():
    meta = parse_transcript_metadata(FIXTURE)
    assert isinstance(meta.topics, list)
    assert len(meta.topics) >= 1


def test_extract_speakers_finds_names():
    content = FIXTURE.read_text()
    speakers = extract_speakers(content)
    assert isinstance(speakers, list)
    assert len(speakers) >= 1
    assert "Lenny" in speakers or "Brian Chesky" in speakers


def test_get_transcript_body():
    content = FIXTURE.read_text()
    body = get_transcript_body(content)
    assert len(body) > 0
    # Should not contain frontmatter
    assert "youtube_url" not in body
