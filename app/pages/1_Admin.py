from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.db import (
    build_export_dataframe,
    create_annotator_account,
    create_assignments,
    create_document,
    create_segments,
    create_theme,
    get_annotation_counts_by_segment,
    get_annotators,
    get_assignments_for_admin,
    get_dashboard_counts,
    get_documents,
    get_segments_by_document,
    get_themes,
)
from src.eltec_parser import parse_eltec_tei_xml
from src.errors import AppError
from src.export_utils import build_export_zip
from src.logging_utils import get_logger, log_event
from src.models import ParsedDocument, ROLE_ADMIN
from src.page_utils import load_authenticated_page
from src.segmentation import segment_by_chapters, segment_by_pages, segment_by_word_count

logger = get_logger("eltec_admin")


def _segment_document(parsed: ParsedDocument, mode: str, chunk_size: int, use_pages: bool) -> list[dict[str, Any]]:
    if use_pages:
        return segment_by_pages(parsed)
    if mode == "By chapters" and parsed.sections:
        return segment_by_chapters(parsed)
    return segment_by_word_count(parsed.full_text, chunk_size)


def _render_dashboard(service_client: Any) -> None:
    st.subheader("Dashboard")
    counts = get_dashboard_counts(service_client)
    columns = st.columns(5)
    columns[0].metric("Documents", counts["documents"])
    columns[1].metric("Segments", counts["segments"])
    columns[2].metric("Assignments", counts["assignments"])
    columns[3].metric("Completed", counts["completed_assignments"])
    columns[4].metric("Annotations", counts["annotations"])


