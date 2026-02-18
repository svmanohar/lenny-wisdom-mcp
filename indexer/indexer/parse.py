"""Parse episode metadata and speaker information from transcript markdown files."""

import re
import yaml
from pathlib import Path

from indexer.models import EpisodeMetadata


def parse_transcript_metadata(filepath: Path) -> EpisodeMetadata:
    """Extract episode metadata from a transcript file.

    Supports two formats:
    - .md files with YAML frontmatter (original transcripts repo)
    - .txt files with no metadata (Dropbox shared folder) — guest name
      is inferred from the filename (e.g., "Gibson Biddle.txt").
    """
    content = filepath.read_text(encoding="utf-8")

    # Parse YAML frontmatter (returns {} for .txt files without frontmatter)
    frontmatter = _parse_frontmatter(content)

    # Extract episode number from parent directory or filename
    episode_number = _extract_episode_number(filepath)

    # For .txt files without frontmatter, infer guest from filename
    guest = frontmatter.get("guest")
    if not guest:
        guest = _guest_name_from_filepath(filepath)

    return EpisodeMetadata(
        source_file=str(filepath.relative_to(filepath.parent.parent)),
        episode_number=episode_number,
        title=frontmatter.get("title"),
        guest=guest,
        date=str(frontmatter["publish_date"]) if frontmatter.get("publish_date") is not None else None,
        topics=frontmatter.get("keywords", []),
    )


def _parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def extract_speakers(content: str) -> list[str]:
    """Extract unique speaker names from transcript content.

    Handles format: 'Speaker Name (HH:MM:SS):'
    Ignores continuation lines that are just '(HH:MM:SS):'
    """
    pattern = r"^([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z\'-]+)*)\s+\(\d{2}:\d{2}:\d{2}\):"
    speakers = set()
    for line in content.split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            speakers.add(match.group(1))
    return sorted(speakers)


def get_transcript_body(content: str) -> str:
    """Extract just the transcript body.

    For .md files: strips frontmatter and finds the ## Transcript heading.
    For .txt files: returns the full content (it's already just transcript).
    """
    # Remove frontmatter if present
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2]

    # Find ## Transcript heading
    match = re.search(r"^##\s+Transcript\s*$", content, re.MULTILINE)
    if match:
        return content[match.end() :].strip()

    # Fallback: return everything after the first H1
    match = re.search(r"^#\s+.+$", content, re.MULTILINE)
    if match:
        return content[match.end() :].strip()

    # No markdown structure — return as-is (raw .txt files)
    return content.strip()


def _guest_name_from_filepath(filepath: Path) -> str:
    """Infer guest name from filepath.

    Handles:
    - guest-name/transcript.md → "Guest Name" (from directory)
    - "Gibson Biddle.txt"      → "Gibson Biddle" (from filename)
    """
    if filepath.stem == "transcript":
        # Directory-based: guest-name/transcript.md
        slug = filepath.parent.name
        return slug.replace("-", " ").title()
    # Filename-based: "Gibson Biddle.txt"
    return filepath.stem


def _extract_episode_number(filepath: Path) -> int | None:
    """Try to extract episode number. Returns None since transcripts use guest names."""
    return None
