"""CLI entrypoint for the full indexing pipeline.

Usage:
    lenny-index --transcripts ~/lenny-transcripts/episodes --dry-run --limit 3

Parallelism design
------------------
Three axes of concurrency, each controlled by a semaphore:

1. Intra-episode Sonnet parallelism (SONNET_SEM):
   All segment extraction calls within one episode fire concurrently.
   With ~5 segments × 4 s per call, this collapses per-episode Sonnet time
   from ~20 s → ~4 s (one network RTT).

2. Inter-episode parallelism (EPISODE_SEM):
   Up to EPISODE_CONCURRENCY episodes are processed at once.
   Default: 10. At 5 segments each that's 50 Sonnet calls in flight at peak —
   within the 4000 RPM tier limit.

3. Upload overlap (asyncio.gather on D1 + Vectorize):
   D1 and Vectorize uploads for a completed batch run concurrently.

Rate limit headroom (at EPISODE_CONCURRENCY=10, 5 segs/ep):
    Sonnet:  50 concurrent calls, each ~4 s → ~750 RPM peak  (limit: 4000 RPM)
    Haiku:   20 concurrent calls (seg + guest), each ~1 s → ~1200 RPM (limit: 4000 RPM)
    Voyage:  10 concurrent calls, each ~1 s → ~600 RPM       (limit: 300 RPM)

Voyage is the tightest. VOYAGE_SEM=5 keeps it well under 300 RPM.

Caching
-------
Every successfully processed episode is saved to a `.extraction.json` file
next to the transcript. On subsequent runs, episodes with an existing cache
file are loaded from disk (skipping all AI calls). Use --force to re-process.

The cache includes embeddings, so a --upload-only run costs $0 in API calls.

Error handling
--------------
Each episode is wrapped in a try/except. Failures are collected and reported
at the end. A single bad episode never aborts the run.

Progress tracking
-----------------
Rich progress bar with episode counter and status line per episode. Concurrent
episodes print to console non-interleaved via a threading lock (rich handles
this internally for its Progress context).
"""

import asyncio
import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from indexer.embed import generate_embeddings, prepare_embedding_text
from indexer.extract import extract_all_segments
from indexer.guest import extract_guest_profile
from indexer.models import EpisodeMetadata, ExtractionResult, GuestProfile, SegmentMetadata
from indexer.parse import parse_transcript_metadata
from indexer.segment import segment_transcript
from indexer.upload import (
    build_d1_insert_statements,
    build_guest_insert_statement,
    upload_to_d1,
    upload_to_vectorize,
)

console = Console()

# ── Concurrency knobs ──────────────────────────────────────────────────────────
# These can be overridden via env vars for easy tuning without code changes.
EPISODE_CONCURRENCY = int(os.getenv("LENNY_EPISODE_CONCURRENCY", "10"))
SONNET_CONCURRENCY  = int(os.getenv("LENNY_SONNET_CONCURRENCY",  "50"))
VOYAGE_CONCURRENCY  = int(os.getenv("LENNY_VOYAGE_CONCURRENCY",  "5"))

CACHE_SUFFIX = ".extraction.json"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def cache_path_for(filepath: Path) -> Path:
    """Return the cache file path for a given transcript."""
    return filepath.with_suffix(CACHE_SUFFIX)


def save_cache(
    filepath: Path,
    episode: EpisodeMetadata,
    guest: GuestProfile | None,
    segments: list[SegmentMetadata],
    extractions: list[ExtractionResult],
    embeddings: list[list[float]],
) -> None:
    """Write extraction results + embeddings to disk."""
    output = {
        "version": 1,
        "episode": episode.model_dump(),
        "guest": guest.model_dump() if guest else None,
        "segments": [s.model_dump() for s in segments],
        "extractions": [e.model_dump() for e in extractions],
        "embeddings": embeddings,
    }
    cache_path_for(filepath).write_text(json.dumps(output, indent=2))