def _render_import_section(service_client: Any, user: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("Upload ELTeC / TEI XML")

    xml_file = st.file_uploader("Select XML file", type=["xml"])
    if xml_file is not None:
        try:
            parsed = parse_eltec_tei_xml(xml_file.getvalue())
            st.session_state["parsed_doc"] = parsed
            st.session_state["source_filename"] = xml_file.name
            st.success("XML parsed successfully.")
            log_event(logger, "info", "admin_xml_parsed", user_id=user.get("id"), file_name=xml_file.name)
        except Exception as exc:  # noqa: BLE001
            st.error(f"XML parsing failed: {exc}")

    parsed = st.session_state.get("parsed_doc")
    if not parsed:
        return

    st.write("**Metadata preview**")
    st.json(
        {
            "title": parsed.title,
            "author": parsed.author,
            "publication_year": parsed.publication_year,
            "sections_detected": len(parsed.sections),
            "pages_detected": len(parsed.pages),
            "text_length_chars": len(parsed.full_text),
        }
    )

    mode = st.radio("Segmentation mode", options=["By chapters", "By word count"], horizontal=True)
    use_page_segmentation = st.checkbox("Use TEI pages for segmentation", value=False) if parsed.pages else False
    chunk_size = 1200
    if mode == "By word count":
        chunk_size = int(st.number_input("Words per segment", min_value=200, max_value=5000, value=1200, step=100))

    if st.button("Prepare segments", type="secondary"):
        st.session_state["candidate_segments"] = _segment_document(parsed, mode, chunk_size, use_page_segmentation)

    candidate_segments = st.session_state.get("candidate_segments", [])
    if not candidate_segments:
        return

    st.write(f"Prepared segments: **{len(candidate_segments)}**")
    st.dataframe(pd.DataFrame(candidate_segments), use_container_width=True)

    if st.button("Confirm document import", type="primary"):
        try:
            document = create_document(
                service_client,
                title=parsed.title,
                author=parsed.author,
                publication_year=parsed.publication_year,
                source_file_name=st.session_state.get("source_filename", "uploaded.xml"),
                created_by=user["id"],
            )
            segments_payload = [{**segment, "document_id": document["id"]} for segment in candidate_segments]
            create_segments(service_client, segments_payload)
            st.success(f"Document saved (ID: {document['id']}) and {len(segments_payload)} segments created.")
            log_event(
                logger,
                "info",
                "admin_import_completed",
                user_id=user.get("id"),
                document_id=document.get("id"),
                segment_count=len(segments_payload),
            )
        except AppError as exc:
            st.error(str(exc))


def _render_annotator_creation(service_client: Any, user: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("Add annotator")
    st.caption("This form creates annotator accounts only. Admin accounts stay in the Supabase dashboard.")

    with st.form("annotator_account_form"):
        annotator_email = st.text_input("Annotator email")
        annotator_full_name = st.text_input("Full name")
        annotator_password = st.text_input("Temporary password", type="password")
        submitted = st.form_submit_button("Create annotator account")

    if not submitted:
        return
    if not annotator_email.strip() or not annotator_password.strip():
        st.warning("Email and password are required.")
        return

    try:
        profile = create_annotator_account(
            service_client,
            email=annotator_email,
            password=annotator_password,
            full_name=annotator_full_name,
        )
        st.success(f"Annotator account created for {profile.get('email')}.")
        st.info("If this person ever needs admin access, change that only in the Supabase dashboard.")
        log_event(
            logger,
            "info",
            "admin_annotator_created",
            admin_user_id=user.get("id"),
            annotator_id=profile.get("id"),
            annotator_email=profile.get("email"),
        )
    except AppError as exc:
        st.error(str(exc))


def _render_themes(service_client: Any) -> None:
    st.markdown("---")
    st.subheader("Themes")
    themes_col, form_col = st.columns([2, 1])

    with themes_col:
        st.dataframe(pd.DataFrame(get_themes(service_client)), use_container_width=True)

    with form_col:
        with st.form("theme_form"):
            new_theme_name = st.text_input("Theme name")
            new_theme_description = st.text_area("Description")
            submitted = st.form_submit_button("Add theme")

        if submitted:
            if not new_theme_name.strip():
                st.warning("Theme name is required.")
            else:
                try:
                    create_theme(service_client, new_theme_name, new_theme_description)
                    st.success("Theme added.")
                except AppError as exc:
                    st.error(str(exc))


def _render_assignments(service_client: Any, user: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("Assign segments to annotators")

    documents = get_documents(service_client)
    annotators = get_annotators(service_client)
    if not documents:
        st.info("There are no documents available for assignment.")
        return
    if not annotators:
        st.info("There are no annotator users in the profiles table.")
        return

    document_options = {f"{document['title']} ({document['id']})": document for document in documents}
    selected_document = document_options[st.selectbox("Document", list(document_options.keys()))]

    segments = get_segments_by_document(service_client, selected_document["id"])
    segments_df = pd.DataFrame(segments)
    if segments_df.empty:
        st.info("This document does not have any segments yet.")
    else:
        st.dataframe(segments_df[["id", "segment_order", "segment_label", "word_count"]], use_container_width=True)

    annotator_options = {f"{annotator.get('email')} ({annotator.get('full_name') or '-'})": annotator for annotator in annotators}
    selected_annotator = annotator_options[st.selectbox("Annotator", list(annotator_options.keys()))]

    selected_segment_ids = st.multiselect(
        "Segments to assign",
        options=[segment["id"] for segment in segments],
        format_func=lambda segment_id: next(
            f"#{segment['segment_order']} - {segment.get('segment_label') or ''}"
            for segment in segments
            if segment["id"] == segment_id
        ),
    )

    if st.button("Assign segments"):
        try:
            created = create_assignments(service_client, selected_segment_ids, selected_annotator["id"], user["id"])
            st.success(f"Created {len(created)} new assignments.")
        except AppError as exc:
            st.error(str(exc))


def _render_progress(service_client: Any) -> None:
    st.markdown("---")
    st.subheader("Progress")

    annotation_counts = get_annotation_counts_by_segment(service_client)
    rows: list[dict[str, Any]] = []
    for assignment in get_assignments_for_admin(service_client):
        segment = assignment.get("segments") or {}
        document = segment.get("documents") or {}
        profile = assignment.get("profiles") or {}
        rows.append(
            {
                "document": document.get("title"),
                "segment_order": segment.get("segment_order"),
                "annotator": profile.get("email") or profile.get("full_name"),
                "status": assignment.get("status"),
                "annotations_count": annotation_counts.get(segment.get("id"), 0),
                "assigned_at": assignment.get("assigned_at"),
                "completed_at": assignment.get("completed_at"),
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def _render_export(service_client: Any, user: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("Export annotated data")

    if not st.button("Generate ZIP export"):
        return

    try:
        export_df = build_export_dataframe(service_client)
        zip_bytes = build_export_zip(export_df)
        st.download_button(
            label="Download export.zip",
            data=zip_bytes,
            file_name="export.zip",
            mime="application/zip",
        )
        st.success("ZIP export is ready.")
        log_event(logger, "info", "admin_export_generated", user_id=user.get("id"), row_count=len(export_df))
    except AppError as exc:
        st.error(str(exc))


_, service_client, current_user = load_authenticated_page(
    page_title="Admin",
    heading="Admin panel",
    allowed_role=ROLE_ADMIN,
)

_render_dashboard(service_client)
_render_import_section(service_client, current_user)
_render_annotator_creation(service_client, current_user)
_render_themes(service_client)
_render_assignments(service_client, current_user)
_render_progress(service_client)
_render_export(service_client, current_user)
