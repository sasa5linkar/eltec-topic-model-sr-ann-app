"""Parser utilities for ELTeC / TEI XML files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from src.models import ParsedDocument, ParsedSection


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _first_text(root: ET.Element, xpaths: list[str], ns: dict[str, str]) -> Optional[str]:
    for xpath in xpaths:
        found = root.find(xpath, ns)
        if found is not None:
            text = _clean_text("".join(found.itertext()))
            if text:
                return text
    return None


def _extract_year(root: ET.Element, ns: dict[str, str]) -> Optional[int]:
    year_text = _first_text(
        root,
        [
            ".//tei:teiHeader//tei:sourceDesc//tei:date",
            ".//tei:teiHeader//tei:publicationStmt//tei:date",
            ".//tei:teiHeader//tei:imprint//tei:date",
        ],
        ns,
    )
    if not year_text:
        return None

    match = re.search(r"(1[6-9]\d{2}|20\d{2})", year_text)
    return int(match.group(1)) if match else None


def parse_eltec_tei_xml(xml_bytes: bytes) -> ParsedDocument:
    """Parse TEI XML into metadata + section/full text.

    The parser tolerates variations in ELTeC/TEI structure and falls back gracefully.
    """
    root = ET.fromstring(xml_bytes)
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}

    title = _first_text(root, [".//tei:teiHeader//tei:titleStmt//tei:title", ".//tei:title"], ns) or "Untitled"
    author = _first_text(root, [".//tei:teiHeader//tei:titleStmt//tei:author", ".//tei:author"], ns) or "Unknown"
    publication_year = _extract_year(root, ns)

    body = root.find(".//tei:text/tei:body", ns)
    if body is None:
        body = root.find(".//body")

    if body is None:
        return ParsedDocument(
            title=title,
            author=author,
            publication_year=publication_year,
            full_text="",
            sections=[],
        )

    sections: list[ParsedSection] = []
    for idx, div in enumerate(body.findall(".//tei:div", ns), start=1):
        label = _first_text(div, ["./tei:head", "./tei:title"], ns) or f"Chapter {idx}"
        text = _clean_text(" ".join(t for t in div.itertext()))
        if text:
            sections.append(ParsedSection(label=label, text=text))

    if not sections:
        for idx, div in enumerate(body.findall(".//div"), start=1):
            label = _clean_text("".join(div.findtext("head", default=""))) or f"Chapter {idx}"
            text = _clean_text(" ".join(t for t in div.itertext()))
            if text:
                sections.append(ParsedSection(label=label, text=text))

    full_text = _clean_text(" ".join(t for t in body.itertext()))

    return ParsedDocument(
        title=title,
        author=author,
        publication_year=publication_year,
        full_text=full_text,
        sections=sections,
    )
