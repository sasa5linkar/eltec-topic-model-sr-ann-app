from src.eltec_parser import parse_eltec_tei_xml


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
    assert "Samo tekst" in parsed.full_text
