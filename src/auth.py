"""Simple auth helper with dev-user mode and extensibility for real auth."""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st
from supabase import Client

from src.db import get_profiles


@st.cache_data(ttl=60)
def get_available_users(client: Client) -> list[dict[str, Any]]:
    return get_profiles(client)


def _resolve_query_param_user(users: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    params = st.query_params
    user_id = params.get("user_id")
    if not user_id:
        return None
    return next((u for u in users if u.get("id") == user_id), None)


def get_current_user(client: Client) -> dict[str, Any]:
    """Return current user selected in development mode.

    Architecture leaves room for replacing this with Supabase Auth session handling.
    """
    users = get_available_users(client)
    if not users:
        raise RuntimeError("No users found in profiles table. Add at least one admin/annotator profile.")

    query_user = _resolve_query_param_user(users)
    if query_user:
        st.session_state["selected_user_id"] = query_user["id"]

    default_id = st.session_state.get("selected_user_id") or users[0]["id"]
    options = {f"{u.get('email', 'unknown')} ({u.get('role', '-')})": u["id"] for u in users}

    selected_label = st.sidebar.selectbox("Development user", options=list(options.keys()))
    selected_id = options[selected_label]
    st.session_state["selected_user_id"] = selected_id

    return next(u for u in users if u["id"] == selected_id)
