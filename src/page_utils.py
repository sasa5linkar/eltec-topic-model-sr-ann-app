"""Shared Streamlit page bootstrap helpers."""

from __future__ import annotations

from typing import Any

import streamlit as st
from supabase import Client

from src.auth import get_current_user
from src.db import get_client
from src.errors import AppError


def load_authenticated_page(
    *,
    page_title: str,
    heading: str,
    allowed_role: str | None = None,
) -> tuple[Client, Client, dict[str, Any]]:
    """Configure a page, resolve the current user, and optionally enforce a role."""
    st.set_page_config(page_title=page_title, layout="wide")
    st.title(heading)

    try:
        anon_client = get_client(use_service_role=False)
        service_client = get_client(use_service_role=True)
        user = get_current_user(anon_client, service_client)
    except AppError as exc:
        st.error(str(exc))
        st.stop()
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        st.error(f"Greska pri povezivanju: {exc}")
        st.stop()
        raise SystemExit(1) from exc

    if allowed_role and user.get("role") != allowed_role:
        st.warning(f"Ova stranica je dostupna samo korisnicima sa rolom: {allowed_role}.")
        st.stop()
        raise SystemExit(1)

    return anon_client, service_client, user
