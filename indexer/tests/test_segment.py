from indexer.segment import build_segmentation_prompt, parse_segmentation_response

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
