"""Request/response schemas for the FastAPI layer.

  * Wire schemas need to be JSON-serialisable; ORM models hold ORM state.
  * Validation rules

"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Enums (input validation)

class Decision(str, enum.Enum):
#Outcome of a Checker action.

    APPROVE = "APPROVE"
    REJECT = "REJECT"


# Intake
# The intake endpoint accepts form-data 
# FastAPI handles the form parameters directly in the route signature. 
# Only the response is modelled

class IntakeResponse(BaseModel):
    #Returned by POST /requests once the AI pipeline has finished.

    request_id: UUID
    status: str
    recommended_action: Optional[str] = None
    overall_confidence: Optional[float] = None
    ai_summary: Optional[str] = None


# Checker queue + detailss

class AgentRunSummary(BaseModel):
    """One error audit row"""
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    agent: str
    status: str
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime


class PendingRequestSummary(BaseModel):
    """One row in the Checker queue. """
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    customer_id: str
    change_type: str
    requested_value: dict
    overall_confidence: Optional[float] = None
    recommended_action: Optional[str] = None
    status: str
    created_at: datetime


class PendingRequestDetail(BaseModel):
    """Full detail for one request — everything the Checker UI needs."""
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    customer_id: str
    change_type: str
    requested_value: dict
    extracted_value: Optional[dict] = None
    confidence_card: Optional[dict] = None
    overall_confidence: Optional[float] = None
    ai_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    status: str
    filenet_ref: Optional[str] = None
    checker_user: Optional[str] = None
    checker_reason: Optional[str] = None
    checker_decided_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    agent_runs: list[AgentRunSummary] = Field(default_factory=list)


# Decision (HITL boundary)

class DecisionRequest(BaseModel):
    """Body for POST /requests/{id}/decision.

    The act of approving here is what releases the mock-RPS write 
    There is no other path to a write, anywhere in the codebase. decision must be one of two values, reason is non-empty
    """
    decision: Decision
    reason: str = Field(min_length=1, max_length=2000)
    checker_user: str = Field(min_length=1, max_length=64)


class DecisionResponse(BaseModel):
    request_id: UUID
    status: str
    decided_at: datetime