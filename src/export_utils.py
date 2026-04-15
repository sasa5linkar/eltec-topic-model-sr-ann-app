"""ZIP export helpers for annotated segment data."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


def build_export_zip(df: pd.DataFrame) -> bytes:
    """Build a ZIP file bytes payload with metadata.tsv and per-segment text files."""
    export_df = df.copy()
    if export_df.empty:
        export_df = pd.DataFrame(
            columns=[
                "document_id",
                "title",
                "author",
                "publication_year",
                "segment_id",
                "segment_order",
                "segment_label",
                "relative_text_path",
                "annotator_id",
                "annotator_email",
                "status",
                "themes",
                "note",
                "text_content",
            ]
        )

    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as zf:
        for row in export_df.to_dict(orient="records"):
            path = f"export/{row['relative_text_path']}"
            zf.writestr(path, (row.get("text_content") or "").strip())

        metadata_columns = [
            "document_id",
            "title",
            "author",
            "publication_year",
            "segment_id",
            "segment_order",
            "segment_label",
            "relative_text_path",
            "annotator_id",
            "annotator_email",
            "status",
            "themes",
            "note",
        ]
        metadata_tsv = export_df[metadata_columns].fillna("").to_csv(sep="\t", index=False)
        zf.writestr("export/metadata.tsv", metadata_tsv)

    output.seek(0)
    return output.getvalue()
