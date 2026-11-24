import httpx
import pytest
from rich.console import Console

from indexer.models import EpisodeMetadata
from indexer.rss_titles import (
    apply_feed_metadata,
    fetch_feed,
    guest_tokens,
    match_item,
    parse_feed,
)

RSS = """<?xml version="1.0"?>
<rss><channel>
<item><title>Building products with Josh Woodward (Google Labs)</title><pubDate>Sun, 02 Nov 2025 10:30:00 GMT</pubDate></item>
<item><title>Inside OpenAI Codex with Tibo Sottiaux</title><pubDate>Thu, 06 Mar 2025 08:00:00 GMT</pubDate></item>
<item><title>Mona Sarantakos on growth</title><pubDate>Mon, 01 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Anish Acharya on AI investing</title><pubDate>Tue, 02 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Sherwin Wu on OpenAI platform</title><pubDate>Wed, 03 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Dr. Becky Kennedy on parenting</title><pubDate>Fri, 05 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Jane Smith on pricing</title><pubDate>Sat, 06 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Jane Smith returns: hiring</title><pubDate>Sun, 07 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Rene Zellweger</title><pubDate>not a date</pubDate></item>
<item><pubDate>Sun, 07 Jan 2024 08:00:00 GMT</pubDate></item>
</channel></rss>"""

ITEMS = parse_feed(RSS)


def episode(**kw) -> EpisodeMetadata:
    return EpisodeMetadata(source_file="x.txt", **kw)


def test_parse_feed_skips_items_without_title():
    assert len(ITEMS) == 9


def test_exact_single_match():
    item = match_item("Josh Woodward", ITEMS)
    assert item.title.startswith("Building products with Josh Woodward")


def test_camel_case_stem():
    assert guest_tokens("TiboSottiaux") == ["tibo", "sottiaux"]
    assert match_item("TiboSottiaux", ITEMS).title.endswith("Tibo Sottiaux")


@pytest.mark.parametrize("stem", ["Mona Sarantakos_V2", "Anish Acharya 2.0", "Sherwin Wu_V2", "Sherwin Wu V2"])
def test_version_suffixes_stripped(stem):
    assert match_item(stem, ITEMS) is not None


def test_dr_prefix():
    assert guest_tokens("Dr. Becky Kennedy") == ["dr", "becky", "kennedy"]
    assert match_item("Dr. Becky Kennedy", ITEMS).title.startswith("Dr. Becky Kennedy")


def test_accents_normalized():
    items = parse_feed("<rss><channel><item><title>Zoë Chance</title></item></channel></rss>")
    assert match_item("Zoe Chance", items) is not None


def test_ambiguous_returns_none():
    assert match_item("Jane Smith", ITEMS) is None


def test_no_match_returns_none():
    assert match_item("Max Schoenig", ITEMS) is None


def test_whole_word_only():
    assert match_item("Jan", ITEMS) is None


def test_apply_fills_title_and_date():
    result = apply_feed_metadata(episode(guest="Josh Woodward"), "Josh Woodward", ITEMS)
    assert result.title == "Building products with Josh Woodward (Google Labs)"
    assert result.date == "2025-11-02"


def test_apply_does_not_override_frontmatter_title():
    ep = episode(title="Frontmatter title", date="2020-01-01")
    result = apply_feed_metadata(ep, "Josh Woodward", ITEMS)
    assert result.title == "Frontmatter title"
    assert result.date == "2020-01-01"


def test_apply_keeps_existing_date_when_title_missing():
    result = apply_feed_metadata(episode(date="2020-01-01"), "Josh Woodward", ITEMS)
    assert result.title is not None
    assert result.date == "2020-01-01"


def test_apply_no_match_leaves_none():
    result = apply_feed_metadata(episode(), "Jane Smith", ITEMS)
    assert result.title is None and result.date is None


def test_apply_with_empty_feed():
    assert apply_feed_metadata(episode(), "Josh Woodward", []).title is None


def test_unparseable_date_leaves_date_none():
    result = apply_feed_metadata(episode(), "Rene Zellweger", ITEMS)
    assert result.title == "Rene Zellweger"
    assert result.date is None


def test_fetch_failure_returns_empty(monkeypatch, capsys):
    def boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "get", boom)
    assert fetch_feed(Console()) == []
    assert "RSS feed unavailable" in capsys.readouterr().out


def test_fetch_non_200_returns_empty(monkeypatch):
    def fake_get(url, **k):
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_feed(Console()) == []


def test_fetch_malformed_xml_returns_empty(monkeypatch):
    def fake_get(url, **k):
        return httpx.Response(200, content=b"<rss><oops", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_feed(Console()) == []


def test_fetch_success_parses(monkeypatch):
    def fake_get(url, **k):
        assert k["headers"]["User-Agent"] == "lenny-wisdom-indexer"
        return httpx.Response(200, content=RSS.encode(), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert len(fetch_feed(Console())) == 9


def test_process_episode_fills_title_for_cached_episode(tmp_path):
    import asyncio
    from unittest.mock import MagicMock

    from indexer.models import ExtractionResult, SegmentMetadata
    from indexer.run import process_episode, save_cache

    transcript = tmp_path / "Josh Woodward.txt"
    transcript.write_text("raw transcript")
    seg = SegmentMetadata(segment_id="josh-woodward-seg-0", topic="t", speakers=[], content="c")
    save_cache(transcript, episode(guest="Josh Woodward"),
               None, [seg], [ExtractionResult()], [[0.1, 0.2]])

    result = asyncio.run(process_episode(
        filepath=transcript, episode_index=1, dry_run=True, force=False,
        sonnet_sem=None, voyage_sem=None, progress=MagicMock(), progress_task_id=0,
        feed_items=ITEMS,
    ))

    assert result.ok and result.from_cache
    insert = next(s for s in result.stmts if "INTO episodes" in s["sql"])
    assert "Building products with Josh Woodward (Google Labs)" in insert["params"]
    assert "2025-11-02" in insert["params"]
