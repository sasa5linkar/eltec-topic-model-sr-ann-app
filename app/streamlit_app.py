"""Main entry point for the ELTeC annotation Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.auth import get_current_user
from src.db import get_client
from src.errors import AppError
from src.models import ROLE_ADMIN, ROLE_ANNOTATOR

st.set_page_config(page_title="ELTeC Topic Annotation", layout="wide")


def main() -> None:
    st.title("ELTeC Topic Annotation MVP")
    st.caption("One Streamlit app for both admin and annotator workflows.")

    try:
        anon_client = get_client(use_service_role=False)
        service_client = get_client(use_service_role=True)
        user = get_current_user(anon_client, service_client)
    except AppError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"Greska pri inicijalizaciji aplikacije: {exc}")
        return

    st.sidebar.markdown("---")
    st.sidebar.write(f"**Aktivni korisnik:** {user.get('email', 'N/A')}")
    st.sidebar.write(f"**Rola:** {user.get('role', 'N/A')}")

    if user.get("role") == ROLE_ADMIN:
        st.success("Prijavljeni ste kao admin. Otvorite stranicu Admin iz levog menija.")
    elif user.get("role") == ROLE_ANNOTATOR:
        st.success("Prijavljeni ste kao annotator. Otvorite stranicu Annotator iz levog menija.")
    else:
        st.warning("Korisnik nema podrzanu rolu. Ocekivane role su admin ili annotator.")

    st.markdown(
        """
### Navigacija
- **Admin**: upload XML, segmentacija, teme, dodele, progres, export
- **Annotator**: licni zadaci, anotiranje tema, zavrsavanje dodela
"""
    )


main()
