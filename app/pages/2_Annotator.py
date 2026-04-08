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
    get_annotations_for_segment_and_user,
    get_assignments_for_annotator,
    get_client,
    get_themes,
    mark_assignment_completed,
    save_annotations_for_segment,
)
from src.models import ROLE_ANNOTATOR

st.set_page_config(page_title="Annotator", layout="wide")
st.title("Annotator panel")

try:
    client = get_client(use_service_role=True)
    user = get_current_user(client)
except Exception as exc:
    st.error(f"Greška pri povezivanju: {exc}")
    st.stop()

if user.get("role") != ROLE_ANNOTATOR:
    st.warning("Ova stranica je dostupna samo annotator korisnicima.")
    st.stop()

assignments = get_assignments_for_annotator(client, user["id"])
if not assignments:
    st.info("Nemate dodeljenih segmenata.")
    st.stop()

st.subheader("Moji zadaci")
task_rows = []
for task in assignments:
    seg = task.get("segments") or {}
    doc = seg.get("documents") or {}
    task_rows.append(
        {
            "assignment_id": task.get("id"),
            "document_title": doc.get("title"),
            "segment_order": seg.get("segment_order"),
            "segment_label": seg.get("segment_label"),
            "status": task.get("status"),
        }
    )
st.dataframe(pd.DataFrame(task_rows), use_container_width=True)

options = {
    f"{(t.get('segments') or {}).get('documents', {}).get('title')} / #{(t.get('segments') or {}).get('segment_order')} / {t.get('status')}": t
    for t in assignments
}
selected_label = st.selectbox("Otvori zadatak", list(options.keys()))
selected_task = options[selected_label]
selected_segment = selected_task.get("segments") or {}
selected_document = selected_segment.get("documents") or {}

st.markdown("---")
st.subheader("Anotacija segmenta")

meta_col1, meta_col2 = st.columns(2)
meta_col1.write(f"**Dokument:** {selected_document.get('title')}")
meta_col1.write(f"**Autor:** {selected_document.get('author')}")
meta_col2.write(f"**Segment:** #{selected_segment.get('segment_order')} - {selected_segment.get('segment_label')}")
meta_col2.write(f"**Status:** {selected_task.get('status')}")

st.markdown("**Tekst segmenta**")
st.text_area(
    "segment_text",
    value=selected_segment.get("text_content", ""),
    height=260,
    disabled=True,
    label_visibility="collapsed",
)

themes = get_themes(client)
theme_options = {f"{t.get('name')} ({t.get('id')})": t.get("id") for t in themes}

existing = get_annotations_for_segment_and_user(client, selected_segment["id"], user["id"])
preselected_theme_ids = [a["theme_id"] for a in existing]
default_note = existing[0].get("note", "") if existing else ""

selected_theme_labels = st.multiselect(
    "Teme",
    options=list(theme_options.keys()),
    default=[label for label, tid in theme_options.items() if tid in preselected_theme_ids],
)
note = st.text_area("Beleška (opciono)", value=default_note)

save_col, complete_col = st.columns(2)
with save_col:
    if st.button("Sačuvaj anotaciju", type="primary"):
        try:
            selected_theme_ids = [theme_options[label] for label in selected_theme_labels]
            save_annotations_for_segment(
                client,
                segment_id=selected_segment["id"],
                annotator_id=user["id"],
                theme_ids=selected_theme_ids,
                note=note,
            )
            st.success("Anotacija je sačuvana.")
        except Exception as exc:
            st.error(f"Greška pri čuvanju anotacije: {exc}")

with complete_col:
    if st.button("Označi zadatak kao završen"):
        try:
            mark_assignment_completed(client, selected_task["id"])
            st.success("Zadatak označen kao završen. Osvežite stranicu.")
        except Exception as exc:
            st.error(f"Greška pri završavanju zadatka: {exc}")
