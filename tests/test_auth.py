from types import SimpleNamespace

import pytest

from src.auth import _resolve_profile_for_authenticated_user
from src.errors import AuthenticationError


class FakeExecute:
    def __init__(self, data):
        self.data = data


class FakeProfilesQuery:
    def __init__(self, client):
        self.client = client
        self.filters: dict[str, str] = {}
        self._insert_payload: dict | None = None

    def select(self, _expr):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _value):
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def execute(self):
        if self._insert_payload is not None:
            self.client.inserted.append(dict(self._insert_payload))
            self.client.profiles_by_id[self._insert_payload["id"]] = dict(self._insert_payload)
            return FakeExecute([dict(self._insert_payload)])

        user_id = self.filters.get("id")
        row = self.client.profiles_by_id.get(user_id)
        return FakeExecute([dict(row)] if row else [])


class FakeClient:
    def __init__(self, profiles=None):
        self.profiles_by_id = {row["id"]: dict(row) for row in (profiles or [])}
        self.inserted: list[dict] = []

    def table(self, table_name):
        assert table_name == "profiles"
        return FakeProfilesQuery(self)


def test_resolve_profile_falls_back_to_service_role_when_anon_sees_no_rows() -> None:
    anon_client = FakeClient()
    service_client = FakeClient(
        profiles=[
            {
                "id": "509ec082-12df-4a05-8e77-8941d60a6f47",
                "email": "sasa5linkar@gmail.com",
                "full_name": "Sasa Petalinkar",
                "role": "admin",
            }
        ]
    )
    user = SimpleNamespace(
        id="509ec082-12df-4a05-8e77-8941d60a6f47",
        email="sasa5linkar@gmail.com",
        user_metadata={},
        app_metadata={},
    )

    profile = _resolve_profile_for_authenticated_user(anon_client, service_client, user)

    assert profile["role"] == "admin"
    assert service_client.inserted == []


def test_resolve_profile_creates_missing_profile_from_auth_metadata() -> None:
    anon_client = FakeClient()
    service_client = FakeClient()
    user = SimpleNamespace(
        id="u1",
        email=" Ann@example.com ",
        user_metadata={"full_name": "Ann Example", "role": "annotator"},
        app_metadata={},
    )

    profile = _resolve_profile_for_authenticated_user(anon_client, service_client, user)

    assert profile["id"] == "u1"
    assert profile["email"] == "ann@example.com"
    assert profile["full_name"] == "Ann Example"
    assert profile["role"] == "annotator"
    assert service_client.inserted[0]["role"] == "annotator"


def test_resolve_profile_raises_when_missing_profile_has_no_role_metadata() -> None:
    anon_client = FakeClient()
    service_client = FakeClient()
    user = SimpleNamespace(
        id="u1",
        email="ann@example.com",
        user_metadata={"email_verified": True},
        app_metadata={},
    )

    with pytest.raises(AuthenticationError, match="Dodajte red"):
        _resolve_profile_for_authenticated_user(anon_client, service_client, user)
