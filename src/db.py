"""Database access layer for Supabase."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, TypeVar
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from src.assignment_merge import build_document_overview_rows, index_by_id as _index_by_id, merge_assignment_rows
from src.errors import map_supabase_error
from src.models import ROLE_ANNOTATOR, STATUS_ASSIGNED, STATUS_COMPLETED, TABLES

T = TypeVar("T")


def _safe(operation: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Exception as exc:  # noqa: BLE001
        raise map_supabase_error(exc, operation) from exc


def _bypass_proxy_for_host(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return

    for env_name in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(env_name, "")
        entries = [entry.strip() for entry in current.split(",") if entry.strip()]
        if host not in entries:
            entries.append(host)
            os.environ[env_name] = ",".join(entries)


@st.cache_resource
def get_client(use_service_role: bool = False) -> Client:
    """Return a cached Supabase client from Streamlit secrets."""
    url = st.secrets.get("SUPABASE_URL")
    key_name = "SUPABASE_SERVICE_ROLE_KEY" if use_service_role else "SUPABASE_ANON_KEY"
    key = st.secrets.get(key_name)

    if not url or not key:
        raise RuntimeError(
            f"Missing Supabase secrets. Expected SUPABASE_URL and {key_name} in .streamlit/secrets.toml"
        )

    _bypass_proxy_for_host(url)
    return _safe("create_client", lambda: create_client(url, key))


def _execute_select(client: Client, table: str, select_expr: str = "*") -> list[dict[str, Any]]:
    return _safe(
        f"select {table}",
        lambda: client.table(table).select(select_expr).execute().data or [],
    )



def get_profiles(client: Client) -> list[dict[str, Any]]:
    return _execute_select(client, TABLES.profiles)


def get_annotators(client: Client) -> list[dict[str, Any]]:
    return _safe(
        "get_annotators",
        lambda: (
            client.table(TABLES.profiles)
            .select("*")
            .eq("role", "annotator")
            .order("email")
            .execute()
            .data
            or []
        ),
    )


def get_documents(client: Client) -> list[dict[str, Any]]:
    return _safe(
        "get_documents",
        lambda: client.table(TABLES.documents).select("*").order("created_at", desc=True).execute().data or [],
    )


def get_all_segments(client: Client) -> list[dict[str, Any]]:
    return _safe(
        "get_all_segments",
        lambda: client.table(TABLES.segments).select("*").order("document_id").order("segment_order").execute().data or [],
    )


def create_document(
    client: Client,
    title: str,
    author: str,
    publication_year: Optional[int],
    source_file_name: str,
    created_by: str,
) -> dict[str, Any]:
    payload = {
        "title": title,
        "author": author,
        "publication_year": publication_year,
        "source_file_name": source_file_name,
        "created_by": created_by,
    }
    return _safe("create_document", lambda: client.table(TABLES.documents).insert(payload).execute().data[0])


def create_segments(client: Client, segments: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = list(segments)
    if not payload:
        return []
    return _safe("create_segments", lambda: client.table(TABLES.segments).insert(payload).execute().data or [])


def delete_document(client: Client, document_id: str) -> dict[str, int]:
    segment_rows = _safe(
        "delete_document.fetch_segments",
        lambda: client.table(TABLES.segments).select("id").eq("document_id", document_id).execute().data or [],
    )
    segment_ids = [row["id"] for row in segment_rows if row.get("id")]

    deleted_annotations = []
    deleted_assignments = []
    if segment_ids:
        deleted_annotations = _safe(
            "delete_document.annotations",
            lambda: client.table(TABLES.annotations).delete().in_("segment_id", segment_ids).execute().data or [],
        )
        deleted_assignments = _safe(
            "delete_document.assignments",
            lambda: client.table(TABLES.assignments).delete().in_("segment_id", segment_ids).execute().data or [],
        )

    deleted_segments = _safe(
        "delete_document.segments",
        lambda: client.table(TABLES.segments).delete().eq("document_id", document_id).execute().data or [],
    )
    deleted_documents = _safe(
        "delete_document.document",
        lambda: client.table(TABLES.documents).delete().eq("id", document_id).execute().data or [],
    )

    return {
        "documents_deleted": len(deleted_documents),
        "segments_deleted": len(deleted_segments),
        "assignments_deleted": len(deleted_assignments),
        "annotations_deleted": len(deleted_annotations),
    }


def get_segments_by_document(client: Client, document_id: str) -> list[dict[str, Any]]:
    return _safe(
        "get_segments_by_document",
        lambda: (
            client.table(TABLES.segments)
            .select("*")
            .eq("document_id", document_id)
            .order("segment_order")
            .execute()
            .data
            or []
        ),
    )


def get_themes(client: Client) -> list[dict[str, Any]]:
    return _safe("get_themes", lambda: client.table(TABLES.themes).select("*").order("name").execute().data or [])


def create_theme(client: Client, name: str, description: str) -> dict[str, Any]:
    return _safe(
        "create_theme",
        lambda: client.table(TABLES.themes).insert({"name": name.strip(), "description": description.strip()}).execute().data[0],
    )


def create_annotator_account(
    client: Client,
    *,
    email: str,
    password: str,
    full_name: str,
) -> dict[str, Any]:
    cleaned_email = email.strip().lower()
    cleaned_name = full_name.strip() or None
    user_metadata = {"role": ROLE_ANNOTATOR}
    if cleaned_name:
        user_metadata["full_name"] = cleaned_name

    auth_user = _safe(
        "create_annotator_account.auth.create_user",
        lambda: client.auth.admin.create_user(
            {
                "email": cleaned_email,
                "password": password,
                "email_confirm": True,
                "user_metadata": user_metadata,
            }
        ).user,
    )

    try:
        profile = _safe(
            "create_annotator_account.profiles.insert",
            lambda: client.table(TABLES.profiles)
            .insert(
                {
                    "id": auth_user.id,
                    "email": cleaned_email,
                    "full_name": cleaned_name,
                    "role": ROLE_ANNOTATOR,
                }
            )
            .execute()
            .data[0],
        )
    except Exception:
        _safe(
            "create_annotator_account.auth.rollback_delete_user",
            lambda: client.auth.admin.delete_user(auth_user.id),
        )
        raise

    return profile


def create_assignments(
    client: Client,
    segment_ids: list[str],
    annotator_id: str,
    assigned_by: str,
) -> list[dict[str, Any]]:
    if not segment_ids:
        return []

    existing = _safe(
        "create_assignments.fetch_existing",
        lambda: (
            client.table(TABLES.assignments)
            .select("segment_id")
            .eq("annotator_id", annotator_id)
            .in_("segment_id", segment_ids)
            .execute()
            .data
            or []
        ),
    )
    existing_segment_ids = {row["segment_id"] for row in existing}
    new_segment_ids = [seg_id for seg_id in segment_ids if seg_id not in existing_segment_ids]

    payload = [
        {
            "segment_id": seg_id,
            "annotator_id": annotator_id,
            "assigned_by": assigned_by,
            "status": STATUS_ASSIGNED,
        }
        for seg_id in new_segment_ids
    ]
    if not payload:
        return []

    return _safe("create_assignments.insert", lambda: client.table(TABLES.assignments).insert(payload).execute().data or [])



def _get_assignment_enriched_rows(client: Client, annotator_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Fetch assignments and enrich rows without relying on FK relation names."""
    assignments = _safe(
        "get_assignments.base",
        lambda: (
            client.table(TABLES.assignments)
            .select("*")
            .eq("annotator_id", annotator_id)
            .order("assigned_at", desc=False)
            .execute()
            .data
            if annotator_id
            else client.table(TABLES.assignments).select("*").order("assigned_at", desc=False).execute().data
        )
        or [],
    )

    if not assignments:
        return []

    segment_ids = sorted({row["segment_id"] for row in assignments if row.get("segment_id")})
    annotator_ids = sorted({row["annotator_id"] for row in assignments if row.get("annotator_id")})

    segments = _safe(
        "get_assignments.segments",
        lambda: client.table(TABLES.segments).select("*").in_("id", segment_ids).execute().data or [],
    )
    document_ids = sorted({row["document_id"] for row in segments if row.get("document_id")})
    documents = _safe(
        "get_assignments.documents",
        lambda: client.table(TABLES.documents).select("*").in_("id", document_ids).execute().data or [],
    )
    profiles = _safe(
        "get_assignments.profiles",
        lambda: client.table(TABLES.profiles).select("*").in_("id", annotator_ids).execute().data or [],
    )

    return merge_assignment_rows(assignments, segments, documents, profiles)


