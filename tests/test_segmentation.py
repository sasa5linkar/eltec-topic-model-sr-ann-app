from pathlib import Path

from src.eltec_parser import parse_eltec_tei_xml
from src.models import ParsedDocument, ParsedPage, ParsedParagraph, ParsedSection
from src.segmentation import segment_by_chapters, segment_by_pages, segment_by_paragraph_count, segment_by_word_count

EXAMPLES_DIR = Path(__file__).parent / "examples"


def test_segment_by_chapters() -> None:
    parsed = ParsedDocument(
        title="T",
        author="A",
        publication_year=None,
        full_text="",
        sections=[ParsedSection(label="C1", text="a b c"), ParsedSection(label="C2", text="d e")],
        pages=[],
        paragraphs=[],
    )
    segments = segment_by_chapters(parsed)
    assert len(segments) == 2
    assert segments[0]["segment_order"] == 1
    assert segments[0]["word_count"] == 3


def test_segment_by_word_count() -> None:
    text = " ".join([f"w{i}" for i in range(11)])
    segments = segment_by_word_count(text, chunk_size=5)
    assert len(segments) == 3
    assert segments[0]["word_count"] == 5
    assert segments[-1]["word_count"] == 1


def test_segment_by_pages() -> None:
    parsed = ParsedDocument(
        title="T",
        author="A",
        publication_year=None,
        full_text="",
        sections=[],
        pages=[ParsedPage(label="1", text="a b c"), ParsedPage(label="2", text="d e")],
        paragraphs=[],
    )
    segments = segment_by_pages(parsed)
    assert len(segments) == 2
    assert segments[0]["segment_label"] == "1"
    assert segments[1]["word_count"] == 2


def test_segment_by_paragraph_count() -> None:
    parsed = ParsedDocument(
        title="T",
        author="A",
        publication_year=None,
        full_text="",
        sections=[],
        pages=[],
        paragraphs=[
            ParsedParagraph(label="Paragraph 1", text="a b"),
            ParsedParagraph(label="Paragraph 2", text="c d e"),
            ParsedParagraph(label="Paragraph 3", text="f"),
        ],
    )
    segments = segment_by_paragraph_count(parsed, chunk_size=2)
    assert len(segments) == 2
    assert segments[0]["segment_label"] == "Paragraphs 1-2"
    assert segments[0]["word_count"] == 5
    assert segments[1]["segment_label"] == "Paragraph 3"


def test_segment_real_example_by_chapters_and_pages() -> None:
    xml_bytes = (EXAMPLES_DIR / "SRP1867a_KonstantinH_IzBosneOBosni.xml").read_bytes()
    parsed = parse_eltec_tei_xml(xml_bytes)

    chapter_segments = segment_by_chapters(parsed)
    page_segments = segment_by_pages(parsed)
    paragraph_segments = segment_by_paragraph_count(parsed, chunk_size=10)

    assert len(chapter_segments) == 13
    assert len(page_segments) == 35
    assert paragraph_segments
    assert page_segments[0]["segment_label"] == "20.474"
    assert page_segments[-1]["segment_label"] == "28.669"
