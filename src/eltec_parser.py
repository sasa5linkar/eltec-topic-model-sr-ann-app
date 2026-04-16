"""Parser utilities for ELTeC / TEI XML files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from src.models import ParsedDocument, ParsedPage, ParsedParagraph, ParsedSection


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


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _extract_paragraph_texts(root: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "p":
            continue

        text = _clean_text(" ".join(fragment for fragment in elem.itertext()))
        if text:
            paragraphs.append(text)
    return paragraphs


def _extract_text_with_paragraph_breaks(root: ET.Element) -> str:
    paragraphs = _extract_paragraph_texts(root)
    if paragraphs:
        return "\n\n".join(paragraphs)
    return _clean_text(" ".join(fragment for fragment in root.itertext()))


def _extract_labeled_sections(
    divs: list[ET.Element],
    *,
    label_paths: list[str],
    default_prefix: str,
    ns: dict[str, str],
) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    for idx, div in enumerate(divs, start=1):
        label = _first_text(div, label_paths, ns) or f"{default_prefix} {idx}"
        text = _extract_text_with_paragraph_breaks(div)
        if text:
            sections.append(ParsedSection(label=label, text=text))
    return sections


def _extract_pages(body: ET.Element) -> list[ParsedPage]:
    pages: list[ParsedPage] = []
    current_label: Optional[str] = None
    current_blocks: list[str] = []
    current_parts: list[str] = []

    def flush_current_parts() -> None:
        nonlocal current_blocks, current_parts
        text = _clean_text(" ".join(current_parts))
        if text:
            current_blocks.append(text)
        current_parts = []

    def flush_current_page() -> None:
        nonlocal current_label, current_blocks, current_parts
        flush_current_parts()
        if not current_label:
            return

        text = "\n\n".join(current_blocks)
        if text:
            pages.append(ParsedPage(label=current_label, text=text))
        current_label = None
        current_blocks = []
        current_parts = []

    def walk(elem: ET.Element) -> None:
        nonlocal current_label

        if _local_name(elem.tag) == "pb":
            if current_label is not None:
                flush_current_page()
            current_label = elem.attrib.get("n") or f"Page {len(pages) + 1}"
            return

        if elem.text:
            current_parts.append(elem.text)

        for child in elem:
            walk(child)
            if child.tail:
                current_parts.append(child.tail)

        if _local_name(elem.tag) == "p":
            flush_current_parts()

    walk(body)
    flush_current_page()
    return pages


def _extract_paragraphs(body: ET.Element) -> list[ParsedParagraph]:
    paragraphs: list[ParsedParagraph] = []
    for text in _extract_paragraph_texts(body):
        paragraphs.append(ParsedParagraph(label=f"Paragraph {len(paragraphs) + 1}", text=text))
    return paragraphs


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
            pages=[],
            paragraphs=[],
        )

    tei_divs = body.findall("./tei:div", ns) or body.findall(".//tei:div", ns)
    sections = _extract_labeled_sections(
        tei_divs,
        label_paths=["./tei:head", "./tei:title"],
        default_prefix="Chapter",
        ns=ns,
    )

    if not sections:
        plain_divs = body.findall("./div") or body.findall(".//div")
        sections = _extract_labeled_sections(
            plain_divs,
            label_paths=["./head", "./title"],
            default_prefix="Chapter",
            ns={},
        )

    full_text = _extract_text_with_paragraph_breaks(body)
    pages = _extract_pages(body)
    paragraphs = _extract_paragraphs(body)

    return ParsedDocument(
        title=title,
        author=author,
        publication_year=publication_year,
        full_text=full_text,
        sections=sections,
        pages=pages,
        paragraphs=paragraphs,
    )
