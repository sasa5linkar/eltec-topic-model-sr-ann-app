from types import SimpleNamespace

from src.assignment_merge import merge_assignment_rows
from src.db import create_annotator_account


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


def test_create_annotator_account_creates_auth_user_and_profile() -> None:
    inserted_payloads: list[dict] = []

    class FakeExecute:
        def __init__(self, data):
            self.data = data

    class FakeTable:
        def insert(self, payload):
            inserted_payloads.append(payload)
            return SimpleNamespace(execute=lambda: FakeExecute([payload]))

    class FakeAdmin:
        def create_user(self, attributes):
            return SimpleNamespace(user=SimpleNamespace(id="u1", email=attributes["email"]))

        def delete_user(self, _user_id):
            return None

    fake_client = SimpleNamespace(
        auth=SimpleNamespace(admin=FakeAdmin()),
        table=lambda _name: FakeTable(),
    )

    profile = create_annotator_account(
        fake_client,
        email=" Ann@example.com ",
        password="secret123",
        full_name="Ann Example",
    )

    assert profile["id"] == "u1"
    assert profile["email"] == "ann@example.com"
    assert profile["role"] == "annotator"
    assert inserted_payloads[0]["full_name"] == "Ann Example"
