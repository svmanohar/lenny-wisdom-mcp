"""Fill missing episode titles and dates from Lenny's podcast RSS feed.

Dropbox `.txt` transcripts carry no metadata, only a guest name in the
filename. The feed is fetched once per run and each guest is matched to at
most one item title. Ambiguous or missing matches are left as None.
"""

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx
from rich.console import Console

from indexer.models import EpisodeMetadata

FEED_URL = "https://api.substack.com/feed/podcast/10845.rss"
USER_AGENT = "lenny-wisdom-indexer"

_VERSION_SUFFIX = re.compile(r"[ _]?(?:V2|2\.0)$", re.IGNORECASE)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")


@dataclass(frozen=True)
class FeedItem:
    title: str
    date: str | None
    words: frozenset[str]


def _words(text: str) -> list[str]:
    """NFKD -> ASCII, lowercase, non-letters to spaces, split into words."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]+", " ", ascii_text.lower()).split()


def guest_tokens(stem: str) -> list[str]:
    """Turn a filename stem like 'TiboSottiaux' or 'Sherwin Wu_V2' into name tokens."""
    stem = _VERSION_SUFFIX.sub("", stem.strip())
    stem = stem.replace("_", " ")
    stem = _CAMEL_BOUNDARY.sub(" ", stem)
    return _words(stem)


def _pub_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw.strip()).date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_feed(xml_text: str | bytes) -> list[FeedItem]:
    """Parse RSS XML into feed items. Raises ET.ParseError on malformed XML."""
    root = ET.fromstring(xml_text)
    items: list[FeedItem] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        items.append(
            FeedItem(
                title=title,
                date=_pub_date(item.findtext("pubDate")),
                words=frozenset(_words(title)),
            )
        )
    return items


def fetch_feed(console: Console, url: str = FEED_URL) -> list[FeedItem]:
    """Fetch and parse the feed. On any failure, warn and return no items."""
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )
        response.raise_for_status()
        return parse_feed(response.content)
    except (httpx.HTTPError, ET.ParseError) as exc:
        console.print(f"  [yellow]⚠ RSS feed unavailable, titles/dates not filled: {exc}[/yellow]")
        return []


def match_item(stem: str, items: list[FeedItem]) -> FeedItem | None:
    """Return the single feed item whose title contains every guest token, else None."""
    tokens = guest_tokens(stem)
    if not tokens:
        return None
    matches = [item for item in items if all(t in item.words for t in tokens)]
    return matches[0] if len(matches) == 1 else None


def apply_feed_metadata(
    episode: EpisodeMetadata, stem: str, items: list[FeedItem]
) -> EpisodeMetadata:
    """Fill title/date from the feed. Existing values are never overridden."""
    if episode.title is not None or not items:
        return episode
    item = match_item(stem, items)
    if item is None:
        return episode
    update = {"title": item.title}
    if episode.date is None and item.date is not None:
        update["date"] = item.date
    return episode.model_copy(update=update)
