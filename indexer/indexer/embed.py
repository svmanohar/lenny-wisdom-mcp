"""Voyage AI embedding generation for transcript segments."""

from __future__ import annotations

import asyncio
import voyageai


def prepare_embedding_text(
    topic: str,
    content: str,
    frameworks: list[str],
    tags: list[str],
) -> str:
    """Combine segment fields into a single text for embedding."""
    parts = [f"Topic: {topic}"]
    if frameworks:
        parts.append(f"Frameworks: {', '.join(frameworks)}")
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    parts.append(content)
    return "\n".join(parts)


# Module-level shared client — created once, reused across all coroutines.
_voyage_client: voyageai.AsyncClient | None = None


def get_voyage_client() -> voyageai.AsyncClient:
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.AsyncClient()
    return _voyage_client


async def generate_embeddings(
    texts: list[str],
    semaphore: asyncio.Semaphore | None = None,
) -> list[list[float]]:
    """Generate embeddings using Voyage AI voyage-3 (1024 dims).

    Args:
        texts: Texts to embed. Usually 3-8 per episode — well under one batch.
        semaphore: Optional semaphore to cap concurrent Voyage API calls across
                   all episodes. Pass the same instance to every call so the
                   limit is global. Voyage RPM limit is 300; a semaphore of
                   20-30 concurrent callers is safe.
    """
    client = get_voyage_client()
    batch_size = 128
    batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

    async def _embed_batch(batch: list[str]) -> list[list[float]]:
        async def _call() -> list[list[float]]:
            result = await client.embed(
                batch,
                model="voyage-3",
                input_type="document",
            )
            return result.embeddings

        if semaphore is not None:
            async with semaphore:
                return await _call()
        return await _call()

    # Run multiple batches concurrently when texts exceed batch_size.
    # For typical episode sizes (3-8 segments) this is always a single batch,
    # so gather() adds no overhead.
    results = await asyncio.gather(*[_embed_batch(b) for b in batches])

    all_embeddings: list[list[float]] = []
    for batch_result in results:
        all_embeddings.extend(batch_result)
    return all_embeddings
