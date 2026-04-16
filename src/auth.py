"""Auth helpers: real Supabase session mode plus development fallback mode."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st
from supabase import Client

from src.db import get_profiles
from src.errors import AuthenticationError, map_supabase_error
from src.logging_utils import get_logger, log_event
from src.models import ROLE_ADMIN, ROLE_ANNOTATOR, TABLES

AUTH_CALLBACK_KEYS = (
    "code",
    "token_hash",
    "type",
    "error",
    "error_code",
    "error_description",
    "access_token",
    "refresh_token",
    "expires_at",
    "expires_in",
    "token_type",
    "provider_token",
    "provider_refresh_token",
)
LOGGER = get_logger("eltec_app.auth")
EMAIL_ACTION_COOLDOWN_SECONDS = 60
SUPPORTED_PROFILE_ROLES = {ROLE_ADMIN, ROLE_ANNOTATOR}


@st.cache_data(ttl=60)
def get_available_users(client: Client) -> list[dict[str, Any]]:
    return get_profiles(client)


def _query_param(name: str) -> str | None:
    value = st.query_params.get(name)
    if value is None or value == "":
        return None
    return value


def _clear_auth_callback_params() -> None:
    for key in AUTH_CALLBACK_KEYS:
        try:
            del st.query_params[key]
        except Exception:
            continue


def _set_notice(message: str) -> None:
    st.session_state["auth_notice"] = message


def _pop_notice() -> str | None:
    return st.session_state.pop("auth_notice", None)


def _set_email_action_cooldown(seconds: int = EMAIL_ACTION_COOLDOWN_SECONDS) -> None:
    st.session_state["auth_email_cooldown_until"] = time.time() + seconds


def _get_email_action_cooldown_remaining() -> int:
    cooldown_until = st.session_state.get("auth_email_cooldown_until", 0.0)
    return max(0, int(cooldown_until - time.time()))


def _auth_error_message(exc: Exception, operation: str) -> str:
    raw_status = getattr(exc, "status_code", None)
    raw_message = str(exc)
    log_event(
        LOGGER,
        "error",
        "auth_error",
        operation=operation,
        status_code=raw_status,
        raw_message=raw_message,
    )

    friendly = map_supabase_error(exc, operation)
    if friendly.message == "Database request failed." and raw_message:
        return f"{operation}: {raw_message}"
    return str(friendly)


def _get_redirect_url() -> str:
    explicit_url = st.secrets.get("APP_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    current_url = getattr(st.context, "url", None)
    if current_url:
        parts = urlsplit(current_url)
        if parts.scheme and parts.netloc:
            return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")

    return "http://localhost:8501"


def _resolve_query_param_user(users: list[dict[str, Any]]) -> dict[str, Any] | None:
    user_id = _query_param("user_id")
    if not user_id:
        return None
    return next((user for user in users if user.get("id") == user_id), None)


def _try_find_profile_by_id(client: Client, user_id: str) -> tuple[dict[str, Any] | None, Exception | None]:
    try:
        rows = client.table(TABLES.profiles).select("*").eq("id", user_id).limit(1).execute().data or []
    except Exception as exc:  # noqa: BLE001
        return None, exc
    return (rows[0] if rows else None), None


def _find_profile_by_id(client: Client, user_id: str) -> dict[str, Any] | None:
    profile, error = _try_find_profile_by_id(client, user_id)
    if error:
        raise error
    return profile


def _normalize_role(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    return cleaned if cleaned in SUPPORTED_PROFILE_ROLES else None


def _build_profile_payload_from_auth_user(user: Any) -> dict[str, Any] | None:
    user_id = getattr(user, "id", None)
    raw_email = getattr(user, "email", None)
    if not user_id or not raw_email:
        return None

    user_metadata = getattr(user, "user_metadata", {}) or {}
    app_metadata = getattr(user, "app_metadata", {}) or {}
    role = _normalize_role(user_metadata.get("role") or app_metadata.get("role"))
    if not role:
        return None

    raw_full_name = (
        user_metadata.get("full_name")
        or user_metadata.get("name")
        or app_metadata.get("full_name")
        or app_metadata.get("name")
    )
    cleaned_full_name = raw_full_name.strip() if isinstance(raw_full_name, str) and raw_full_name.strip() else None

    return {
        "id": user_id,
        "email": str(raw_email).strip().lower(),
        "full_name": cleaned_full_name,
        "role": role,
    }


def _create_profile_from_auth_user(client_service: Client, user: Any) -> dict[str, Any] | None:
    payload = _build_profile_payload_from_auth_user(user)
    if not payload:
        return None

    try:
        rows = client_service.table(TABLES.profiles).insert(payload).execute().data or []
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError(str(map_supabase_error(exc, "profiles.insert_missing_profile"))) from exc

    profile = rows[0] if rows else payload
    log_event(
        LOGGER,
        "info",
        "profile_created_from_auth_metadata",
        user_id=payload["id"],
        email=payload["email"],
        role=payload["role"],
    )
    return profile


def _resolve_profile_for_authenticated_user(
    client_anon: Client,
    client_service: Client | None,
    user: Any,
) -> dict[str, Any]:
    profile, anon_error = _try_find_profile_by_id(client_anon, user.id)
    if profile:
        return profile

    if anon_error:
        mapped = map_supabase_error(anon_error, "profiles.select_current_user")
        if mapped.status_code == 403 or "rls/policy" in mapped.message.lower():
            log_event(
                LOGGER,
                "warning",
                "profile_lookup_requires_service_role",
                user_id=user.id,
                email=getattr(user, "email", None),
            )
        else:
            raise AuthenticationError(str(mapped)) from anon_error

    if client_service is not None:
        service_profile, service_error = _try_find_profile_by_id(client_service, user.id)
        if service_error:
            raise AuthenticationError(str(map_supabase_error(service_error, "profiles.select_current_user_service"))) from service_error
        if service_profile:
            return service_profile

        created_profile = _create_profile_from_auth_user(client_service, user)
        if created_profile:
            return created_profile

    email = str(getattr(user, "email", "") or "").strip().lower() or "unknown"
    raise AuthenticationError(
        "Korisnik postoji u auth-u, ali nema profil u tabeli profiles. "
        f"Dodajte red sa id='{user.id}', email='{email}' i rolom 'admin' ili 'annotator'."
    )


def _sync_client_session(client_anon: Client) -> Any:
    session = st.session_state.get("supabase_session")
    if not session:
        return None

    client_anon.auth.set_session(session.access_token, session.refresh_token)
    return session


def _render_hash_callback_bridge() -> None:
    st.html(
        """
        <script>
        (function () {
          const hash = window.location.hash || "";
          if (!hash || hash.length <= 1) return;

          const hashParams = new URLSearchParams(hash.slice(1));
          if (!hashParams.has("access_token") && !hashParams.has("refresh_token") && !hashParams.has("type")) {
            return;
          }

          const url = new URL(window.location.href);
          for (const [key, value] of hashParams.entries()) {
            url.searchParams.set(key, value);
          }
          url.hash = "";
          window.location.replace(url.toString());
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _complete_auth_session(*, session: Any, otp_type: str | None) -> None:
    st.session_state["supabase_session"] = session
    st.session_state["auth_recovery_mode"] = otp_type == "recovery"
    if otp_type == "recovery":
        _set_notice("Recovery link confirmed. Set a new password in the sidebar.")
    else:
        _set_notice("Email link confirmed. Signed in successfully.")
    _clear_auth_callback_params()
    st.rerun()


def _handle_auth_callback(client_anon: Client) -> None:
    error_description = _query_param("error_description")
    if error_description:
        log_event(
            LOGGER,
            "error",
            "auth_callback_error",
            error_description=error_description,
            error_code=_query_param("error_code"),
        )
        _clear_auth_callback_params()
        raise AuthenticationError(f"Auth callback error: {error_description}")

    auth_code = _query_param("code")
    if auth_code:
        try:
            response = client_anon.auth.exchange_code_for_session({"auth_code": auth_code})
            _complete_auth_session(session=response.session, otp_type=None)
        except Exception as exc:
            _clear_auth_callback_params()
            raise AuthenticationError(_auth_error_message(exc, "auth.exchange_code_for_session")) from exc

    token_hash = _query_param("token_hash")
    otp_type = _query_param("type")
    if token_hash and otp_type:
        try:
            response = client_anon.auth.verify_otp({"token_hash": token_hash, "type": otp_type})
            _complete_auth_session(session=response.session, otp_type=otp_type)
        except Exception as exc:
            _clear_auth_callback_params()
            raise AuthenticationError(_auth_error_message(exc, "auth.verify_otp")) from exc

    access_token = _query_param("access_token")
    refresh_token = _query_param("refresh_token")
    if access_token and refresh_token:
        try:
            client_anon.auth.set_session(access_token, refresh_token)
            _complete_auth_session(session=client_anon.auth.get_session(), otp_type=otp_type)
        except Exception as exc:
            _clear_auth_callback_params()
            raise AuthenticationError(_auth_error_message(exc, "auth.set_session")) from exc


def _render_recovery_form(client_anon: Client) -> None:
    st.caption("Recovery mode: set a new password.")
    new_password = st.text_input("New password", type="password", key="auth_new_password")
    confirm_password = st.text_input("Confirm password", type="password", key="auth_confirm_password")

    if not st.button("Update password", key="auth_update_password"):
        return
    if not new_password:
        st.error("Enter a new password.")
        return
    if new_password != confirm_password:
        st.error("Passwords do not match.")
        return

    try:
        _sync_client_session(client_anon)
        client_anon.auth.update_user({"password": new_password})
        st.session_state["auth_recovery_mode"] = False
        _set_notice("Password updated successfully.")
        st.rerun()
    except Exception as exc:
        st.error(_auth_error_message(exc, "auth.update_user"))


def _render_email_actions(client_anon: Client) -> None:
    cooldown_remaining = _get_email_action_cooldown_remaining()
    email_actions_disabled = cooldown_remaining > 0
    if email_actions_disabled:
        st.caption(f"Email actions available again in {cooldown_remaining}s.")

    magic_email = st.text_input("Email for magic link", key="auth_magic_email")
    if st.button("Send magic link", key="auth_send_magic_link", disabled=email_actions_disabled):
        try:
            client_anon.auth.sign_in_with_otp(
                {
                    "email": magic_email,
                    "options": {
                        "email_redirect_to": _get_redirect_url(),
                        "should_create_user": False,
                    },
                }
            )
            _set_email_action_cooldown()
            st.success("Magic link sent.")
        except Exception as exc:
            st.error(_auth_error_message(exc, "auth.sign_in_with_otp"))

    reset_email = st.text_input("Email for password reset", key="auth_reset_email")
    if st.button("Send reset link", key="auth_send_reset", disabled=email_actions_disabled):
        try:
            client_anon.auth.reset_password_for_email(reset_email, {"redirect_to": _get_redirect_url()})
            _set_email_action_cooldown()
            st.success("Password reset link sent.")
        except Exception as exc:
            st.error(_auth_error_message(exc, "auth.reset_password_for_email"))


def _render_login_form(client_anon: Client) -> None:
    with st.sidebar.expander("Supabase login", expanded=True):
        notice = _pop_notice()
        if notice:
            st.success(notice)

        if st.session_state.get("auth_recovery_mode"):
            _render_recovery_form(client_anon)
            return

        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_password")
        if st.button("Sign in", key="auth_sign_in"):
            try:
                result = client_anon.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["supabase_session"] = result.session
                st.success("Uspesna prijava.")
                st.rerun()
            except Exception as exc:
                st.error(_auth_error_message(exc, "auth.sign_in_with_password"))

        _render_email_actions(client_anon)
        st.caption(f"Auth redirect URL: {_get_redirect_url()}")


def _get_current_user_real_auth(client_anon: Client, client_service: Client | None = None) -> dict[str, Any]:
    """Resolve user from a real Supabase auth session in anon/RLS mode."""
    _render_hash_callback_bridge()
    _handle_auth_callback(client_anon)
    _render_login_form(client_anon)

    session = _sync_client_session(client_anon)
    if not session:
        raise AuthenticationError("Nema aktivne sesije. Prijavite se u sidebar-u.")

    try:
        user = client_anon.auth.get_user().user
    except Exception as exc:
        raise AuthenticationError(str(map_supabase_error(exc, "auth.get_user"))) from exc

    if not user or not user.id:
        raise AuthenticationError("Nije moguce ucitati autentifikovanog korisnika.")

    profile = _resolve_profile_for_authenticated_user(client_anon, client_service, user)

    if st.sidebar.button("Sign out"):
        client_anon.auth.sign_out()
        st.session_state.pop("supabase_session", None)
        st.session_state.pop("auth_recovery_mode", None)
        st.rerun()

    return profile


def _get_current_user_dev_mode(client_service: Client) -> dict[str, Any]:
    users = get_available_users(client_service)
    if not users:
        raise AuthenticationError("No users found in profiles table. Add at least one admin or annotator profile.")

    query_user = _resolve_query_param_user(users)
    if query_user:
        st.session_state["selected_user_id"] = query_user["id"]

    default_id = st.session_state.get("selected_user_id") or users[0]["id"]
    options = {f"{user.get('email', 'unknown')} ({user.get('role', '-')})": user["id"] for user in users}
    labels = list(options.keys())

    default_index = next((idx for idx, label in enumerate(labels) if options[label] == default_id), 0)
    selected_label = st.sidebar.selectbox("Development user", options=labels, index=default_index)
    selected_id = options[selected_label]
    st.session_state["selected_user_id"] = selected_id

    return next(user for user in users if user["id"] == selected_id)


def get_current_user(client_anon: Client, client_service: Client | None = None) -> dict[str, Any]:
    """Return the active user profile for either auth mode."""
    mode = st.sidebar.radio("Auth mode", ["Real auth", "Development"], index=0)
    if mode == "Real auth":
        return _get_current_user_real_auth(client_anon, client_service)

    if client_service is None:
        raise AuthenticationError("Development mode zahteva service-role klijent.")
    return _get_current_user_dev_mode(client_service)
