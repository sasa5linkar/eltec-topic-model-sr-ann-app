"""Shared models and schema constants for the MVP annotation app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TableNames:
    """Logical table names centralized in one place for easy schema changes."""

    profiles: str = "profiles"
    documents: str = "documents"
    themes: str = "themes"
    segments: str = "segments"
    assignments: str = "assignments"
    annotations: str = "annotations"


TABLES = TableNames()


ROLE_ADMIN = "admin"
ROLE_ANNOTATOR = "annotator"

STATUS_ASSIGNED = "assigned"
STATUS_COMPLETED = "completed"


@dataclass
class ParsedSection:
    """One parsed section/chapter extracted from ELTeC/TEI XML."""

    label: str
    text: str


@dataclass
class ParsedDocument:
    """Result object returned by ELTeC parser."""

    title: str
    author: str
    publication_year: Optional[int]
    full_text: str
    sections: list[ParsedSection]
