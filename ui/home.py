"""Streamlit landing page for the IASW prototype.

Run from the project root with:
    streamlit run ui/Home.py
"""

import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="IASW", layout="wide", page_icon=":bank:")

st.title("Intelligent Account Servicing Workflow")
st.caption("Agentic AI prototype with Human-in-the-Loop checker approval")

st.markdown(
    """
This prototype demonstrates an AI-augmented workflow for processing customer
account change requests. The AI replaces the **Maker** role (intake, document
verification, data validation) but a human **Checker** remains the only
authority that can commit a change to the (mocked) core banking system.

Use the sidebar to switch roles:

- **Staff Intake** — submit a change request and supporting document.
- **Checker Review** — review AI-verified requests and approve or reject.

The HITL boundary lives in the backend: only the `/requests/{id}/decision`
endpoint can call the mock RPS write, and only this UI can fire that endpoint
with `decision=APPROVE`.
    """
)

# A tiny health probe so you see immediately if FastAPI isn't running.
st.markdown("---")
st.subheader("Backend status")
try:
    r = requests.get(f"{API_BASE_URL}/health", timeout=2)
    if r.ok:
        st.success(f"API connected at {API_BASE_URL}")
    else:
        st.warning(f"API responded with HTTP {r.status_code} at {API_BASE_URL}")
except requests.exceptions.RequestException as e:
    st.error(f"API unreachable at {API_BASE_URL}")
    st.caption(
        "Start the backend in another terminal: "
        "`uvicorn app.api.main:app --reload --port 8000`"
    )
    st.code(str(e), language="text")