def get_assignments_for_admin(client: Client) -> list[dict[str, Any]]:
    rows = _get_assignment_enriched_rows(client)
    return sorted(rows, key=lambda r: r.get("assigned_at") or "", reverse=True)


def get_document_overview(client: Client) -> list[dict[str, Any]]:
    documents = get_documents(client)
    segments = get_all_segments(client)
    assignments = _safe(
        "get_document_overview.assignments",
        lambda: client.table(TABLES.assignments).select("segment_id,status").execute().data or [],
    )
    return build_document_overview_rows(documents, segments, assignments)


def get_assignments_for_annotator(client: Client, user_id: str) -> list[dict[str, Any]]:
    return _get_assignment_enriched_rows(client, annotator_id=user_id)


def get_annotations_for_segment_and_user(client: Client, segment_id: str, annotator_id: str) -> list[dict[str, Any]]:
    return _safe(
        "get_annotations_for_segment_and_user",
        lambda: (
            client.table(TABLES.annotations)
            .select("*")
            .eq("segment_id", segment_id)
            .eq("annotator_id", annotator_id)
            .execute()
            .data
            or []
        ),
    )


def save_annotations_for_segment(
    client: Client,
    *,
    segment_id: str,
    annotator_id: str,
    theme_ids: list[str],
    note: str,
) -> list[dict[str, Any]]:
    _safe(
        "save_annotations_for_segment.delete_previous",
        lambda: client.table(TABLES.annotations).delete().eq("segment_id", segment_id).eq("annotator_id", annotator_id).execute(),
    )

    if not theme_ids:
        return []

    cleaned_note = note.strip() if note else None
    payload = [
        {
            "segment_id": segment_id,
            "annotator_id": annotator_id,
            "theme_id": theme_id,
            "note": cleaned_note,
        }
        for theme_id in theme_ids
    ]
    return _safe("save_annotations_for_segment.insert", lambda: client.table(TABLES.annotations).insert(payload).execute().data or [])


