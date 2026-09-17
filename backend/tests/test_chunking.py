from backend.app.agent.chunking import chunk_text


def test_chunk_text_short_text_is_single_chunk():
    assert chunk_text("hello world") == ["hello world"]


def test_chunk_text_empty_or_whitespace_is_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_splits_long_text_into_multiple_chunks():
    long_text = " ".join(f"word{i}" for i in range(500))

    chunks = chunk_text(long_text, chunk_size=100, overlap=20)

    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_chunk_text_covers_the_whole_input():
    long_text = " ".join(f"word{i}" for i in range(500))

    chunks = chunk_text(long_text, chunk_size=100, overlap=20)

    all_words = set(long_text.split())
    covered_words = set(" ".join(chunks).split())
    assert all_words <= covered_words


def test_chunk_text_terminates_with_tiny_overlap_relative_to_chunk_size():
    long_text = "x" * 5000

    chunks = chunk_text(long_text, chunk_size=200, overlap=190)

    assert len(chunks) > 1
