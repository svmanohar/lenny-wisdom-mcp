"""CLI entrypoint for the full indexing pipeline.

Usage:
    lenny-index --transcripts ~/lenny-transcripts/episodes --dry-run --limit 3
"""

import asyncio
import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from indexer.embed import generate_embeddings, prepare_embedding_text
from indexer.extract import extract_from_segment
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


async def process_episode(
    filepath: Path,
    episode_index: int,
    dry_run: bool = False,
) -> tuple[EpisodeMetadata, list[SegmentMetadata], list[ExtractionResult], list[dict], GuestProfile | None]:
    """Process a single episode through the full pipeline."""
    episode_id = f"ep-{episode_index}"
    console.print(f"  [dim]Parsing metadata...[/dim]")
    episode = parse_transcript_metadata(filepath)

    content = filepath.read_text(encoding="utf-8")

    console.print(f"  [dim]Segmenting with Haiku...[/dim]")
    segments = await segment_transcript(content, episode_id)
    console.print(f"  [dim]  → {len(segments)} segments[/dim]")

    console.print(f"  [dim]Extracting guest profile...[/dim]")
    intro_text = "\n".join(seg.content for seg in segments[:2])
    try:
        guest_profile = await extract_guest_profile(intro_text, fallback_name=episode.guest)
        console.print(f"  [dim]  → {guest_profile.name}: {guest_profile.current_role or 'role unknown'} @ {guest_profile.current_company or '?'}[/dim]")
    except Exception as e:
        console.print(f"  [yellow]⚠ Guest extraction failed: {e}[/yellow]")
        guest_profile = None

    console.print(f"  [dim]Extracting with Sonnet...[/dim]")
    extractions: list[ExtractionResult] = []
    for seg in segments:
        ext = await extract_from_segment(seg.content)
        extractions.append(ext)

    embedding_texts = []
    for seg, ext in zip(segments, extractions):
        text = prepare_embedding_text(
            topic=seg.topic,
            content=seg.content,
            frameworks=[f.name for f in ext.frameworks],
            tags=ext.applicable_to,
        )
        embedding_texts.append(text)

    console.print(f"  [dim]Generating Voyage embeddings...[/dim]")
    embeddings = await generate_embeddings(embedding_texts)

    vectors = []
    for seg, ext, emb in zip(segments, extractions, embeddings):
        vectors.append({
            "id": seg.segment_id,
            "values": emb,
            "metadata": {
                "episode_id": episode_id,
                "topic": seg.topic,
                "tags": ",".join(ext.applicable_to),
                "source_file": episode.source_file,
            },
        })

    fw_count = sum(len(e.frameworks) for e in extractions)
    h_count = sum(len(e.heuristics) for e in extractions)
    ex_count = sum(len(e.examples) for e in extractions)
    console.print(
        f"  [green]✓[/green] {len(segments)} segments, "
        f"{fw_count} frameworks, {h_count} heuristics, {ex_count} examples"
    )

    if dry_run:
        output = {
            "episode": episode.model_dump(),
            "guest": guest_profile.model_dump() if guest_profile else None,
            "segments": [s.model_dump() for s in segments],
            "extractions": [e.model_dump() for e in extractions],
        }
        dry_run_path = filepath.with_suffix(".extraction.json")
        dry_run_path.write_text(json.dumps(output, indent=2))
        console.print(f"  [dim]Dry run output: {dry_run_path}[/dim]")

    return episode, segments, extractions, vectors, guest_profile


@click.command()
@click.option("--transcripts", type=click.Path(exists=True), required=True, help="Path to transcript directory")
@click.option("--account-id", envvar="CF_ACCOUNT_ID", help="Cloudflare account ID")
@click.option("--db-id", envvar="CF_DB_ID", help="D1 database ID")
@click.option("--api-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
@click.option("--index-name", default="lenny-wisdom-vectors", help="Vectorize index name")
@click.option("--dry-run", is_flag=True, help="Process without uploading to Cloudflare")
@click.option("--limit", type=int, default=0, help="Process only N episodes (0 = all)")
def main(
    transcripts: str,
    account_id: str | None,
    db_id: str | None,
    api_token: str | None,
    index_name: str,
    dry_run: bool,
    limit: int,
) -> None:
    """Index Lenny's Podcast transcripts into Cloudflare D1 + Vectorize."""
    if not dry_run and not all([account_id, db_id, api_token]):
        raise click.UsageError(
            "Must provide --account-id, --db-id, --api-token (or set CF_ACCOUNT_ID, CF_DB_ID, CF_API_TOKEN env vars). "
            "Or use --dry-run to test without uploading."
        )

    transcript_dir = Path(transcripts)
    # Transcripts live at episodes/{guest-name}/transcript.md
    files = sorted(transcript_dir.glob("**/transcript.md"))
    if not files:
        # Fallback: try flat *.md pattern
        files = sorted(transcript_dir.glob("*.md"))
    if limit > 0:
        files = files[:limit]

    console.print(f"\n[bold]Lenny Wisdom Indexer[/bold]")
    console.print(f"Transcripts: {transcript_dir} ({len(files)} files)")
    console.print(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPLOAD'}\n")

    asyncio.run(_run_pipeline(
        files=files,
        account_id=account_id or "",
        db_id=db_id or "",
        api_token=api_token or "",
        index_name=index_name,
        dry_run=dry_run,
    ))


async def _run_pipeline(
    files: list[Path],
    account_id: str,
    db_id: str,
    api_token: str,
    index_name: str,
    dry_run: bool,
) -> None:
    """Run the full indexing pipeline."""
    all_stmts: list[dict] = []
    all_vectors: list[dict] = []

    for i, filepath in enumerate(files):
        console.print(f"\n[bold][{i+1}/{len(files)}] {filepath.name}[/bold]")

        episode, segments, extractions, vectors, guest_profile = await process_episode(
            filepath=filepath,
            episode_index=i + 1,
            dry_run=dry_run,
        )

        stmts = build_d1_insert_statements(episode, segments, extractions)
        if guest_profile:
            stmts.append(build_guest_insert_statement(guest_profile))
        all_stmts.extend(stmts)
        all_vectors.extend(vectors)

    if dry_run:
        console.print(f"\n[bold green]Dry run complete.[/bold green]")
        console.print(f"Would upload: {len(all_stmts)} SQL statements, {len(all_vectors)} vectors")
        return

    console.print(f"\n[bold]Uploading to Cloudflare D1...[/bold]")
    await upload_to_d1(all_stmts, account_id, db_id, api_token)
    console.print(f"[green]✓[/green] {len(all_stmts)} statements executed")

    console.print(f"\n[bold]Uploading to Cloudflare Vectorize...[/bold]")
    await upload_to_vectorize(all_vectors, account_id, index_name, api_token)
    console.print(f"[green]✓[/green] {len(all_vectors)} vectors upserted")

    console.print(f"\n[bold green]Indexing complete![/bold green]")


if __name__ == "__main__":
    main()
