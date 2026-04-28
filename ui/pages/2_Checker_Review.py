"""Checker Review — page 2 of the IASW Streamlit UI.

Two views: a queue list and a per-request detail page. The detail page lays
out AI outputs on the left and the supporting document + decision form on
the right so the reviewer sees everything at one glance.

The Approve button is the only path to the mock-RPS write.
"""

import os
from typing import Optional

import requests
import streamlit as st

import _components as ui

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="Checker Review — IASW", layout="wide", page_icon="✅")
ui.inject_css()


# --- Session state ---------------------------------------------------------

if "selected_request_id" not in st.session_state:
    st.session_state.selected_request_id = None


# --- HTTP helpers ----------------------------------------------------------

def _fetch_queue() -> list[dict]:
    try:
        r = requests.get(f"{API_BASE_URL}/requests", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Queue fetch failed: {e}", icon="🚫")
        return []


def _fetch_detail(request_id: str) -> Optional[dict]:
    try:
        r = requests.get(f"{API_BASE_URL}/requests/{request_id}", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Detail fetch failed: {e}", icon="🚫")
        return None


def _submit_decision(request_id: str, decision: str, reason: str,
                     checker_user: str) -> Optional[dict]:
    try:
        r = requests.post(
            f"{API_BASE_URL}/requests/{request_id}/decision",
            json={"decision": decision, "reason": reason, "checker_user": checker_user},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Decision submission failed: {e}", icon="🚫")
        return None


# --- Hero + breadcrumb -----------------------------------------------------

ui.hero(
    "Checker Review",
    "Review AI-verified requests. The Checker is the only authority that can "
    "commit a change to the (mocked) core banking system.",
)

if st.session_state.selected_request_id:
    if st.button("← Back to queue", type="secondary"):
        st.session_state.selected_request_id = None
        st.rerun()


# --- Queue view ------------------------------------------------------------

def render_queue() -> None:
    queue = _fetch_queue()

    ui.section_label(f"Queue · {len(queue)} pending")

    if not queue:
        st.info(
            "No requests awaiting review. Submit one from the **Staff Intake** "
            "page.",
            icon="📭",
        )
        return

    for row in queue:
        confidence = row.get("overall_confidence")
        rec = row.get("recommended_action")
        rv = row.get("requested_value", {})

        with st.container(border=True):
            cols = st.columns([3.2, 1.6, 1.6, 1.0], gap="medium")

            with cols[0]:
                st.markdown(
                    f"**{row['change_type']}**  &nbsp;·&nbsp;  "
                    f"Customer `{row['customer_id']}`"
                )
                st.markdown(
                    f"<span style='color:{ui.COLOR_TEXT_MUTED};font-size:14px'>"
                    f"{rv.get('old_name', '?')}  →  "
                    f"{rv.get('new_name', '?')}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Request `{row['request_id']}`")

            with cols[1]:
                st.markdown(
                    f"<div style='font-size:11px;color:{ui.COLOR_TEXT_MUTED};"
                    f"font-weight:600;letter-spacing:0.05em;margin-bottom:6px'>"
                    f"CONFIDENCE</div>"
                    + ui.confidence_badge(confidence),
                    unsafe_allow_html=True,
                )

            with cols[2]:
                st.markdown(
                    f"<div style='font-size:11px;color:{ui.COLOR_TEXT_MUTED};"
                    f"font-weight:600;letter-spacing:0.05em;margin-bottom:6px'>"
                    f"AI RECOMMENDS</div>"
                    + ui.recommendation_badge(rec),
                    unsafe_allow_html=True,
                )

            with cols[3]:
                if st.button("Review →",
                             key=f"review_{row['request_id']}",
                             type="primary",
                             use_container_width=True):
                    st.session_state.selected_request_id = row["request_id"]
                    st.rerun()


# --- Detail view -----------------------------------------------------------

def render_detail(request_id: str) -> None:
    detail = _fetch_detail(request_id)
    if not detail:
        st.session_state.selected_request_id = None
        return

    rv = detail.get("requested_value", {})

    # Header strip
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1.4, 1.4])
        with c1:
            st.markdown(
                f"**{detail['change_type']}**  &nbsp;·&nbsp;  "
                f"Customer `{detail['customer_id']}`"
            )
            st.markdown(
                f"<span style='color:{ui.COLOR_TEXT_MUTED};font-size:14px'>"
                f"{rv.get('old_name', '?')}  →  {rv.get('new_name', '?')}</span>",
                unsafe_allow_html=True,
            )
            st.caption(f"Request ID: `{detail['request_id']}`")
        with c2:
            st.markdown(
                f"<div style='font-size:11px;color:{ui.COLOR_TEXT_MUTED};"
                f"font-weight:600;letter-spacing:0.05em;margin-bottom:6px'>STATUS</div>"
                + ui.status_badge(detail.get("status")),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"<div style='font-size:11px;color:{ui.COLOR_TEXT_MUTED};"
                f"font-weight:600;letter-spacing:0.05em;margin-bottom:6px'>CONFIDENCE</div>"
                + ui.confidence_badge(detail.get("overall_confidence")),
                unsafe_allow_html=True,
            )

    st.write("")

    # Two columns: AI on left, document + decision on right
    left, right = st.columns([3, 2.4], gap="large")

    # --- LEFT: AI outputs ---
    with left:
        ui.section_label("AI summary")
        st.info(detail.get("ai_summary") or "_(no summary)_")

        ui.section_label("Confidence score card")
        card = detail.get("confidence_card") or {}
        scores = card.get("scores") or {}

        if not scores:
            st.warning("No score card available.")
        else:
            rows_html = []
            for dim, payload in scores.items():
                label = dim.replace("_", " ").title()
                rows_html.append(
                    ui.score_row(label, payload.get("score"), payload.get("reason", ""))
                )
            st.markdown("".join(rows_html), unsafe_allow_html=True)

        with st.expander("Extracted fields"):
            st.json(detail.get("extracted_value") or {})

        with st.expander("Audit trail (per-agent runs)"):
            runs = detail.get("agent_runs", [])
            if not runs:
                st.caption("No audit rows.")
            for run in runs:
                ms = run.get("duration_ms")
                ms_str = f"{ms} ms" if ms is not None else "?"
                err = run.get("error")
                ok = run.get("status") == "SUCCESS"
                icon = "✅" if ok else "⚠️"
                line = f"{icon}  `{run['agent']}` · {run.get('status', '?')} · {ms_str}"
                if err:
                    line += f"\n   *{err}*"
                st.markdown(line)

    # --- RIGHT: document, then decision form below it ---
    with right:
        ui.section_label("Supporting document")
        ref = detail.get("filenet_ref")
        if not ref:
            st.warning("No document attached.")
        else:
            doc_url = f"{API_BASE_URL}/filenet/{ref}"
            ui.render_document(doc_url, height=620)

        st.write("")
        ui.section_label("Decision")

        if detail["status"] != "AI_VERIFIED_PENDING_HUMAN":
            st.warning(
                f"Status is **{detail['status']}** — this request has already "
                f"been acted on and cannot be decided again.",
                icon="🔒",
            )
            return

        with st.container(border=True):
            checker_user = st.text_input(
                "Checker username",
                value="",
                placeholder="e.g. checker_demo",
                key="checker_user",
            )
            reason = st.text_area(
                "Reason / notes",
                value="",
                height=110,
                placeholder=(
                    "e.g. Marriage Certificate verified. "
                    "Bride name matches current record; married name matches the "
                    "requested change. AI confidence high."
                ),
                key="checker_reason",
            )

            col_a, col_r = st.columns(2)
            with col_a:
                approve = st.button(
                    "✓  Approve & Write to RPS",
                    type="primary",
                    use_container_width=True,
                )
            with col_r:
                reject = st.button(
                    "✗  Reject",
                    use_container_width=True,
                )

        if approve or reject:
            if not checker_user.strip():
                st.error("Checker username is required.", icon="🚫")
                return
            if not reason.strip():
                st.error("Please provide a reason before deciding.", icon="🚫")
                return
            decision_value = "APPROVE" if approve else "REJECT"
            with st.spinner("Submitting decision…"):
                result = _submit_decision(
                    detail["request_id"], decision_value,
                    reason.strip(), checker_user.strip(),
                )
            if result:
                st.success(
                    f"Decision submitted — request is now **{result['status']}**",
                    icon="✅",
                )
                st.session_state.selected_request_id = None
                st.rerun()


# --- Main render -----------------------------------------------------------

if st.session_state.selected_request_id:
    render_detail(st.session_state.selected_request_id)
else:
    render_queue()
