"""The four agent functions that make up the IASW pipeline.

Each function:
  -Takes an AgentState dict.
  -Performs its job (DB lookup, LLM call, scoring math, summary generation).
  -Returns a dict of UPDATES that LangGraph merges back into state.
  -Writes one AgentRun audit row via the _agent_run context manager.
  -Honours the `halt` short-circuit flag - if validation failed, downstream nodes return early with no work done.

    Temperature is 0 for extraction and scoring and 0.3 for summary 
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional

from anthropic import Anthropic
from rapidfuzz.fuzz import token_set_ratio

from app.agents.prompts import EXTRACTION_SYSTEM, SCORING_SYSTEM, SUMMARY_SYSTEM
from app.agents.state import AgentState
from app.config import settings
from app.db import SessionLocal
from app.filenet import fetch_path
from app.models import AgentRun, AgentRunStatus, Customer, RecommendedAction
from app.observability import get_logger

log = get_logger(__name__)

# Shared Claude client; one connection pool reused across nodes and requests.
_client = Anthropic(api_key=settings.anthropic_api_key)


# Weights for aggregating the five 0-5 dimension scores into overall_confidence.
# Sum to 1.0. Reflects rubric emphasis on identity (name_match) and authenticity over completeness/clarity.

#mathematical decisions and not a LLM judgement
_DIMENSION_WEIGHTS = {
    "name_match":              0.30,
    "document_type_relevance": 0.20,
    "document_authenticity":   0.20,
    "field_completeness":      0.15,
    "document_clarity":        0.15,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def _agent_run(agent_name: str, request_id: str, input_payload: dict) -> Iterator[dict]:
    """Timestamping an agent execution and write an AgentRun erro audit row.

    """
    start = time.perf_counter()
    output_box: dict = {}
    error: Optional[str] = None
    try:
        yield output_box
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            with SessionLocal() as session:
                session.add(AgentRun(
                    request_id=uuid.UUID(request_id),
                    agent=agent_name,
                    status=AgentRunStatus.ERROR if error else AgentRunStatus.SUCCESS,
                    input_payload=input_payload,
                    output_payload=output_box.get("payload"),
                    error=error,
                    duration_ms=duration_ms,
                ))
                session.commit()
        except Exception as audit_exc:
            # Audit failures must not mask the real exception.
            log.error("agent_run_audit_write_failed", agent=agent_name,
                      request_id=request_id, audit_error=str(audit_exc))
        log.info(
            "agent_run_complete",
            agent=agent_name,
            request_id=request_id,
            duration_ms=duration_ms,
            status="ERROR" if error else "SUCCESS",
        )


def _build_document_content_block(filenet_ref: str) -> dict:
    """We make the Claude content block for the archived document.

    Claude's API distinguishes images (PNG/JPEG) from documents (PDF) by content-type tag. 
    Non-supported extensions are rejected upstream by app.filenet.
    """
    path = fetch_path(filenet_ref)
    ext = path.suffix.lower().lstrip(".")
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")

    if ext == "pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext)
    if media_type is None:
        raise ValueError(f"Unsupported document extension for vision: .{ext}")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def _parse_json(text: str) -> dict:
    """Parse JSON from a model response, stripping markdown fences if present.

    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _fuzzy_ratio(a: Optional[str], b: Optional[str]) -> float:
    """Token-set fuzzy ratio in [0.0, 1.0].
    Used to match names with minor variations
    """
    if not a or not b:
        return 0.0
    return round(token_set_ratio(a, b) / 100.0, 4)


def _aggregate_overall_confidence(scores: dict) -> float:
    """Weighted average of the five 0-5 dimension scores, normalised to [0.0, 1.0]."""
    total = 0.0
    for dim, weight in _DIMENSION_WEIGHTS.items():
        s = scores.get(dim, {}).get("score", 0) or 0
        total += float(s) * weight
    return round(total / 5.0, 4)


def _recommend_action(overall_confidence: float) -> str:
    """Threshold-based recommendation."""
    if overall_confidence >= settings.approve_threshold:
        return RecommendedAction.APPROVE.value
    if overall_confidence < settings.reject_threshold:
        return RecommendedAction.REJECT.value
    return RecommendedAction.REVIEW.value


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def validation_node(state: AgentState) -> dict:
    """Confirm the customer exists in mock RPS and load their current record, from Db, not using LLM

    Sets state.halt to "CUSTOMER_NOT_FOUND" if the customer is missing, which downstream nodes honour to short-circuit.
    """
    request_id = state["request_id"]
    customer_id = state["customer_id"]

    with _agent_run(
        "validation",
        request_id,
        input_payload={"customer_id": customer_id, "change_type": state["change_type"]},
    ) as out:
        with SessionLocal() as session:
            customer = session.get(Customer, customer_id)

        if customer is None:
            out["payload"] = {"customer_record": None, "halt": "CUSTOMER_NOT_FOUND"}
            return {
                "customer_record": None,
                "halt": "CUSTOMER_NOT_FOUND",
                "errors": [{
                    "agent": "validation",
                    "code": "CUSTOMER_NOT_FOUND",
                    "customer_id": customer_id,
                }],
            }

        record = {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
            "date_of_birth": customer.date_of_birth.isoformat() if customer.date_of_birth else None,
        }
        out["payload"] = {"customer_record": record}
        return {"customer_record": record}


