"""Topic-based transcript segmentation using Claude Haiku."""

import re
import anthropic
from indexer.models import SegmentMetadata

SEGMENTATION_PROMPT = """You are segmenting a podcast transcript into coherent topic blocks.

Rules:
- Each block covers ONE topic, framework, or line of discussion
- Preserve speaker attribution exactly as written
- Blocks should be 300-2000 tokens (flexible based on topic coherence)
- Mark topic shifts with the separator format below
- Do NOT summarize or modify the transcript text

Output format (repeat for each segment):
---SEGMENT---
topic: [brief topic label, 3-8 words]
speakers: ["Speaker1", "Speaker2"]
[exact transcript text for this segment]

Here is the transcript to segment:

{transcript}"""


def build_segmentation_prompt(transcript: str) -> str:
    return SEGMENTATION_PROMPT.format(transcript=transcript)


def parse_segmentation_response(response: str, episode_id: str) -> list[SegmentMetadata]:
    raw_segments = response.split("---SEGMENT---")
    segments = []

    for raw in raw_segments:
        raw = raw.strip()
        if not raw:
            continue

        topic = ""
        speakers: list[str] = []
        content_lines: list[str] = []

        lines = raw.split("\n")
        for line in lines:
            if line.startswith("topic:"):
                topic = line[len("topic:"):].strip()
            elif line.startswith("speakers:"):
                speakers_str = line[len("speakers:"):].strip()
                speakers = _parse_speakers_list(speakers_str)
            else:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()
        if not content:
            continue

        segments.append(SegmentMetadata(
            segment_id=f"{episode_id}-seg-{len(segments)}",
            topic=topic or "untitled",
            speakers=speakers,
            content=content,
            token_count=_estimate_tokens(content),
        ))

    return segments


def _parse_speakers_list(s: str) -> list[str]:
    s = s.strip().strip("[]")
    return [name.strip().strip("\"'") for name in s.split(",") if name.strip()]


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


async def segment_transcript(transcript: str, episode_id: str) -> list[SegmentMetadata]:
    client = anthropic.AsyncAnthropic()
    prompt = build_segmentation_prompt(transcript)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = message.content[0].text
    return parse_segmentation_response(response_text, episode_id)
