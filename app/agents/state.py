"""The LANGGRAPH shared state object that flows through every node in the LangGraph.

Three logical groups of fields:

  Inputs   — set by the API before the pipeline runs; nodes treat as read-only.
  Pipeline — populated by individual nodes as they execute.
  Control  — short-circuit flag + accumulated error log.
"""

import operator
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """`total=False` means every field is optional — early in the run, only the input fields are populated; fields fill in as nodes execute.
    """

    # Inputs (read-only)
    request_id: str          # the PendingRequest.request_id
    customer_id: str         
    change_type: str         # "LEGAL_NAME", "ADDRESS", etc.
    requested_value: dict    # shape varies by change_type — for LEGAL_NAME: {"old_name", "new_name"}, hence we use a dict
    filenet_ref: str         

    # outputs (filled as our nodes execute)
    customer_record: Optional[dict]      # validation_node — None if customer not found
    extracted_value: Optional[dict]      # extraction_node — valuies we have pulled from the document
    forgery_signals: Optional[dict]      # extraction_node — three forgery heuristic scores that we ahve outlined in the prompt
    confidence_card: Optional[dict]      # scoring_node — per-field scores + LLM reasoning
    overall_confidence: Optional[float]  # scoring_node — Approximate score in [0.0, 1.0]
    ai_summary: Optional[str]            # summary_node — human-readable paragraph for Checker
    recommended_action: Optional[str]    # summary_node — "APPROVE" / "REJECT" / "REVIEW"

    # Control flow + Logs
    halt: Optional[str]                  # Gives a reason for error
    errors: Annotated[list[dict], operator.add]  # Tells langraph to append the errors and not recycle through the life of the Agent