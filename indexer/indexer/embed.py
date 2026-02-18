"""Voyage AI embedding generation for transcript segments."""

from __future__ import annotations


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


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using Voyage AI voyage-3 (1024 dims)."""
    import voyageai

    client = voyageai.AsyncClient()
    all_embeddings: list[list[float]] = []
    batch_size = 128

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = await client.embed(
            batch,
            model="voyage-3",
            input_type="document",
        )
        all_embeddings.extend(result.embeddings)

    return all_embeddings
