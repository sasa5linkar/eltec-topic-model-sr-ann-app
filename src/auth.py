"""Auth helpers: real Supabase session mode + development fallback mode."""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st
from supabase import Client

from src.db import get_profiles
from src.errors import AuthenticationError, map_supabase_error


@st.cache_data(ttl=60)
def get_available_users(client: Client) -> list[dict[str, Any]]:
    return get_profiles(client)


def _resolve_query_param_user(users: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    params = st.query_params
    user_id = params.get("user_id")
    if not user_id:
        return None
    return next((u for u in users if u.get("id") == user_id), None)


def _find_profile_by_id(client: Client, user_id: str) -> Optional[dict[str, Any]]:
    data = client.table("profiles").select("*").eq("id", user_id).limit(1).execute().data or []
    return data[0] if data else None


def _render_login_form(client_anon: Client) -> None:
    with st.sidebar.expander("Supabase login", expanded=True):
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_password")
        if st.button("Sign in"):
            try:
                result = client_anon.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["supabase_session"] = result.session
                st.success("Uspešna prijava.")
                st.rerun()
            except Exception as exc:
                err = map_supabase_error(exc, "auth.sign_in_with_password")
                st.error(str(err))


def _get_current_user_real_auth(client_anon: Client) -> dict[str, Any]:
    """Resolve user from real Supabase auth session in anon/RLS mode."""
    _render_login_form(client_anon)

    session = st.session_state.get("supabase_session")
    if not session:
        raise AuthenticationError("Nema aktivne sesije. Prijavite se u sidebar-u.")

    try:
        # Keep auth state synced with the stored access token.
        client_anon.auth.set_session(session.access_token, session.refresh_token)
        user = client_anon.auth.get_user().user
    except Exception as exc:
        raise AuthenticationError(str(map_supabase_error(exc, "auth.get_user"))) from exc

    if not user or not user.id:
        raise AuthenticationError("Nije moguće učitati autentifikovanog korisnika.")

    profile = _find_profile_by_id(client_anon, user.id)
    if not profile:
        raise AuthenticationError("Korisnik postoji u auth-u, ali nema profil u tabeli profiles.")

    if st.sidebar.button("Sign out"):
        client_anon.auth.sign_out()
        st.session_state.pop("supabase_session", None)
        st.rerun()

    return profile


def _get_current_user_dev_mode(client_service: Client) -> dict[str, Any]:
    users = get_available_users(client_service)
    if not users:
        raise AuthenticationError("No users found in profiles table. Add at least one admin/annotator profile.")

    query_user = _resolve_query_param_user(users)
    if query_user:
        st.session_state["selected_user_id"] = query_user["id"]

    default_id = st.session_state.get("selected_user_id") or users[0]["id"]
    options = {f"{u.get('email', 'unknown')} ({u.get('role', '-')})": u["id"] for u in users}
    labels = list(options.keys())

    default_index = next((idx for idx, label in enumerate(labels) if options[label] == default_id), 0)
    selected_label = st.sidebar.selectbox("Development user", options=labels, index=default_index)
    selected_id = options[selected_label]
    st.session_state["selected_user_id"] = selected_id

    return next(u for u in users if u["id"] == selected_id)


def get_current_user(client_anon: Client, client_service: Optional[Client] = None) -> dict[str, Any]:
    """Return active user profile.

    Modes:
    - Real auth mode: uses Supabase Auth session + anon key (RLS-friendly).
    - Development mode: manual user selector over profiles (requires service client).
    """
    mode = st.sidebar.radio("Auth mode", ["Real auth", "Development"], index=0)
    if mode == "Real auth":
        return _get_current_user_real_auth(client_anon)

    if client_service is None:
        raise AuthenticationError("Development mode zahteva service-role klijent.")
    return _get_current_user_dev_mode(client_service)