def load_cache(
    filepath: Path,
) -> tuple[EpisodeMetadata, GuestProfile | None, list[SegmentMetadata], list[ExtractionResult], list[list[float]]]:
    """Load extraction results + embeddings from disk."""
    data = json.loads(cache_path_for(filepath).read_text())
    episode = EpisodeMetadata.model_validate(data["episode"])
    guest = GuestProfile.model_validate(data["guest"]) if data.get("guest") else None
    segments = [SegmentMetadata.model_validate(s) for s in data["segments"]]
    extractions = [ExtractionResult.model_validate(e) for e in data["extractions"]]
    embeddings = data.get("embeddings", [])
    return episode, guest, segments, extractions, embeddings


def has_cache(filepath: Path) -> bool:
    """Check if a valid cache file exists for this transcript."""
    cp = cache_path_for(filepath)
    if not cp.exists():
        return False
    try:
        data = json.loads(cp.read_text())
        # v1 caches include embeddings; older ones don't
        return "embeddings" in data and len(data["embeddings"]) > 0
    except (json.JSONDecodeError, KeyError):
        return False


# ── Episode result type ────────────────────────────────────────────────────────

class EpisodeResult:
    """Outcome of processing one episode — either success or failure."""

    def __init__(
        self,
        filepath: Path,
        episode_index: int,
        stmts: list[dict] | None = None,
        vectors: list[dict] | None = None,
        error: Exception | None = None,
        from_cache: bool = False,
    ) -> None:
        self.filepath = filepath
        self.episode_index = episode_index
        self.stmts = stmts or []
        self.vectors = vectors or []
        self.error = error
        self.from_cache = from_cache

    @property
    def ok(self) -> bool:
        return self.error is None


# ── Building upload payloads from loaded data ─────────────────────────────────

def build_payloads(
    episode: EpisodeMetadata,
    guest: GuestProfile | None,
    segments: list[SegmentMetadata],
    extractions: list[ExtractionResult],
    embeddings: list[list[float]],
) -> tuple[list[dict], list[dict]]:
    """Build SQL statements and vector payloads from extracted data."""
    vectors = [
        {
            "id": seg.segment_id,
            "values": emb,
            "metadata": {
                "episode_id": seg.segment_id.split("-seg-")[0],
                "topic": seg.topic,
                "tags": ",".join(ext.applicable_to),
                "source_file": episode.source_file,
            },
        }
        for seg, ext, emb in zip(segments, extractions, embeddings)
    ]

    stmts = build_d1_insert_statements(episode, segments, extractions)
    if guest:
        stmts.append(build_guest_insert_statement(guest))

    return stmts, vectors


# ── Per-episode processor ──────────────────────────────────────────────────────

def _episode_slug(filepath: Path) -> str:
    """Derive a stable, unique slug from a transcript filepath.

    For subdirectory transcripts (e.g. brian-chesky/transcript.md) → 'brian-chesky'.
    For flat .txt files (e.g. 'Dr. Becky Kennedy.txt') → 'dr-becky-kennedy'.
    """
    import re
    if filepath.name == "transcript.md":
        return filepath.parent.name
    # Flat file: slugify the stem
    slug = filepath.stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