def extraction_node(state: AgentState) -> dict:
    """Run Claude Vision over the archived document.

    One LLM call producing TWO outputs simultaneously - structured fields AND three forgery heuristics. 
    Sharing the call avoids paying for two passes over the same image.
    """
    if state.get("halt"):
        return {}

    request_id = state["request_id"]
    filenet_ref = state["filenet_ref"]

    with _agent_run(
        "extraction",
        request_id,
        input_payload={"filenet_ref": filenet_ref},
    ) as out:
        doc_block = _build_document_content_block(filenet_ref)

        message = _client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            temperature=0,
            system=EXTRACTION_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    doc_block,
                    {"type": "text", "text": "Analyse the document per your instructions and return the JSON."},
                ],
            }],
        )
        parsed = _parse_json(message.content[0].text)

        out["payload"] = parsed
        return {
            "extracted_value": parsed.get("extracted_value", {}) or {},
            "forgery_signals": parsed.get("forgery_signals", {}) or {},
        }


def scoring_node(state: AgentState) -> dict:
    """Score five dimensions and compute overall_confidence.

    Hybrid approach:
        `name_match_ratio` is computed deterministically with rapidfuzz so the scorer has a numeric anchor for the name comparison.
        The five 0-5 dimension scores come from Claude per the SCORING prompt with `name_match_ratio` provided as a hint.
        `overall_confidence` is a weighted aggregation done in Python - the weights are a product decision
    """
    if state.get("halt"):
        return {}

    request_id = state["request_id"]
    requested = state["requested_value"]
    extracted = state.get("extracted_value") or {}
    customer_record = state.get("customer_record")
    forgery_signals = state.get("forgery_signals") or {}

    name_match_ratio = {
        "old_to_bride": _fuzzy_ratio(requested.get("old_name"), extracted.get("bride_name")),
        "new_to_married": _fuzzy_ratio(requested.get("new_name"), extracted.get("married_name")),
    }

    packet = {
        "request": {
            "change_type": state["change_type"],
            "old_name": requested.get("old_name"),
            "new_name": requested.get("new_name"),
        },
        "customer_record": customer_record,
        "extracted_value": extracted,
        "forgery_signals": forgery_signals,
        "name_match_ratio": name_match_ratio,
    }

    with _agent_run(
        "scoring",
        request_id,
        input_payload=packet,
    ) as out:
        message = _client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            temperature=0,
            system=SCORING_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(packet, default=str)}],
        )
        parsed = _parse_json(message.content[0].text)
        scores = parsed.get("scores", {})

        overall = _aggregate_overall_confidence(scores)
        confidence_card = {
            "scores": scores,
            "name_match_ratio": name_match_ratio,
            "overall_confidence": overall,
            "weights": _DIMENSION_WEIGHTS,
        }

        out["payload"] = {
            "confidence_card": confidence_card,
            "overall_confidence": overall,
        }
        return {
            "confidence_card": confidence_card,
            "overall_confidence": overall,
        }


def summary_node(state: AgentState) -> dict:
    """A one-paragraph human-readable summary + a recommended action.

    """
    if state.get("halt"):
        return {}

    request_id = state["request_id"]
    overall = state.get("overall_confidence", 0.0) or 0.0

    packet = {
        "request": {
            "change_type": state["change_type"],
            "old_name": state["requested_value"].get("old_name"),
            "new_name": state["requested_value"].get("new_name"),
        },
        "extracted_value": state.get("extracted_value"),
        "confidence_card": state.get("confidence_card"),
        "overall_confidence": overall,
    }

    with _agent_run(
        "summary",
        request_id,
        input_payload=packet,
    ) as out:
        message = _client.messages.create(
            model=settings.anthropic_model,
            max_tokens=512,
            temperature=0.3,
            system=SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(packet, default=str)}],
        )
        summary = message.content[0].text.strip()
        recommended = _recommend_action(overall)

        out["payload"] = {"ai_summary": summary, "recommended_action": recommended}
        return {"ai_summary": summary, "recommended_action": recommended}