def mark_assignment_completed(client: Client, assignment_id: str) -> dict[str, Any]:
    return _safe(
        "mark_assignment_completed",
        lambda: (
            client.table(TABLES.assignments)
            .update({"status": STATUS_COMPLETED, "completed_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", assignment_id)
            .execute()
            .data[0]
        ),
    )


def get_annotation_counts_by_segment(client: Client) -> dict[str, int]:
    rows = _safe(
        "get_annotation_counts_by_segment",
        lambda: client.table(TABLES.annotations).select("segment_id").execute().data or [],
    )
    counts: dict[str, int] = {}
    for row in rows:
        segment_id = row.get("segment_id")
        if segment_id:
            counts[segment_id] = counts.get(segment_id, 0) + 1
    return counts


def get_dashboard_counts(client: Client) -> dict[str, int]:
    return {
        "documents": len(_execute_select(client, TABLES.documents, "id")),
        "segments": len(_execute_select(client, TABLES.segments, "id")),
        "assignments": len(_execute_select(client, TABLES.assignments, "id")),
        "completed_assignments": len(
            _safe(
                "get_dashboard_counts.completed",
                lambda: client.table(TABLES.assignments).select("id").eq("status", STATUS_COMPLETED).execute().data or [],
            )
        ),
        "annotations": len(_execute_select(client, TABLES.annotations, "id")),
    }


def build_export_dataframe(client: Client) -> pd.DataFrame:
    assignments = _get_assignment_enriched_rows(client)
    annotations = _safe(
        "build_export_dataframe.annotations",
        lambda: client.table(TABLES.annotations).select("segment_id,annotator_id,theme_id,note").execute().data or [],
    )
    themes = get_themes(client)
    themes_by_id = _index_by_id(themes)

    ann_index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in annotations:
        key = (row["segment_id"], row["annotator_id"])
        ann_index.setdefault(key, {"themes": [], "note": None})

        theme = themes_by_id.get(row.get("theme_id"), {})
        if theme.get("name"):
            ann_index[key]["themes"].append(theme["name"])
        if row.get("note") and not ann_index[key]["note"]:
            ann_index[key]["note"] = row["note"]

    export_rows: list[dict[str, Any]] = []
    for assignment in assignments:
        segment = assignment.get("segments") or {}
        doc = segment.get("documents") or {}
        profile = assignment.get("profiles") or {}
        key = (assignment.get("segment_id"), assignment.get("annotator_id"))
        ann_data = ann_index.get(key, {"themes": [], "note": None})

        relative_text_path = f"texts/{doc.get('id')}_{segment.get('segment_order')}.txt"
        export_rows.append(
            {
                "document_id": doc.get("id"),
                "title": doc.get("title"),
                "author": doc.get("author"),
                "publication_year": doc.get("publication_year"),
                "segment_id": segment.get("id"),
                "segment_order": segment.get("segment_order"),
                "segment_label": segment.get("segment_label"),
                "relative_text_path": relative_text_path,
                "annotator_id": assignment.get("annotator_id"),
                "annotator_email": profile.get("email"),
                "status": assignment.get("status"),
                "themes": "|".join(sorted(set(ann_data["themes"]))),
                "note": ann_data.get("note"),
                "text_content": segment.get("text_content", ""),
            }
        )

    return pd.DataFrame(export_rows)
