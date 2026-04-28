"""Staff Intake — page 1 of the IASW Streamlit UI.

Banking-style intake form with placeholders, client-side validation, and
an explicit verification acknowledgement. Submits to POST /requests.
"""

import os
import re

import requests
import streamlit as st

import _components as ui

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="Staff Intake — IASW", layout="wide", page_icon="🧾")
ui.inject_css()


# --- Hero ------------------------------------------------------------------

ui.hero(
    "Staff Intake",
    "Submit a customer change request. The AI pipeline runs synchronously "
    "and returns a recommendation in a few seconds.",
)


# --- Validation helpers ----------------------------------------------------

CUSTOMER_ID_RE = re.compile(r"^[A-Za-z0-9\-]{3,32}$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,254}$")
STAFF_ID_RE = re.compile(r"^[A-Za-z0-9\-_.]{2,64}$")


def _validate(customer_id, change_type, old_name, new_name,
              staff_id, ack, document):
    """Return list of human-readable error strings; empty list = OK."""
    errors = []

    if not customer_id or not customer_id.strip():
        errors.append("Customer ID is required.")
    elif not CUSTOMER_ID_RE.fullmatch(customer_id.strip()):
        errors.append("Customer ID must be 3–32 alphanumeric characters (e.g. C001).")

    if not change_type:
        errors.append("Please select a change type.")

    if not old_name or not old_name.strip():
        errors.append("Current legal name is required.")
    elif not NAME_RE.fullmatch(old_name.strip()):
        errors.append("Current legal name contains invalid characters.")

    if not new_name or not new_name.strip():
        errors.append("New legal name is required.")
    elif not NAME_RE.fullmatch(new_name.strip()):
        errors.append("New legal name contains invalid characters.")

    if (old_name and new_name and
            old_name.strip().casefold() == new_name.strip().casefold()):
        errors.append("New legal name must differ from the current name.")

    if not staff_id or not staff_id.strip():
        errors.append("Staff ID is required for audit purposes.")
    elif not STAFF_ID_RE.fullmatch(staff_id.strip()):
        errors.append("Staff ID must be 2–64 chars (letters, digits, -, _, .).")

    if not ack:
        errors.append("You must confirm the customer's identity has been verified.")

    if document is None:
        errors.append("Please upload a supporting document.")
    else:
        max_mb = 10
        if len(document.getvalue()) > max_mb * 1024 * 1024:
            errors.append(f"Document exceeds the {max_mb} MB upload limit.")

    return errors


# --- Form ------------------------------------------------------------------

ui.section_label("Customer details")

with st.form("intake_form", clear_on_submit=False):

    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        customer_id = st.text_input(
            "Customer ID",
            value="",
            placeholder="e.g. C001",
            max_chars=32,
            help="Bank-issued customer identifier.",
        )
        change_type = st.selectbox(
            "Change type",
            options=["LEGAL_NAME"],
            help="Only Legal Name Change is implemented in this prototype.",
        )
    with col_b:
        old_name = st.text_input(
            "Current legal name",
            value="",
            placeholder="e.g. Priya Sharma",
            max_chars=255,
            help="Name as it currently appears on the customer's record.",
        )
        new_name = st.text_input(
            "New legal name",
            value="",
            placeholder="e.g. Priya Mehta",
            max_chars=255,
            help="Name to be applied after verification.",
        )

    ui.section_label("Supporting document")
    document = st.file_uploader(
        "Upload one of: Marriage Certificate, Gazette Notification, Deed Poll",
        type=["pdf", "png", "jpg", "jpeg"],
        help="Max 10 MB. Accepted formats: PDF, PNG, JPG.",
    )

    ui.section_label("Maker attestation")
    col_s, col_a2 = st.columns([1, 2], gap="large")
    with col_s:
        staff_id = st.text_input(
            "Staff ID",
            value="",
            placeholder="e.g. STF-1042",
            max_chars=64,
            help="Your bank-issued employee ID. Recorded with the request.",
        )
    with col_a2:
        ack = st.checkbox(
            "I confirm the customer's identity has been verified in person "
            "or via approved digital channels, and the supporting document "
            "is the original or a certified copy.",
            value=False,
        )

    st.write("")
    submitted = st.form_submit_button(
        "Submit request", type="primary", use_container_width=True,
    )


# --- Submission handling ---------------------------------------------------

if submitted:
    errors = _validate(customer_id, change_type, old_name, new_name,
                       staff_id, ack, document)
    if errors:
        for e in errors:
            st.error(e, icon="🚫")
        st.stop()

    with st.spinner("Running AI pipeline — extracting fields, scoring confidence, "
                    "generating summary…"):
        try:
            files = {"document": (document.name, document.getvalue(), document.type)}
            data = {
                "customer_id": customer_id.strip(),
                "change_type": change_type,
                "old_name": old_name.strip(),
                "new_name": new_name.strip(),
            }
            r = requests.post(f"{API_BASE_URL}/requests",
                              data=data, files=files, timeout=180)
        except requests.exceptions.RequestException as e:
            st.error(f"Request failed: {e}", icon="🚫")
            st.stop()

    if not r.ok:
        st.error(f"API returned HTTP {r.status_code}", icon="🚫")
        st.code(r.text, language="json")
        st.stop()

    body = r.json()

    st.success(f"Request submitted by **{staff_id.strip()}** — "
               f"reference `{body['request_id']}`", icon="✅")

    ui.section_label("AI verdict")

    rec = body.get("recommended_action")
    conf = body.get("overall_confidence")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Recommended action", rec or "—")
    with col2:
        st.metric("Overall confidence",
                  f"{conf:.1%}" if conf is not None else "—")
    with col3:
        st.metric("Status", body.get("status", "—"))

    st.markdown(
        f'<div style="margin-top:6px">'
        f'<span style="margin-right:10px">{ui.recommendation_badge(rec)}</span>'
        f'<span style="margin-right:10px">{ui.confidence_badge(conf)}</span>'
        f'<span>{ui.status_badge(body.get("status"))}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.write("")
    ui.section_label("AI summary")
    st.info(body.get("ai_summary") or "_(no summary returned)_")

    st.write("")
    with st.container(border=True):
        st.markdown("**What happens next**")
        st.markdown(
            "- A Checker reviews this request from the **Checker Review** page.\n"
            "- The Checker can approve (which fires the mock-RPS write) or reject.\n"
            f"- Reference for tracking: `{body['request_id']}`."
        )
