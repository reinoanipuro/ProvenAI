from backend.rag import _split_text


def test_split_text_keeps_all_content():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = _split_text(text, size=100, overlap=20)

    assert len(chunks) > 1
    assert chunks[0].startswith("word0")
    assert chunks[-1].endswith("word499")


def test_split_text_rejects_invalid_overlap():
    try:
        _split_text("text", size=10, overlap=10)
    except ValueError as error:
        assert "greater than" in str(error)
    else:
        raise AssertionError("Expected invalid chunk configuration to fail.")
