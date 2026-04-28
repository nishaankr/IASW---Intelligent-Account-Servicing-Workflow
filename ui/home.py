"""Streamlit landing page for the IASW prototype.

Run from the project root with:
    streamlit run ui/Home.py

Kept intentionally minimal: hero, status row, two role cards.
The status row fetches all stats in parallel with a short-TTL cache so
repeat loads are instant.
"""

import os
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

import _components as ui

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="IASW", layout="wide", page_icon="🏦")
ui.inject_css()


# --- Hero (renders immediately, never blocked on network) ------------------

ui.hero(
    "Intelligent Account Servicing Workflow",
    "Agentic AI document verification with human-in-the-loop approval.",
)


# --- Stats fetch (parallel + cached for snappy reloads) --------------------

@st.cache_data(ttl=15, show_spinner=False)
def _fetch_stats(api_url: str) -> dict:
    """Fetch backend health and request counts in parallel."""

    def _get(path: str, params=None):
        try:
            r = requests.get(f"{api_url}{path}", params=params, timeout=3)
            return r if r.ok else None
        except requests.exceptions.RequestException:
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        health_f = ex.submit(_get, "/health")
        queue_f = ex.submit(_get, "/requests")
        approved_f = ex.submit(_get, "/requests", {"status": "APPROVED"})
        rejected_f = ex.submit(_get, "/requests", {"status": "REJECTED"})

        h = health_f.result()
        q = queue_f.result()
        a = approved_f.result()
        rj = rejected_f.result()

    return {
        "online": h is not None,
        "queue": len(q.json()) if q else None,
        "approved": len(a.json()) if a else None,
        "rejected": len(rj.json()) if rj else None,
    }


with st.spinner("Loading status…"):
    stats = _fetch_stats(API_BASE_URL)


# --- Status row ------------------------------------------------------------

ui.section_label("System status")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Backend", "Online" if stats["online"] else "Offline")
with c2:
    st.metric("Pending in queue",
              stats["queue"] if stats["queue"] is not None else "—")
with c3:
    st.metric("Approved",
              stats["approved"] if stats["approved"] is not None else "—")
with c4:
    st.metric("Rejected",
              stats["rejected"] if stats["rejected"] is not None else "—")

if not stats["online"]:
    st.warning(
        f"Backend not reachable at `{API_BASE_URL}`. Start it with "
        "`uvicorn app.api.main:app --reload --port 8000`.",
        icon="⚠️",
    )


# --- Role cards ------------------------------------------------------------

ui.section_label("Choose a role")

col_a, col_b = st.columns(2, gap="large")

with col_a:
    with st.container(border=True):
        st.markdown("### 🧾  Staff Intake")
        st.caption("Submit a customer change request and supporting document.")
        try:
            st.page_link("pages/1_Staff_Intake.py",
                         label="Open Staff Intake →", icon="🧾")
        except Exception:
            st.caption("Use the sidebar to navigate.")

with col_b:
    with st.container(border=True):
        st.markdown("### ✅  Checker Review")
        st.caption("Review AI-verified requests; approve or reject.")
        try:
            st.page_link("pages/2_Checker_Review.py",
                         label="Open Checker Review →", icon="✅")
        except Exception:
            st.caption("Use the sidebar to navigate.")


# --- Footer ----------------------------------------------------------------

st.markdown("")
st.caption(f"IASW v0.1  ·  API `{API_BASE_URL}`  ·  Design notes: `docs/`")
