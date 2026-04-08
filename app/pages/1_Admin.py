from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.auth import get_current_user
from src.db import (
    build_export_dataframe,
    create_assignments,
    create_document,
    create_segments,
    create_theme,
    get_annotation_counts_by_segment,
    get_annotators,
    get_assignments_for_admin,
    get_client,
    get_dashboard_counts,
    get_documents,
    get_segments_by_document,
    get_themes,
)
from src.eltec_parser import parse_eltec_tei_xml
from src.errors import AppError
from src.export_utils import build_export_zip
from src.logging_utils import get_logger, log_event
from src.models import ROLE_ADMIN
from src.segmentation import segment_by_chapters, segment_by_word_count

logger = get_logger("eltec_admin")

st.set_page_config(page_title="Admin", layout="wide")
st.title("Admin panel")

try:
    anon_client = get_client(use_service_role=False)
    service_client = get_client(use_service_role=True)
    user = get_current_user(anon_client, service_client)
except AppError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Greška pri povezivanju: {exc}")
    st.stop()

if user.get("role") != ROLE_ADMIN:
    st.warning("Ova stranica je dostupna samo admin korisnicima.")
    st.stop()

# 1) Dashboard
st.subheader("Dashboard")
counts = get_dashboard_counts(service_client)
cols = st.columns(5)
cols[0].metric("Dokumenti", counts["documents"])
cols[1].metric("Segmenti", counts["segments"])
cols[2].metric("Dodele", counts["assignments"])
cols[3].metric("Završeno", counts["completed_assignments"])
cols[4].metric("Anotacije", counts["annotations"])

st.markdown("---")

# 2-4) Upload + parse + segment
st.subheader("Upload ELTeC / TEI XML")
xml_file = st.file_uploader("Izaberite XML fajl", type=["xml"])
if xml_file is not None:
    try:
        parsed = parse_eltec_tei_xml(xml_file.getvalue())
        st.session_state["parsed_doc"] = parsed
        st.session_state["source_filename"] = xml_file.name
        st.success("XML uspešno parsiran.")
        log_event(logger, "info", "admin_xml_parsed", user_id=user.get("id"), file_name=xml_file.name)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Greška pri parsiranju XML-a: {exc}")

parsed = st.session_state.get("parsed_doc")
if parsed:
    st.write("**Preview metapodataka**")
    st.json(
        {
            "title": parsed.title,
            "author": parsed.author,
            "publication_year": parsed.publication_year,
            "sections_detected": len(parsed.sections),
            "text_length_chars": len(parsed.full_text),
        }
    )

    mode = st.radio(
        "Režim segmentacije",
        options=["Po poglavljima", "Po broju reči"],
        horizontal=True,
    )
    chunk_size = 1200
    if mode == "Po broju reči":
        chunk_size = st.number_input("Reči po segmentu", min_value=200, max_value=5000, value=1200, step=100)

    if st.button("Pripremi segmente", type="secondary"):
        if mode == "Po poglavljima" and parsed.sections:
            candidate_segments = segment_by_chapters(parsed)
        else:
            candidate_segments = segment_by_word_count(parsed.full_text, int(chunk_size))
        st.session_state["candidate_segments"] = candidate_segments

    candidate_segments = st.session_state.get("candidate_segments", [])
    if candidate_segments:
        st.write(f"Pripremljeno segmenata: **{len(candidate_segments)}**")
        st.dataframe(pd.DataFrame(candidate_segments), use_container_width=True)

        if st.button("Potvrdi import dokumenta i segmenata", type="primary"):
            try:
                doc = create_document(
                    service_client,
                    title=parsed.title,
                    author=parsed.author,
                    publication_year=parsed.publication_year,
                    source_file_name=st.session_state.get("source_filename", "uploaded.xml"),
                    created_by=user["id"],
                )
                segments_payload = [{**seg, "document_id": doc["id"]} for seg in candidate_segments]
                create_segments(service_client, segments_payload)
                st.success(f"Dokument sačuvan (ID: {doc['id']}) i {len(segments_payload)} segmenata kreirano.")
                log_event(
                    logger,
                    "info",
                    "admin_import_completed",
                    user_id=user.get("id"),
                    document_id=doc.get("id"),
                    segment_count=len(segments_payload),
                )
            except AppError as exc:
                st.error(str(exc))

