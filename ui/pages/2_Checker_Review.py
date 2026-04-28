"""Checker Review - page 2 of the IASW Streamlit UI.

The Approve button fires POST /requests/{id}/decision with decision=APPROVE,
which is the ONLY path to the mock-RPS write.
"""

import os
from typing import Optional

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="Checker Review — IASW", layout="wide")


#Session state
# A single None|str variable controls which view we render: None means
#a request_id means show that request's detail.

if "selected_request_id" not in st.session_state:
    st.session_state.selected_request_id = None


# HTTP helpers

def _fetch_queue() -> list[dict]:
    try:
        r = requests.get(f"{API_BASE_URL}/requests", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Queue fetch failed: {e}")
        return []


def _fetch_detail(request_id: str) -> Optional[dict]:
    try:
        r = requests.get(f"{API_BASE_URL}/requests/{request_id}", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Detail fetch failed: {e}")
        return None


def _submit_decision(
    request_id: str, decision: str, reason: str, checker_user: str,
) -> Optional[dict]:
    try:
        r = requests.post(
            f"{API_BASE_URL}/requests/{request_id}/decision",
            json={"decision": decision, "reason": reason, "checker_user": checker_user},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Decision submission failed: {e}")
        return None


#Header + navigation

st.title("Checker Review")
st.caption(
    "Review AI-verified requests. The Checker is the only authority that "
    "can commit a change to the (mocked) core banking system."
)

if st.session_state.selected_request_id:
    if st.button("← Back to queue"):
        st.session_state.selected_request_id = None
        st.rerun()


# Queue view 

def render_queue() -> None:
    queue = _fetch_queue()
    st.subheader(f"Queue ({len(queue)} pending)")

    if not queue:
        st.info(
            "No requests awaiting review. Submit one from the **Staff Intake** "
            "page in the sidebar."
        )
        return

    for row in queue:
        confidence = row.get("overall_confidence")
        confidence_str = f"{confidence:.1%}" if confidence is not None else "—"
        rec = row.get("recommended_action") or "—"

        with st.container(border=True):
            cols = st.columns([3, 2, 2, 1])
            with cols[0]:
                st.markdown(f"**{row['change_type']}** · Customer `{row['customer_id']}`")
                rv = row.get("requested_value", {})
                st.caption(f"{rv.get('old_name', '?')} → {rv.get('new_name', '?')}")
                st.caption(f"Request `{row['request_id']}`")
            with cols[1]:
                st.metric("Confidence", confidence_str)
            with cols[2]:
                st.metric("AI Recommends", rec)
            with cols[3]:
                if st.button("Review", key=f"review_{row['request_id']}"):
                    st.session_state.selected_request_id = row["request_id"]
                    st.rerun()


# Detail view 
def render_detail(request_id: str) -> None:
    detail = _fetch_detail(request_id)
    if not detail:
        st.session_state.selected_request_id = None
        return

    st.subheader(f"Request {detail['request_id']}")
    st.caption(
        f"{detail['change_type']} for customer `{detail['customer_id']}` · "
        f"status **{detail['status']}**"
    )

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("### AI Summary")
        st.info(detail.get("ai_summary") or "(no summary)")

        st.markdown("### Confidence Score Card")
        card = detail.get("confidence_card") or {}
        scores = card.get("scores") or {}
        if not scores:
            st.warning("No score card available.")
        else:
            for dim, payload in scores.items():
                score = payload.get("score", "?")
                reason = payload.get("reason", "")
                label = dim.replace("_", " ").title()
                st.markdown(f"**{label}** — `{score}/5`  {reason}")

        overall = detail.get("overall_confidence")
        if overall is not None:
            st.markdown(f"**Overall Confidence:** `{overall:.2%}`")

        with st.expander("Extracted Fields"):
            st.json(detail.get("extracted_value") or {})

        with st.expander("Audit Trail (Agent Runs)"):
            runs = detail.get("agent_runs", [])
            if not runs:
                st.caption("No audit rows.")
            for run in runs:
                ms = run.get("duration_ms")
                ms_str = f"{ms}ms" if ms is not None else "?"
                err = run.get("error")
                line = f"- `{run['agent']}` · {run['status']} · {ms_str}"
                if err:
                    line += f" · ⚠ {err}"
                st.markdown(line)

    with right:
        st.markdown("### Supporting Document")
        ref = detail.get("filenet_ref")
        if not ref:
            st.warning("No document attached.")
        else:
            doc_url = f"{API_BASE_URL}/filenet/{ref}"
            st.markdown(f"[Open in new tab ↗]({doc_url})")
            # iframe works for both PDF and image MIME types in modern browsers.
            # We use unsafe_allow_html because Streamlit has no native iframe widget.
            st.markdown(
                f'<iframe src="{doc_url}" width="100%" height="600px" '
                f'style="border:1px solid #ccc; border-radius:4px"></iframe>',
                unsafe_allow_html=True,
            )

    # Decision form
    st.markdown("---")
    st.markdown("### Decision")

    if detail["status"] != "AI_VERIFIED_PENDING_HUMAN":
        st.warning(
            f"Status is **{detail['status']}** — this request has already "
            f"been acted on and cannot be decided again."
        )
        return

    checker_user = st.text_input(
        "Checker username", value="checker_demo", key="checker_user",
    )
    reason = st.text_area(
        "Reason / notes",
        value="",
        height=100,
        placeholder="e.g., 'Marriage Certificate verified, names match.'",
        key="checker_reason",
    )

    col_a, col_r = st.columns(2)
    with col_a:
        approve = st.button(
            "✓ Approve & Write to RPS", type="primary",
            use_container_width=True,
        )
    with col_r:
        reject = st.button("✗ Reject", use_container_width=True)

    if approve or reject:
        if not reason.strip():
            st.error("Please provide a reason before deciding.")
            return
        decision_value = "APPROVE" if approve else "REJECT"
        with st.spinner("Submitting decision..."):
            result = _submit_decision(
                detail["request_id"], decision_value, reason, checker_user,
            )
        if result:
            st.success(
                f"Decision submitted — request is now **{result['status']}**"
            )
            st.session_state.selected_request_id = None
            st.rerun()


# Main render 

if st.session_state.selected_request_id:
    render_detail(st.session_state.selected_request_id)
else:
    render_queue()