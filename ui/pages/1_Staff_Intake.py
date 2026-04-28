"""Staff Intake - page 1 of the IASW Streamlit UI.

"""

import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="Staff Intake — IASW", layout="wide")

st.title("Staff Intake")
st.caption(
    "Submit a customer change request. The AI pipeline runs synchronously "
    "and may take 10-30 seconds depending on document size."
)


# --- Form ------------------------------------------------------------------

with st.form("intake_form", clear_on_submit=False):
    col_a, col_b = st.columns(2)
    with col_a:
        customer_id = st.text_input(
            "Customer ID",
            value="C001",
            help="Bank-issued customer identifier (e.g., C001).",
        )
        change_type = st.selectbox(
            "Change Type",
            options=["LEGAL_NAME"],
            help=(
                "Only LEGAL_NAME is implemented in this prototype. "
                "Other types (ADDRESS, DATE_OF_BIRTH, CONTACT_EMAIL) follow "
                "the same shape and would be added in production."
            ),
        )
    with col_b:
        old_name = st.text_input("Current Legal Name", value="Priya Sharma")
        new_name = st.text_input("New Legal Name", value="Priya Mehta")

    document = st.file_uploader(
        "Supporting Document",
        type=["pdf", "png", "jpg", "jpeg"],
        help=(
            "Marriage Certificate (or Gazette Notification / Deed Poll) "
            "supporting the requested name change."
        ),
    )

    submitted = st.form_submit_button("Submit Request", type="primary")


# Submission handling

if submitted:
    if not document:
        st.error("Please upload a supporting document before submitting.")
        st.stop()

    with st.spinner(
        "Running AI pipeline — extracting fields, scoring confidence, "
        "generating summary..."
    ):
        try:
            files = {"document": (document.name, document.getvalue(), document.type)}
            data = {
                "customer_id": customer_id,
                "change_type": change_type,
                "old_name": old_name,
                "new_name": new_name,
            }
            r = requests.post(
                f"{API_BASE_URL}/requests",
                data=data,
                files=files,
                timeout=180,
            )
        except requests.exceptions.RequestException as e:
            st.error(f"Request failed: {e}")
            st.stop()

    if not r.ok:
        st.error(f"API returned HTTP {r.status_code}")
        st.code(r.text, language="json")
        st.stop()

    body = r.json()

    st.success(f"Request submitted — `{body['request_id']}`")
    st.markdown("---")

    rec = body.get("recommended_action") or "—"
    conf = body.get("overall_confidence")
    summary = body.get("ai_summary") or "(no summary returned)"

    col_rec, col_conf, col_status = st.columns(3)
    with col_rec:
        st.metric("Recommended Action", rec)
    with col_conf:
        st.metric(
            "Overall Confidence",
            f"{conf:.1%}" if conf is not None else "—",
        )
    with col_status:
        st.metric("Status", body.get("status", "—"))

    st.subheader("AI Summary")
    st.info(summary)

    st.markdown("---")
    st.markdown(
        f"Switch to **Checker Review** in the sidebar to act on this request. "
        f"Request ID: `{body['request_id']}`"
    )