st.markdown("---")

# 5) Themes
st.subheader("Teme")
col1, col2 = st.columns([2, 1])
with col1:
    themes = get_themes(service_client)
    st.dataframe(pd.DataFrame(themes), use_container_width=True)
with col2:
    with st.form("theme_form"):
        new_theme_name = st.text_input("Naziv teme")
        new_theme_desc = st.text_area("Opis")
        submitted = st.form_submit_button("Dodaj temu")
    if submitted:
        if not new_theme_name.strip():
            st.warning("Naziv teme je obavezan.")
        else:
            try:
                create_theme(service_client, new_theme_name, new_theme_desc)
                st.success("Tema dodata.")
            except AppError as exc:
                st.error(str(exc))

st.markdown("---")

# 6) Assignments
st.subheader("Dodela segmenata anotatorima")
documents = get_documents(service_client)
annotators = get_annotators(service_client)
if not documents:
    st.info("Nema dokumenata za dodelu.")
elif not annotators:
    st.info("Nema annotator korisnika u profiles tabeli.")
else:
    doc_option_map = {f"{d['title']} ({d['id']})": d for d in documents}
    selected_doc_label = st.selectbox("Dokument", list(doc_option_map.keys()))
    selected_doc = doc_option_map[selected_doc_label]

    segments = get_segments_by_document(service_client, selected_doc["id"])
    segments_df = pd.DataFrame(segments)
    if not segments_df.empty:
        st.dataframe(segments_df[["id", "segment_order", "segment_label", "word_count"]], use_container_width=True)
    else:
        st.info("Dokument trenutno nema segmenata.")

    ann_map = {f"{a.get('email')} ({a.get('full_name') or '-'})": a for a in annotators}
    selected_ann_label = st.selectbox("Annotator", list(ann_map.keys()))
    selected_annotator = ann_map[selected_ann_label]

    selected_segment_ids = st.multiselect(
        "Segmenti za dodelu",
        options=[s["id"] for s in segments],
        format_func=lambda sid: next(
            f"#{s['segment_order']} - {s.get('segment_label') or ''}" for s in segments if s["id"] == sid
        ),
    )

    if st.button("Dodeli segmente"):
        try:
            created = create_assignments(service_client, selected_segment_ids, selected_annotator["id"], user["id"])
            st.success(f"Kreirano {len(created)} novih dodela.")
        except AppError as exc:
            st.error(str(exc))

st.markdown("---")

# 7) Progress
st.subheader("Praćenje progresa")
admin_assignments = get_assignments_for_admin(service_client)
annotation_counts = get_annotation_counts_by_segment(service_client)
progress_rows = []
for row in admin_assignments:
    segment = row.get("segments") or {}
    document = segment.get("documents") or {}
    profile = row.get("profiles") or {}
    progress_rows.append(
        {
            "document": document.get("title"),
            "segment_order": segment.get("segment_order"),
            "annotator": profile.get("email") or profile.get("full_name"),
            "status": row.get("status"),
            "annotations_count": annotation_counts.get(segment.get("id"), 0),
            "assigned_at": row.get("assigned_at"),
            "completed_at": row.get("completed_at"),
        }
    )
st.dataframe(pd.DataFrame(progress_rows), use_container_width=True)

st.markdown("---")

# 8) Export
st.subheader("Izvoz anotiranih podataka")
if st.button("Generiši ZIP export"):
    try:
        export_df = build_export_dataframe(service_client)
        zip_bytes = build_export_zip(export_df)
        st.download_button(
            label="Preuzmi export.zip",
            data=zip_bytes,
            file_name="export.zip",
            mime="application/zip",
        )
        st.success("ZIP je spreman za preuzimanje.")
        log_event(logger, "info", "admin_export_generated", user_id=user.get("id"), row_count=len(export_df))
    except AppError as exc:
        st.error(str(exc))
