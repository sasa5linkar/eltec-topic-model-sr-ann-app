"""Custom typed exceptions and Supabase error mapping utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class AppError(Exception):
    """Base exception for user-facing application errors."""


@dataclass
class DatabaseError(AppError):
    operation: str
    message: str
    status_code: Optional[int] = None

    def __str__(self) -> str:
        suffix = f" (status={self.status_code})" if self.status_code is not None else ""
        return f"{self.operation}: {self.message}{suffix}"


class AuthenticationError(AppError):
    """Raised when authentication/session validation fails."""


def map_supabase_error(exc: Exception, operation: str) -> DatabaseError:
    """Convert raw Supabase exception into a stable, user-facing app error."""
    raw_status = getattr(exc, "status_code", None)
    lowered_message = str(exc).lower()

    friendly = "Database request failed."
    if "row-level security" in lowered_message or "permission" in lowered_message or raw_status == 403:
        friendly = "Nemate dozvolu za ovu operaciju (RLS/policy)."
    elif raw_status == 401:
        friendly = "Niste prijavljeni ili je sesija istekla."
    elif raw_status == 404:
        friendly = "Trazeni resurs ne postoji."
    elif raw_status in (408, 504) or "timeout" in lowered_message:
        friendly = "Istek vremena pri komunikaciji sa bazom."
    elif raw_status in (500, 502, 503):
        friendly = "Supabase servis je trenutno nedostupan."
    elif "duplicate" in lowered_message or "unique" in lowered_message:
        friendly = "Podatak vec postoji (duplikat)."

    return DatabaseError(operation=operation, message=friendly, status_code=raw_status)
