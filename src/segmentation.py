"""Text segmentation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.models import ParsedDocument, ParsedPage, ParsedSection


def _word_count(text: str) -> int:
    return len(text.split())


def _build_labeled_segments(
    items: Iterable[ParsedSection | ParsedPage],
    *,
    fallback_prefix: str,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        text = item.text.strip()
        if not text:
            continue
        segments.append(
            {
                "segment_order": idx,
                "segment_label": item.label or f"{fallback_prefix} {idx}",
                "text_content": text,
                "word_count": _word_count(text),
            }
        )
    return segments


def segment_by_chapters(parsed: ParsedDocument) -> list[dict[str, Any]]:
    """Create segments from parsed chapter-like sections."""
    return _build_labeled_segments(parsed.sections, fallback_prefix="Chapter")


def segment_by_pages(parsed: ParsedDocument) -> list[dict[str, Any]]:
    """Create segments from parsed TEI page break markers."""
    return _build_labeled_segments(parsed.pages, fallback_prefix="Page")


def segment_by_word_count(full_text: str, chunk_size: int = 1200) -> list[dict[str, Any]]:
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
