from indexer.taxonomy import TAXONOMY, validate_tags


def test_taxonomy_has_minimum_tags():
    assert len(TAXONOMY) >= 25


def test_taxonomy_tags_are_lowercase_kebab():
    for tag in TAXONOMY:
        assert tag == tag.lower()
        assert " " not in tag


def test_validate_tags_filters_invalid():
    valid = validate_tags(["pricing", "not-a-real-tag-xyz", "retention"])
    assert "pricing" in valid
    assert "retention" in valid
    assert "not-a-real-tag-xyz" not in valid


def test_validate_tags_returns_list():
    result = validate_tags(["pricing"])
    assert isinstance(result, list)
