"""Fixed-size text chunking for document ingestion.

Deliberately simple: fixed character count with overlap, no tokenizer, no
sentence/semantic awareness. Good enough for chunking short ops manuals and
runbooks into embeddable pieces; not intended to be a general-purpose
document-processing pipeline.
"""

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150


def chunk_text(
    text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    if len(stripped) <= chunk_size:
        return [stripped]

    chunks: list[str] = []
    start = 0
    text_len = len(stripped)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Prefer to break on a whitespace boundary rather than mid-word,
        # as long as that doesn't shrink the chunk to nothing useful.
        if end < text_len:
            boundary = stripped.rfind(" ", start, end)
            if boundary > start:
                end = boundary

        chunk = stripped[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        start = end - overlap
        if start <= 0:
            start = end

    return chunks
