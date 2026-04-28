"""FastAPI application

  POST /requests                  staff intake (multipart)
  GET  /requests                  checker queue (filter by status)
  GET  /requests/{id}             full detail incl. audit trail
  POST /requests/{id}/decision    HITL — approve/reject
  GET  /filenet/{ref}             serve archived document for UI display

The decision endpoint is the only place in this codebase that imports app.api.rps. 
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import (
    Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app import filenet
from app.agents.graph import run_pipeline
from app.agents.state import AgentState
from app.api import rps
from app.config import settings
from app.db import get_session
from app.models import (
    ChangeType, PendingRequest, RecommendedAction, RequestStatus,
)
from app.observability import configure_logging, get_logger
from app.schemas import (
    Decision, DecisionRequest, DecisionResponse,
    IntakeResponse, PendingRequestDetail, PendingRequestSummary,
)


# App lifecycle

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging once at startup; nothing to tear down."""
    configure_logging()
    log = get_logger(__name__)
    log.info("api_startup",
             model=settings.anthropic_model,
             db=settings.database_url.split("@")[-1])
    yield
    log.info("api_shutdown")


app = FastAPI(
    title="IASW — Intelligent Account Servicing Workflow",
    version="0.1.0",
    description="Agentic prototype for AI-augmented account change requests with HITL approval.",
    lifespan=lifespan,
)

# Streamlit runs on a different port; allow it cross-origin during dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log = get_logger(__name__)


# Health

@app.get("/health")
def health() -> dict:
    """Liveness probe; returns 200 once the app is up."""
    return {"status": "ok"}


# Intake — staff submits a change request + document

@app.post(
    "/requests",
    response_model=IntakeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def intake(
    customer_id: str = Form(..., min_length=1, max_length=32),
    change_type: ChangeType = Form(...),
    old_name: str = Form(..., min_length=1, max_length=255),
    new_name: str = Form(..., min_length=1, max_length=255),
    document: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> IntakeResponse:
    """Accept a change request, archive the document, run the AI pipeline,
    stage a PendingRequest row for the Checker, and return the AI's verdict. 

    The pipeline runs synchronously inline.
    """
    # 1. Read + archive the document
    if not document.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="missing filename")
    ext = document.filename.rsplit(".", 1)[-1].lower()
    content = await document.read()
    try:
        ref = filenet.archive(
            content=content,
            extension=ext,
            metadata={
                "customer_id": customer_id,
                "change_type": change_type.value,
                "original_filename": document.filename,
            },
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 2. Create the PendingRequest row in PENDING_AI status
    pending = PendingRequest(
        customer_id=customer_id,
        change_type=change_type,
        requested_value={"old_name": old_name, "new_name": new_name},
        filenet_ref=ref,
        status=RequestStatus.PENDING_AI,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    request_id = str(pending.request_id)

    # Bind request_id so every downstream log line carries it.
    structlog.contextvars.bind_contextvars(request_id=request_id)
    log.info("intake_received",
             customer_id=customer_id, change_type=change_type.value, filenet_ref=ref)

    try:
        # 3. Run the agentic pipeline
        initial_state: AgentState = {
            "request_id": request_id,
            "customer_id": customer_id,
            "change_type": change_type.value,
            "requested_value": {"old_name": old_name, "new_name": new_name},
            "filenet_ref": ref,
        }
        final_state = run_pipeline(initial_state)

        # 4. Persist the LLM's outputs into PendingRequest
        pending.extracted_value = final_state.get("extracted_value")
        pending.confidence_card = final_state.get("confidence_card")
        pending.overall_confidence = final_state.get("overall_confidence")
        pending.ai_summary = final_state.get("ai_summary")
        rec = final_state.get("recommended_action")
        if rec:
            pending.recommended_action = RecommendedAction(rec)
        pending.status = RequestStatus.AI_VERIFIED_PENDING_HUMAN
        db.commit()
        db.refresh(pending)
    finally:
        structlog.contextvars.unbind_contextvars("request_id")

    return IntakeResponse(
        request_id=pending.request_id,
        status=pending.status.value,
        recommended_action=pending.recommended_action.value if pending.recommended_action else None,
        overall_confidence=pending.overall_confidence,
        ai_summary=pending.ai_summary,
    )


# Checker queue + detail

@app.get("/requests", response_model=list[PendingRequestSummary])
def list_requests(
    status_filter: Optional[RequestStatus] = Query(
        None, alias="status",
        description="Filter by status; defaults to AI_VERIFIED_PENDING_HUMAN (the queue).",
    ),
    db: Session = Depends(get_session),
):
    """List requests for the Checker queue.

    Defaults to AI_VERIFIED_PENDING_HUMAN — the rows that are actually awaiting a checker decision. 
    """
    chosen = status_filter or RequestStatus.AI_VERIFIED_PENDING_HUMAN
    return (
        db.query(PendingRequest)
        .filter(PendingRequest.status == chosen)
        .order_by(PendingRequest.created_at.desc())
        .all()
    )


@app.get("/requests/{request_id}", response_model=PendingRequestDetail)
def get_request(request_id: UUID, db: Session = Depends(get_session)):
    """Full detail for one request, including the per-agent audit trail."""
    pending = (
        db.query(PendingRequest)
        .options(selectinload(PendingRequest.agent_runs))
        .filter(PendingRequest.request_id == request_id)
        .first()
    )
    if pending is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"request {request_id} not found")
    return pending


# HITL 

@app.post("/requests/{request_id}/decision", response_model=DecisionResponse)
def decide(
    request_id: UUID,
    body: DecisionRequest,
    db: Session = Depends(get_session),
):
    """Approve or reject a request. On APPROVE this handler — and only this handler — calls rps.commit_change. 

    The customer mutation and the request status flip happen in the same transaction so a partial state does not happen
    """
    pending = db.get(PendingRequest, request_id)
    if pending is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"request {request_id} not found")
    if pending.status != RequestStatus.AI_VERIFIED_PENDING_HUMAN:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"request is in status {pending.status.value}; "
                f"only AI_VERIFIED_PENDING_HUMAN is decideable"
            ),
        )

    structlog.contextvars.bind_contextvars(request_id=str(request_id))
    decided_at = datetime.now(timezone.utc)

    pending.checker_user = body.checker_user
    pending.checker_reason = body.reason
    pending.checker_decided_at = decided_at

    try:
        if body.decision == Decision.APPROVE:
            # The single, audited write to mock RPS — same session, same txn.
            rps.commit_change(
                session=db,
                customer_id=pending.customer_id,
                change_type=pending.change_type,
                requested_value=pending.requested_value,
            )
            pending.status = RequestStatus.APPROVED
            log.info("decision", outcome="APPROVE", checker_user=body.checker_user)
        else:
            pending.status = RequestStatus.REJECTED
            log.info("decision", outcome="REJECT", checker_user=body.checker_user)

        db.commit()
    finally:
        structlog.contextvars.unbind_contextvars("request_id")

    return DecisionResponse(
        request_id=pending.request_id,
        status=pending.status.value,
        decided_at=decided_at,
    )


# FileNet (archived doc for Checker UI for display)

@app.get("/filenet/{ref}")
def serve_filenet(ref: str):
    """Stream the archived document so the Checker UI can show it side-by-side."""
    try:
        path = filenet.fetch_path(ref)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"filenet ref {ref} not found")
    media_type = {
        ".pdf":  "application/pdf",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(path.suffix.lower(), "application/octet-stream")
    # `inline` disposition keeps browsers from force-downloading PDFs in iframes.
    return FileResponse(
        path=path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )