from indexer.embed import prepare_embedding_text


def test_prepare_embedding_text_combines_fields():
    text = prepare_embedding_text(
        topic="LNO prioritization framework",
        content="Shreyas explains the LNO framework...",
        frameworks=["LNO Framework"],
        tags=["prioritization", "decision-making"],
    )
    assert "LNO" in text
    assert "prioritization" in text
    assert "Shreyas" in text


def test_prepare_embedding_text_handles_empty_frameworks():
    text = prepare_embedding_text(
        topic="General discussion",
        content="Some content here.",
        frameworks=[],
        tags=["growth"],
    )
    assert "Some content here" in text
    assert "growth" in text
