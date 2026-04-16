from pathlib import Path

from src.eltec_parser import parse_eltec_tei_xml

EXAMPLES_DIR = Path(__file__).parent / "examples"


def test_parse_tei_with_header_and_divs() -> None:
    xml = b"""
    <TEI xmlns=\"http://www.tei-c.org/ns/1.0\">
      <teiHeader>
        <fileDesc>
          <titleStmt>
            <title>Test Roman</title>
            <author>Test Autor</author>
          </titleStmt>
          <sourceDesc><bibl><date>1888</date></bibl></sourceDesc>
        </fileDesc>
      </teiHeader>
      <text><body>
        <div><head>Prvo</head><p>Jedan dva tri.</p></div>
        <div><head>Drugo</head><p>Cetiri pet sest.</p></div>
      </body></text>
    </TEI>
    """
    parsed = parse_eltec_tei_xml(xml)
    assert parsed.title == "Test Roman"
    assert parsed.author == "Test Autor"
    assert parsed.publication_year == 1888
    assert len(parsed.sections) == 2
    assert parsed.pages == []
    assert len(parsed.paragraphs) == 2


def test_parse_tei_without_header_fallbacks() -> None:
    xml = b"""
    <TEI xmlns=\"http://www.tei-c.org/ns/1.0\">
      <text><body><p>Samo tekst bez div elemenata.</p></body></text>
    </TEI>
    """
    parsed = parse_eltec_tei_xml(xml)
    assert parsed.title == "Untitled"
    assert parsed.author == "Unknown"
    assert parsed.sections == []
    assert parsed.pages == []
    assert len(parsed.paragraphs) == 1
    assert "Samo tekst" in parsed.full_text


def test_parse_tei_preserves_paragraph_breaks_in_section_text() -> None:
    xml = b"""
    <TEI xmlns=\"http://www.tei-c.org/ns/1.0\">
      <text><body>
        <div>
          <head>Prvo</head>
          <p>Jedan dva tri.</p>
          <p>Cetiri pet sest.</p>
        </div>
      </body></text>
    </TEI>
    """
    parsed = parse_eltec_tei_xml(xml)
    assert len(parsed.sections) == 1
    assert parsed.sections[0].text == "Jedan dva tri.\n\nCetiri pet sest."
    assert parsed.full_text == "Jedan dva tri.\n\nCetiri pet sest."


def test_parse_real_example_extracts_sections_and_pages() -> None:
    xml_bytes = (EXAMPLES_DIR / "SRP1867a_KonstantinH_IzBosneOBosni.xml").read_bytes()
    parsed = parse_eltec_tei_xml(xml_bytes)

    assert parsed.publication_year == 1867
    assert len(parsed.sections) == 13
    assert len(parsed.pages) == 35
    assert len(parsed.paragraphs) > 0
    assert parsed.pages[0].label == "20.474"
    assert parsed.pages[-1].label == "28.669"
    assert parsed.pages[0].text
    assert parsed.paragraphs[0].text
