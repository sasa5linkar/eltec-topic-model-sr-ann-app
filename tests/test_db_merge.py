from types import SimpleNamespace

from src.assignment_merge import build_document_overview_rows, merge_assignment_rows
from src.db import create_annotator_account, delete_document


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
    created_user_attributes: list[dict] = []

    class FakeExecute:
        def __init__(self, data):
            self.data = data

    class FakeTable:
        def insert(self, payload):
            inserted_payloads.append(payload)
            return SimpleNamespace(execute=lambda: FakeExecute([payload]))

    class FakeAdmin:
        def create_user(self, attributes):
            created_user_attributes.append(attributes)
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
    assert created_user_attributes[0]["user_metadata"]["role"] == "annotator"
    assert created_user_attributes[0]["user_metadata"]["full_name"] == "Ann Example"


def test_build_document_overview_rows_counts_assignment_coverage() -> None:
    documents = [
        {"id": "d1", "title": "Roman 1", "author": "A1"},
        {"id": "d2", "title": "Roman 2", "author": "A2"},
    ]
    segments = [
        {"id": "s1", "document_id": "d1"},
        {"id": "s2", "document_id": "d1"},
        {"id": "s3", "document_id": "d2"},
    ]
    assignments = [
        {"segment_id": "s1", "status": "assigned"},
        {"segment_id": "s1", "status": "completed"},
        {"segment_id": "s3", "status": "assigned"},
    ]

    rows = build_document_overview_rows(documents, segments, assignments)

    assert rows[0]["document_id"] == "d1"
    assert rows[0]["total_segments"] == 2
    assert rows[0]["assigned_segments"] == 1
    assert rows[0]["unassigned_segments"] == 1
    assert rows[0]["assignment_rows"] == 2
    assert rows[0]["completed_assignments"] == 1
    assert rows[1]["document_id"] == "d2"
    assert rows[1]["total_segments"] == 1
    assert rows[1]["assigned_segments"] == 1
    assert rows[1]["unassigned_segments"] == 0


def test_delete_document_removes_related_segments_assignments_and_annotations() -> None:
    class FakeExecute:
        def __init__(self, data):
            self.data = data

    class FakeQuery:
        def __init__(self, tables: dict[str, list[dict]], table_name: str):
            self.tables = tables
            self.table_name = table_name
            self.action = "select"
            self.predicates: list = []

        def select(self, _expr):
            self.action = "select"
            return self

        def delete(self):
            self.action = "delete"
            return self

        def eq(self, key, value):
            self.predicates.append(lambda row, k=key, v=value: row.get(k) == v)
            return self

        def in_(self, key, values):
            allowed = set(values)
            self.predicates.append(lambda row, k=key, v=allowed: row.get(k) in v)
            return self

        def execute(self):
            rows = self.tables[self.table_name]
            matched = [dict(row) for row in rows if all(predicate(row) for predicate in self.predicates)]
            if self.action == "delete":
                self.tables[self.table_name] = [row for row in rows if not all(predicate(row) for predicate in self.predicates)]
            return FakeExecute(matched)

    tables = {
        "documents": [{"id": "d1"}, {"id": "d2"}],
        "segments": [{"id": "s1", "document_id": "d1"}, {"id": "s2", "document_id": "d1"}, {"id": "s3", "document_id": "d2"}],
        "assignments": [{"id": "a1", "segment_id": "s1"}, {"id": "a2", "segment_id": "s3"}],
        "annotations": [{"id": "n1", "segment_id": "s1"}, {"id": "n2", "segment_id": "s2"}, {"id": "n3", "segment_id": "s3"}],
    }
    fake_client = SimpleNamespace(table=lambda name: FakeQuery(tables, name))

    result = delete_document(fake_client, "d1")

    assert result["documents_deleted"] == 1
    assert result["segments_deleted"] == 2
    assert result["assignments_deleted"] == 1
    assert result["annotations_deleted"] == 2
    assert tables["documents"] == [{"id": "d2"}]
    assert tables["segments"] == [{"id": "s3", "document_id": "d2"}]
    assert tables["assignments"] == [{"id": "a2", "segment_id": "s3"}]
    assert tables["annotations"] == [{"id": "n3", "segment_id": "s3"}]
