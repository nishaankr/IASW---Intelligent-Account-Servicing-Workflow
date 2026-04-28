"""
Three tables, each with a single, well-defined responsibility:

  Customer       - the mock RPS (core banking) record. Source of truth that
                   change requests validate against and ultimately mutate.
                   Modified ONLY by app/api/rps.py, only after human approval.

  PendingRequest - a change request after the AI pipeline has finished and
                   is awaiting human decision. Holds the original ask, every
                   AI output, and (once acted upon) the checker's decision.

  AgentRun       - one row per agent execution. The audit trail; lets us
                   reconstruct exactly which agent ran with what input/output
                   for any given request.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db import Base


# Enums
# Inheriting from str makes them JSON-serialisable and human-readable in the DB.

class ChangeType(str, enum.Enum):
    LEGAL_NAME = "LEGAL_NAME"
    ADDRESS = "ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    CONTACT_EMAIL = "CONTACT_EMAIL"


class RequestStatus(str, enum.Enum):
    PENDING_AI = "PENDING_AI"                              # row created, pipeline running or queued
    AI_VERIFIED_PENDING_HUMAN = "AI_VERIFIED_PENDING_HUMAN"  # pipeline succeeded, awaiting checker
    APPROVED = "APPROVED"                                  # checker approved, RPS written
    REJECTED = "REJECTED"   

class RecommendedAction(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


class AgentRunStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


# Tables 
# Timestamps default to func.now() server-sid
class Customer(Base):

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class PendingRequest(Base):
   #A change request after the AI pipeline has run, awaiting checker decision

    __tablename__ = "pending_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customers.customer_id"), nullable=False,
    )
    change_type: Mapped[ChangeType] = mapped_column(Enum(ChangeType), nullable=False)

    # validated at the API boundary by Pydantic schemas.
    requested_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    extracted_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[RecommendedAction | None] = mapped_column(
        Enum(RecommendedAction), nullable=True,
    )

    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), nullable=False,
        default=RequestStatus.PENDING_AI,
    )

    filenet_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Checker fields stay NULL until a hitl  acts on the request.
    checker_user: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checker_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checker_decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    customer: Mapped[Customer] = relationship(Customer)
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Checker queue endpoint filters by status; this index keeps it fast.
        Index("ix_pending_requests_status", "status"),
        Index("ix_pending_requests_customer_id", "customer_id"),
    )


class AgentRun(Base):        #One row per agent execution. The audit trail.

    __tablename__ = "agent_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("pending_requests.request_id"), nullable=False,
    )
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(Enum(AgentRunStatus), nullable=False)

    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )

    request: Mapped[PendingRequest] = relationship(back_populates="agent_runs")

    __table_args__ = (
        Index("ix_agent_runs_request_id", "request_id"),
        Index("ix_agent_runs_agent", "agent"),
    )