async def process_episode(
    filepath: Path,
    episode_index: int,
    dry_run: bool,
    force: bool,
    sonnet_sem: asyncio.Semaphore,
    voyage_sem: asyncio.Semaphore,
    progress: Progress,
    progress_task_id: int,
) -> EpisodeResult:
    """Process a single episode through the full pipeline.

    If a cache file exists and --force is not set, loads from cache instead
    of calling AI APIs.
    """
    episode_name = _episode_slug(filepath)

    try:
        # ── Try loading from cache ────────────────────────────────────────
        if not force and has_cache(filepath):
            episode, guest, segments, extractions, embeddings = load_cache(filepath)
            stmts, vectors = build_payloads(episode, guest, segments, extractions, embeddings)

            fw_count = sum(len(e.frameworks) for e in extractions)
            h_count  = sum(len(e.heuristics) for e in extractions)
            ex_count = sum(len(e.examples)   for e in extractions)
            progress.console.print(
                f"  [cyan]↻[/cyan] [{episode_index}] {episode_name} — "
                f"{len(segments)} segs, {fw_count} fw, {h_count} heur, {ex_count} ex [dim](cached)[/dim]"
            )
            progress.advance(progress_task_id)

            return EpisodeResult(
                filepath=filepath,
                episode_index=episode_index,
                stmts=stmts,
                vectors=vectors,
                from_cache=True,
            )

        # ── Full AI processing ────────────────────────────────────────────
        episode_id = episode_name

        # Step 1: parse metadata (local, instant)
        episode = parse_transcript_metadata(filepath)
        content = filepath.read_text(encoding="utf-8")

        # Step 2: segment transcript (Haiku)
        segments = await segment_transcript(content, episode_id)

        # Step 3: guest profile + Sonnet extraction run concurrently.
        intro_text = "\n".join(seg.content for seg in segments[:2])

        guest_task = asyncio.create_task(
            _safe_guest_profile(intro_text, episode.guest)
        )
        extraction_task = asyncio.create_task(
            extract_all_segments(
                [seg.content for seg in segments],
                semaphore=sonnet_sem,
            )
        )

        guest_profile, extractions = await asyncio.gather(guest_task, extraction_task)

        # Step 4: build embedding texts (local)
        embedding_texts = [
            prepare_embedding_text(
                topic=seg.topic,
                content=seg.content,
                frameworks=[f.name for f in ext.frameworks],
                tags=ext.applicable_to,
            )
            for seg, ext in zip(segments, extractions)
        ]

        # Step 5: generate embeddings (Voyage)
        embeddings = await generate_embeddings(embedding_texts, semaphore=voyage_sem)

        # Step 6: save cache to disk (before upload — protects against upload failures)
        save_cache(filepath, episode, guest_profile, segments, extractions, embeddings)

        # Step 7: build upload payloads
        stmts, vectors = build_payloads(episode, guest_profile, segments, extractions, embeddings)

        fw_count = sum(len(e.frameworks) for e in extractions)
        h_count  = sum(len(e.heuristics) for e in extractions)
        ex_count = sum(len(e.examples)   for e in extractions)
        progress.console.print(
            f"  [green]✓[/green] [{episode_index}] {episode_name} — "
            f"{len(segments)} segs, {fw_count} fw, {h_count} heur, {ex_count} ex"
        )
        progress.advance(progress_task_id)

        return EpisodeResult(
            filepath=filepath,
            episode_index=episode_index,
            stmts=stmts,
            vectors=vectors,
        )

    except Exception as exc:
        progress.console.print(
            f"  [red]✗[/red] [{episode_index}] {episode_name}: {exc}"
        )
        progress.advance(progress_task_id)
        return EpisodeResult(
            filepath=filepath,
            episode_index=episode_index,
            error=exc,
        )


async def _safe_guest_profile(
    intro_text: str,
    fallback_name: str | None,
) -> GuestProfile | None:
    """Extract guest profile, returning None on failure rather than raising."""
    try:
        return await extract_guest_profile(intro_text, fallback_name=fallback_name)
    except Exception as exc:
        console.print(f"  [yellow]⚠ Guest extraction failed: {exc}[/yellow]")
        return None


# ── Main pipeline ──────────────────────────────────────────────────────────────

