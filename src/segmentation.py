"""Text segmentation helpers."""

from __future__ import annotations

from src.models import ParsedDocument


def _word_count(text: str) -> int:
    return len(text.split())


def segment_by_chapters(parsed: ParsedDocument) -> list[dict]:
    """Create segments from parsed chapter-like sections."""
    segments: list[dict] = []
    for idx, section in enumerate(parsed.sections, start=1):
        text = section.text.strip()
        if not text:
            continue
        segments.append(
            {
                "segment_order": idx,
                "segment_label": section.label or f"Chapter {idx}",
                "text_content": text,
                "word_count": _word_count(text),
            }
        )
    return segments


def segment_by_word_count(full_text: str, chunk_size: int = 1200) -> list[dict]:
    """Fallback segmentation by fixed number of words."""
    words = full_text.split()
    if not words:
        return []

    segments: list[dict] = []
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i : i + chunk_size]
        order = len(segments) + 1
        text = " ".join(chunk_words)
        segments.append(
            {
                "segment_order": order,
                "segment_label": f"Segment {order}",
                "text_content": text,
                "word_count": len(chunk_words),
            }
        )
    return segments
