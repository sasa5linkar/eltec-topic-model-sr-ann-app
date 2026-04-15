"""Pure merge utilities for assignment enrichment."""

from __future__ import annotations

from typing import Any


def index_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in rows if row.get("id") is not None}


def merge_assignment_rows(
    assignments: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    segments_by_id = index_by_id(segments)
    documents_by_id = index_by_id(documents)
    profiles_by_id = index_by_id(profiles)

    enriched: list[dict[str, Any]] = []
    for row in assignments:
        seg = segments_by_id.get(row.get("segment_id"), {})
        doc = documents_by_id.get(seg.get("document_id"), {}) if seg else {}
        profile = profiles_by_id.get(row.get("annotator_id"), {})
        enriched.append(
            {
                **row,
                "segments": {**seg, "documents": doc},
                "profiles": profile,
            }
        )
    return enriched
