"""Compatibility helpers for Supabase SDK imports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client as Client
else:
    Client = Any

_create_client_error: Exception | None = None

try:
    from supabase import create_client as create_client
except Exception as exc:  # noqa: BLE001
    _create_client_error = exc

    def create_client(*args: Any, **kwargs: Any) -> Any:
        raise ImportError(
            "Supabase client factory is unavailable. Ensure the 'supabase' package is installed correctly."
        ) from _create_client_error
