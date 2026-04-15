from src.models import ParsedDocument, ParsedSection
from src.segmentation import segment_by_chapters, segment_by_word_count


def test_segment_by_chapters() -> None:
    parsed = ParsedDocument(
        title="T",
        author="A",
        publication_year=None,
        full_text="",
        sections=[ParsedSection(label="C1", text="a b c"), ParsedSection(label="C2", text="d e")],
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
