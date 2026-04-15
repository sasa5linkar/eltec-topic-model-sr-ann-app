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
    get_annotations_for_segment_and_user,
    get_assignments_for_annotator,
    get_themes,
    mark_assignment_completed,
    save_annotations_for_segment,
)
from src.errors import AppError
from src.logging_utils import get_logger, log_event
from src.models import ROLE_ANNOTATOR
from src.page_utils import load_authenticated_page

logger = get_logger("eltec_annotator")


def _build_task_table(assignments: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for assignment in assignments:
        segment = assignment.get("segments") or {}
        document = segment.get("documents") or {}
        rows.append(
            {
                "assignment_id": assignment.get("id"),
                "document_title": document.get("title"),
                "segment_order": segment.get("segment_order"),
                "segment_label": segment.get("segment_label"),
                "status": assignment.get("status"),
            }
        )
    return pd.DataFrame(rows)


def _task_label(task: dict[str, Any]) -> str:
    segment = task.get("segments") or {}
    document = segment.get("documents") or {}
    return f"{document.get('title')} / #{segment.get('segment_order')} / {task.get('status')}"


anon_client, _, current_user = load_authenticated_page(
    page_title="Annotator",
    heading="Annotator panel",
    allowed_role=ROLE_ANNOTATOR,
)

assignments = get_assignments_for_annotator(anon_client, current_user["id"])
if not assignments:
    st.info("You do not have any assigned segments.")
    st.stop()
    raise SystemExit(0)

st.subheader("My tasks")
st.dataframe(_build_task_table(assignments), use_container_width=True)

options = {_task_label(task): task for task in assignments}
selected_task = options[st.selectbox("Open task", list(options.keys()))]
selected_segment = selected_task.get("segments") or {}
selected_document = selected_segment.get("documents") or {}

st.markdown("---")
st.subheader("Segment annotation")

meta_col1, meta_col2 = st.columns(2)
meta_col1.write(f"**Document:** {selected_document.get('title')}")
meta_col1.write(f"**Author:** {selected_document.get('author')}")
meta_col2.write(f"**Segment:** #{selected_segment.get('segment_order')} - {selected_segment.get('segment_label')}")
meta_col2.write(f"**Status:** {selected_task.get('status')}")

st.markdown("**Segment text**")
st.text_area(
    "segment_text",
    value=selected_segment.get("text_content", ""),
    height=260,
    disabled=True,
    label_visibility="collapsed",
)

themes = get_themes(anon_client)
theme_options = {f"{theme.get('name')} ({theme.get('id')})": theme.get("id") for theme in themes}

existing_annotations = get_annotations_for_segment_and_user(anon_client, selected_segment["id"], current_user["id"])
preselected_theme_ids = [annotation["theme_id"] for annotation in existing_annotations]
default_note = existing_annotations[0].get("note", "") if existing_annotations else ""

selected_theme_labels = st.multiselect(
    "Themes",
    options=list(theme_options.keys()),
    default=[label for label, theme_id in theme_options.items() if theme_id in preselected_theme_ids],
)
note = st.text_area("Note (optional)", value=default_note)

save_col, complete_col = st.columns(2)
with save_col:
    if st.button("Save annotation", type="primary"):
        try:
            selected_theme_ids = [theme_options[label] for label in selected_theme_labels]
            save_annotations_for_segment(
                anon_client,
                segment_id=selected_segment["id"],
                annotator_id=current_user["id"],
                theme_ids=selected_theme_ids,
                note=note,
            )
            st.success("Annotation saved.")
            log_event(
                logger,
                "info",
                "annotator_saved_annotation",
                user_id=current_user.get("id"),
                segment_id=selected_segment.get("id"),
                theme_count=len(selected_theme_ids),
            )
        except AppError as exc:
            st.error(str(exc))

with complete_col:
    if st.button("Mark task as completed"):
        try:
            mark_assignment_completed(anon_client, selected_task["id"])
            st.success("Task marked as completed. Refresh the page to see the updated status.")
        except AppError as exc:
            st.error(str(exc))
