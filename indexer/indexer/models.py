"""Pydantic models for the Lenny Wisdom indexer pipeline."""

from pydantic import BaseModel, Field


class EpisodeMetadata(BaseModel):
    """Top-level metadata for a podcast episode transcript."""

    source_file: str
    episode_number: int | None = None
    title: str | None = None
    guest: str | None = None
    date: str | None = None
    topics: list[str] = Field(default_factory=list)


class SegmentMetadata(BaseModel):
    """A topical segment within an episode."""

    segment_id: str
    topic: str
    speakers: list[str]
    content: str
    token_count: int | None = None


class ExtractedFramework(BaseModel):
    """A named framework or mental model extracted from a segment."""

    name: str
    description: str
    source_attribution: str | None = None
    verbatim_definition: str | None = None


class ExtractedHeuristic(BaseModel):
    """A pithy rule-of-thumb or heuristic."""

    statement: str
    context: str | None = None


class ExtractedExample(BaseModel):
    """A concrete company example illustrating a concept."""

    company: str | None = None
    situation: str
    outcome: str | None = None


class ExtractedCommunicationPattern(BaseModel):
    """A communication or persuasion technique observed in the content."""

    technique: str
    audience: str | None = None
    example: str | None = None
    source_attribution: str | None = None


class GuestProfile(BaseModel):
    """Structured profile of a podcast guest extracted from the intro."""

    name: str
    current_role: str | None = None
    current_company: str | None = None
    notable_companies: list[str] = Field(default_factory=list)
    domain_expertise: list[str] = Field(default_factory=list)
    company_stages: list[str] = Field(default_factory=list)
    industry_verticals: list[str] = Field(default_factory=list)
    bio_summary: str | None = None


class ExtractionResult(BaseModel):
    """Aggregated extraction output for a single segment."""

    frameworks: list[ExtractedFramework] = Field(default_factory=list)
    heuristics: list[ExtractedHeuristic] = Field(default_factory=list)
    examples: list[ExtractedExample] = Field(default_factory=list)
    communication_patterns: list[ExtractedCommunicationPattern] = Field(
        default_factory=list
    )
    applicable_to: list[str] = Field(default_factory=list)
    key_quote: str | None = None
