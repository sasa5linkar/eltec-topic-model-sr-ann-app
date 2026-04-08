from src.assignment_merge import merge_assignment_rows


def test_merge_assignment_rows_enriches_segment_document_profile() -> None:
    assignments = [{"id": "a1", "segment_id": "s1", "annotator_id": "u1"}]
    segments = [{"id": "s1", "document_id": "d1", "segment_order": 1}]
    documents = [{"id": "d1", "title": "Roman"}]
    profiles = [{"id": "u1", "email": "ann@example.com"}]

    enriched = merge_assignment_rows(assignments, segments, documents, profiles)

    assert len(enriched) == 1
    row = enriched[0]
    assert row["segments"]["id"] == "s1"
    assert row["segments"]["documents"]["title"] == "Roman"
    assert row["profiles"]["email"] == "ann@example.com"