@click.command()
@click.option("--transcripts", type=click.Path(exists=True), required=True, help="Path to transcript directory")
@click.option("--account-id", envvar="CF_ACCOUNT_ID", help="Cloudflare account ID")
@click.option("--db-id", envvar="CF_DB_ID", help="D1 database ID")
@click.option("--api-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
@click.option("--index-name", default="lenny-wisdom-vectors", help="Vectorize index name")
@click.option("--dry-run", is_flag=True, help="Process without uploading to Cloudflare")
@click.option("--upload-only", is_flag=True, help="Upload from cache only — no AI calls")
@click.option("--force", is_flag=True, help="Re-process even if cache exists")
@click.option("--limit", type=int, default=0, help="Process only N episodes (0 = all)")
@click.option(
    "--episode-concurrency",
    type=int,
    default=EPISODE_CONCURRENCY,
    show_default=True,
    help="Max episodes processed concurrently",
)
@click.option(
    "--sonnet-concurrency",
    type=int,
    default=SONNET_CONCURRENCY,
    show_default=True,
    help="Max concurrent Sonnet API calls (across all episodes)",
)
@click.option(
    "--voyage-concurrency",
    type=int,
    default=VOYAGE_CONCURRENCY,
    show_default=True,
    help="Max concurrent Voyage API calls (across all episodes)",
)
def main(
    transcripts: str,
    account_id: str | None,
    db_id: str | None,
    api_token: str | None,
    index_name: str,
    dry_run: bool,
    upload_only: bool,
    force: bool,
    limit: int,
    episode_concurrency: int,
    sonnet_concurrency: int,
    voyage_concurrency: int,
) -> None:
    """Index Lenny's Podcast transcripts into Cloudflare D1 + Vectorize."""
    if not dry_run and not upload_only and not all([account_id, db_id, api_token]):
        raise click.UsageError(
            "Must provide --account-id, --db-id, --api-token (or set CF_ACCOUNT_ID, CF_DB_ID, CF_API_TOKEN env vars). "
            "Or use --dry-run to test without uploading."
        )

    if upload_only and not all([account_id, db_id, api_token]):
        raise click.UsageError(
            "--upload-only requires --account-id, --db-id, --api-token (or env vars)."
        )

    transcript_dir = Path(transcripts)
    # Support both .md (original repo) and .txt (Dropbox) formats
    files = sorted(
        list(transcript_dir.glob("**/transcript.md"))
        + list(transcript_dir.glob("**/*.txt"))
    )
    if not files:
        files = sorted(transcript_dir.glob("*.md"))
    if limit > 0:
        files = files[:limit]

    mode_label = "DRY RUN" if dry_run else ("UPLOAD ONLY (from cache)" if upload_only else "LIVE")
    console.print(f"\n[bold]Lenny Wisdom Indexer[/bold]")
    console.print(f"Transcripts : {transcript_dir} ({len(files)} files)")
    console.print(f"Mode        : {mode_label}")
    if not upload_only:
        console.print(
            f"Concurrency : {episode_concurrency} episodes | "
            f"{sonnet_concurrency} Sonnet slots | "
            f"{voyage_concurrency} Voyage slots"
        )
    console.print(f"Cache       : {'force refresh' if force else 'enabled'}\n")

    failure_count = asyncio.run(_run_pipeline(
        files=files,
        account_id=account_id or "",
        db_id=db_id or "",
        api_token=api_token or "",
        index_name=index_name,
        dry_run=dry_run,
        upload_only=upload_only,
        force=force,
        episode_concurrency=episode_concurrency,
        sonnet_concurrency=sonnet_concurrency,
        voyage_concurrency=voyage_concurrency,
    ))

    if failure_count > 0:
        raise SystemExit(1)


async def _run_pipeline(
    files: list[Path],
    account_id: str,
    db_id: str,
    api_token: str,
    index_name: str,
    dry_run: bool,
    upload_only: bool,
    force: bool,
    episode_concurrency: int,
    sonnet_concurrency: int,
    voyage_concurrency: int,
) -> int:
    """Run the full indexing pipeline with concurrent episode processing.

    Returns the number of episode failures.
    """

    # Shared semaphores — one instance per API, shared across all coroutines.
    episode_sem = asyncio.Semaphore(episode_concurrency)
    sonnet_sem  = asyncio.Semaphore(sonnet_concurrency)
    voyage_sem  = asyncio.Semaphore(voyage_concurrency)

    all_stmt_groups: list[list[dict]] = []  # one group per episode (ordering preserved)
    all_vectors:     list[dict] = []
    failures:        list[EpisodeResult] = []
    cached_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Indexing episodes", total=len(files))

        if upload_only:
            # Upload-only mode: load all from cache, no AI calls
            for i, filepath in enumerate(files):
                idx = i + 1
                episode_name = _episode_slug(filepath)
                if has_cache(filepath):
                    try:
                        episode, guest, segments, extractions, embeddings = load_cache(filepath)
                        stmts, vectors = build_payloads(episode, guest, segments, extractions, embeddings)
                        all_stmt_groups.append(stmts)
                        all_vectors.extend(vectors)
                        cached_count += 1
                        progress.console.print(
                            f"  [cyan]↻[/cyan] [{idx}] {episode_name} [dim](cached)[/dim]"
                        )
                    except Exception as exc:
                        progress.console.print(
                            f"  [red]✗[/red] [{idx}] {episode_name}: cache load failed: {exc}"
                        )
                        failures.append(EpisodeResult(filepath=filepath, episode_index=idx, error=exc))
                else:
                    progress.console.print(
                        f"  [yellow]⊘[/yellow] [{idx}] {episode_name} [dim](no cache — skipped)[/dim]"
                    )
                progress.advance(task_id)
        else:
            # Normal mode: process episodes (with cache hit optimization)
            async def bounded_process(filepath: Path, idx: int) -> EpisodeResult:
                async with episode_sem:
                    return await process_episode(
                        filepath=filepath,
                        episode_index=idx,
                        dry_run=dry_run,
                        force=force,
                        sonnet_sem=sonnet_sem,
                        voyage_sem=voyage_sem,
                        progress=progress,
                        progress_task_id=task_id,
                    )

            results: list[EpisodeResult] = list(
                await asyncio.gather(
                    *[bounded_process(fp, i + 1) for i, fp in enumerate(files)]
                )
            )

            for result in results:
                if result.ok:
                    all_stmt_groups.append(result.stmts)
                    all_vectors.extend(result.vectors)
                    if result.from_cache:
                        cached_count += 1
                else:
                    failures.append(result)

    # ── Summary ────────────────────────────────────────────────────────────────
    total_ok = len(files) - len(failures) if not upload_only else cached_count
    console.print(f"\n[bold]Results:[/bold]")
    console.print(f"  Succeeded : {total_ok}/{len(files)}")
    if cached_count > 0:
        console.print(f"  From cache: {cached_count}")
    if failures:
        console.print(f"  [red]Failed    : {len(failures)}[/red]")
        for f in failures:
            console.print(f"    - {f.filepath.parent.name}: {f.error}")
    total_stmts = sum(len(g) for g in all_stmt_groups)
    console.print(f"  SQL stmts : {total_stmts} (across {len(all_stmt_groups)} episodes)")
    console.print(f"  Vectors   : {len(all_vectors)}")

    if dry_run:
        console.print(f"\n[bold green]Dry run complete. Cache files saved.[/bold green]")
        return len(failures)

    if not all_stmt_groups and not all_vectors:
        console.print(f"\n[yellow]Nothing to upload.[/yellow]")
        return len(failures)

    # ── Upload: D1 and Vectorize run concurrently ──────────────────────────────
    console.print(f"\n[bold]Uploading to Cloudflare...[/bold]")

    async def _upload_d1() -> None:
        await upload_to_d1(all_stmt_groups, account_id, db_id, api_token)
        console.print(f"  [green]✓[/green] D1: {total_stmts} statements")

    async def _upload_vectorize() -> None:
        await upload_to_vectorize(all_vectors, account_id, index_name, api_token)
        console.print(f"  [green]✓[/green] Vectorize: {len(all_vectors)} vectors")

    await asyncio.gather(_upload_d1(), _upload_vectorize())

    console.print(f"\n[bold green]Indexing complete![/bold green]")

    return len(failures)


if __name__ == "__main__":
    main()
