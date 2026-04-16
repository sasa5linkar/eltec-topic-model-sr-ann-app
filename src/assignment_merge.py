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


def build_document_overview_rows(
    documents: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    segments_by_document: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        document_id = segment.get("document_id")
        if not document_id:
            continue
        segments_by_document.setdefault(document_id, []).append(segment)

    assignments_by_segment_id: dict[str, list[dict[str, Any]]] = {}
    for assignment in assignments:
        segment_id = assignment.get("segment_id")
        if not segment_id:
            continue
        assignments_by_segment_id.setdefault(segment_id, []).append(assignment)

    rows: list[dict[str, Any]] = []
    for document in documents:
        document_id = document.get("id")
        document_segments = segments_by_document.get(document_id, [])
        segment_ids = {segment.get("id") for segment in document_segments if segment.get("id")}

        assigned_segment_ids = {
            segment_id for segment_id in segment_ids if assignments_by_segment_id.get(segment_id)
        }
        assignment_rows = sum(len(assignments_by_segment_id.get(segment_id, [])) for segment_id in segment_ids)
        completed_assignments = sum(
            1
            for segment_id in segment_ids
            for assignment in assignments_by_segment_id.get(segment_id, [])
            if assignment.get("status") == "completed"
        )

        total_segments = len(segment_ids)
        assigned_segments = len(assigned_segment_ids)
        unassigned_segments = max(0, total_segments - assigned_segments)

        rows.append(
            {
                "document_id": document_id,
                "title": document.get("title"),
                "author": document.get("author"),
                "total_segments": total_segments,
                "assigned_segments": assigned_segments,
                "unassigned_segments": unassigned_segments,
                "assignment_rows": assignment_rows,
                "completed_assignments": completed_assignments,
            }
        )

    return rows
