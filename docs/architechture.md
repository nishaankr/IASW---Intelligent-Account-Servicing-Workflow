# IASW — Architecture

Technical companion to the [README](../README.md).

This document will help you understand exactly how each component is wired, what it owns,
and where the trade-offs are.

## 1. System overview

Five layers, each with a single, well-defined responsibility:

| Layer                | Responsibility                                                                    | Implementation                  |
| -------------------- | --------------------------------------------------------------------------------- | ------------------------------- |
| **Frontend**         | Capture staff intake; let checker review and decide                               | Streamlit (multi-page)          |
| **API**              | Validate inputs, orchestrate intake, expose checker queue, gate the HITL boundary | FastAPI                         |
| **Agentic pipeline** | Verify the document, score confidence, summarise for human review                 | LangGraph + Claude Sonnet 4.5   |
| **Data**             | Persist canonical Customer (mock RPS), pending requests, per-agent audit          | Postgres 16                     |
| **Document store**   | Archive supporting documents, retrievable by reference                            | Local filesystem (FileNet mock) |

The layers do not bypass each other. The API owns all writes to canonical
tables; agents only write to the audit log.

The HITL boundary lives at a
single Python module (`app/api/rps.py`) imported by exactly one place.

## 2. Component architecture

```mermaid
graph LR
  classDef sync fill:#e8f5e9,stroke:#2e7d32
  classDef boundary fill:#ffebee,stroke:#c62828,stroke-width:3px

  subgraph UI [Streamlit]
    Staff["Staff Intake"]
    Checker["Checker Review"]
  end

  subgraph API [FastAPI]
    Intake["POST /requests"]:::sync
    List["GET /requests"]:::sync
    Detail["GET /requests/{id}"]:::sync
    DecisionEP["POST /requests/{id}/decision"]:::sync
    DocServe["GET /filenet/{ref}"]:::sync
    RPS["rps.commit_change"]:::boundary
  end

  subgraph Pipeline [LangGraph pipeline — sync within request]
    direction TB
    V[Validation]
    E["Extraction<br/>Claude Vision"]
    S["Scoring<br/>rapidfuzz + Claude"]
    U["Summary<br/>Claude"]
    V --> E --> S --> U
  end

  subgraph Storage
    Customer[customers]
    Pending[pending_requests]
    Audit[agent_runs]
    Files["filenet_storage/"]
  end

  Anthropic{{Claude API}}

  Staff -->|sync HTTP| Intake
  Checker -->|sync HTTP| List
  Checker -->|sync HTTP| Detail
  Checker -->|sync HTTP| DecisionEP
  Checker -->|iframe| DocServe

  Intake --> Pipeline
  Intake -->|archive| Files
  Intake -->|create row| Pending
  Pipeline -->|append per node| Audit
  V -->|read| Customer
  E -->|fetch_path| Files
  E -->|vision| Anthropic
  S -->|messages| Anthropic
  U -->|messages| Anthropic

  DecisionEP -->|update status| Pending
  DecisionEP -.->|APPROVE only| RPS
  RPS -->|write| Customer
  DocServe -->|read| Files
```

**Sync vs async.** Every interaction in the prototype is synchronous
within one HTTP request.
For production:

- Intake would return immediately with a `request_id`; the pipeline
  would run in a job queue (Celery / RQ / Temporal).
- The Checker UI would poll `/requests/{id}` for status changes or
  subscribe via WebSocket / SSE.
- Document archival to FileNet would be async-replicated for durability.

## 3. Agent pipeline detail

Four-node LangGraph state machine. Each node receives a shared
`AgentState` dict, performs its job, and returns updates that LangGraph
merges back. The graph is linear; conditional edges are unused for the
prototype (in-node `halt` checks short-circuit).

### 3.1 AgentState

```python
class AgentState(TypedDict, total=False):
    # Inputs (set once by the API before run_pipeline)
    request_id: str
    customer_id: str
    change_type: str
    requested_value: dict
    filenet_ref: str

    # Pipeline outputs (filled in node by node)
    customer_record: Optional[dict]
    extracted_value: Optional[dict]
    forgery_signals: Optional[dict]
    confidence_card: Optional[dict]
    overall_confidence: Optional[float]
    ai_summary: Optional[str]
    recommended_action: Optional[str]

    # Control flow + audit
    halt: Optional[str]
    errors: Annotated[list[dict], operator.add]
```

`errors` uses LangGraph's reducer pattern: each node appends rather than
overwrites. Other fields use the default merge (replace).

### 3.2 Per-node specification

| Node                | Reads                                                                         | External tools                                                          | Writes                                                                    | LLM details                                                                                   |
| ------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **validation_node** | `customer_id`, `change_type`                                                  | Postgres `SELECT customers`                                             | `customer_record` _or_ `halt="CUSTOMER_NOT_FOUND"`                        | none                                                                                          |
| **extraction_node** | `filenet_ref`                                                                 | FileNet (read bytes); Claude Messages API (vision)                      | `extracted_value` (7 fields), `forgery_signals` (3 heuristics × 0–5)      | `claude-sonnet-4-5` · temp 0 · max 2048 · `EXTRACTION_SYSTEM`                                 |
| **scoring_node**    | `requested_value`, `extracted_value`, `customer_record`, `forgery_signals`    | `rapidfuzz.token_set_ratio` (deterministic); Claude Messages API (text) | `confidence_card` (5 dims × 0–5 + reason), `overall_confidence` ∈ [0, 1]  | `claude-sonnet-4-5` · temp 0 · max 1024 · `SCORING_SYSTEM`                                    |
| **summary_node**    | `confidence_card`, `extracted_value`, `requested_value`, `overall_confidence` | Claude Messages API (text); threshold compare (deterministic)           | `ai_summary` (50–100 w), `recommended_action` ∈ {APPROVE, REJECT, REVIEW} | `claude-sonnet-4-5` · temp 0.3 · max 512 · `SUMMARY_SYSTEM` · recommendation in code, not LLM |

### 3.3 Error/Audit trail

Every node writes one `AgentRun` row via the `_agent_run` context
manager (`app/agents/nodes.py`). Each row captures: agent name, status
(SUCCESS / ERROR / SKIPPED), input payload, output payload, error
string if any, duration ms, timestamp.

Example Query - "what did agent X do for request Y?" maps to:

```sql
SELECT * FROM agent_runs WHERE request_id = $1 ORDER BY created_at;
```

### 3.4 Why hybrid scoring

Pure LLM scoring is unreliable for spelling variants (`"Nishaank Rawat"`
vs `"Nishaank S Rawat"` vs `"Rawat, Nishaank"`). Pure deterministic scoring
misses semantic equivalence.

- `rapidfuzz.token_set_ratio` produces a single 0.0–1.0 ratio per name
  pair.
- That ratio is sent to the scoring LLM as a _hint_ alongside the
  request, customer record, extracted fields, and forgery signals.
- The LLM produces a 0–5 score with reasoning that triangulates the
  ratio against context.

Aggregation to `overall_confidence` is a **pure-Python weighted average**
in `_aggregate_overall_confidence`. Weights live in code, not in the
prompt — auditable and tunable in the eval harness without re-prompting.

## 4. Data model

```mermaid
erDiagram
  customers ||--o{ pending_requests : has
  pending_requests ||--o{ agent_runs : audits
  customers {
    string customer_id PK
    string name
    datetime date_of_birth
    string email
    string phone
    string address
    datetime created_at
    datetime updated_at
  }
  pending_requests {
    uuid request_id PK
    string customer_id FK
    enum change_type
    json requested_value
    json extracted_value
    json confidence_card
    float overall_confidence
    text ai_summary
    enum recommended_action
    enum status
    string filenet_ref
    string checker_user
    text checker_reason
    datetime checker_decided_at
    datetime created_at
    datetime updated_at
  }
  agent_runs {
    uuid run_id PK
    uuid request_id FK
    string agent
    enum status
    json input_payload
    json output_payload
    text error
    int duration_ms
    datetime created_at
  }
```

**JSON columns** for `requested_value`, `extracted_value`,
`confidence_card`, `input_payload`, `output_payload`: the shape varies
per change-type or per agent. JSON avoids a wide, mostly-NULL relational
schema. Validation lives at the API boundary in `app.schemas`.

## 5. HITL boundary enforcement

Three layers of enforcement:

**Layer 1 — physical separation.** `app/api/rps.py` is the only file
in the codebase that contains a `customer.<field> = ...` assignment on
the `Customer` ORM model. Future contributors must edit that file to
introduce a new write path; that edit is visible in code review.

**Layer 2 — single import site.** `app/api/main.py` is the only file
that imports from `app/api/rps.py`. `grep -r "from app.api import rps"`
returns one match.

**Layer 3 — single call site.** Within `app/api/main.py`, only the
`decide` handler invokes `rps.commit_change`, and the call is gated:

```python
if body.decision == Decision.APPROVE:
    rps.commit_change(...)
```

Pydantic ensures `body.decision ∈ {APPROVE, REJECT}` (the `Decision`
enum) before the handler runs, so the gate cannot be bypassed by a
malformed input.

**Atomicity.** The customer mutation and the `pending_requests` status
flip happen in the same SQLAlchemy session and commit together:

```python
rps.commit_change(session=db, customer_id=..., ...)  # mutates customer
pending.status = RequestStatus.APPROVED              # flips status
db.commit()                                          # one transaction
```

A crash mid-handler leaves state consistent — the request remains
`AI_VERIFIED_PENDING_HUMAN`, retryable.

## 6. Sequence diagrams

### 6.1 Intake (Staff submits → AI verifies)

```mermaid
sequenceDiagram
  participant Staff
  participant Streamlit
  participant API as FastAPI
  participant FN as FileNet
  participant DB as Postgres
  participant Graph as LangGraph
  participant Claude

  Staff->>Streamlit: Fill form + upload doc
  Streamlit->>API: POST /requests (multipart)
  API->>FN: archive(bytes, ext, metadata)
  FN-->>API: filenet_ref
  API->>DB: INSERT pending_requests (PENDING_AI)
  API->>Graph: run_pipeline(state)
  Graph->>DB: SELECT customer (validation)
  Graph->>DB: INSERT agent_runs (validation, SUCCESS)
  Graph->>FN: fetch_path
  Graph->>Claude: messages.create (vision, EXTRACTION_SYSTEM)
  Claude-->>Graph: extracted_value + forgery_signals
  Graph->>DB: INSERT agent_runs (extraction, SUCCESS)
  Graph->>Claude: messages.create (text, SCORING_SYSTEM)
  Claude-->>Graph: confidence_card
  Graph->>DB: INSERT agent_runs (scoring, SUCCESS)
  Graph->>Claude: messages.create (text, SUMMARY_SYSTEM)
  Claude-->>Graph: ai_summary
  Graph->>DB: INSERT agent_runs (summary, SUCCESS)
  Graph-->>API: final_state
  API->>DB: UPDATE pending_requests (AI_VERIFIED_PENDING_HUMAN)
  API-->>Streamlit: 201 Created
  Streamlit-->>Staff: render verdict
```

### 6.2 Decision (Checker approves → mock RPS write)

```mermaid
sequenceDiagram
  participant Checker
  participant Streamlit
  participant API as FastAPI
  participant RPS as rps.commit_change
  participant DB as Postgres

  Checker->>Streamlit: review queue, pick request
  Streamlit->>API: GET /requests/{id}
  API->>DB: SELECT pending_request + agent_runs
  API-->>Streamlit: detail JSON
  Streamlit-->>Checker: render side-by-side

  Checker->>Streamlit: enter reason, click Approve
  Streamlit->>API: POST /requests/{id}/decision (APPROVE)
  API->>API: validate decision (Pydantic)
  API->>DB: SELECT pending_request
  API->>RPS: commit_change(session, customer_id, ...)
  RPS->>DB: UPDATE customers SET name = new_name
  API->>DB: UPDATE pending_requests SET status=APPROVED
  API->>DB: COMMIT (single txn)
  API-->>Streamlit: 200 OK
  Streamlit-->>Checker: success, queue refreshes
```

## 7. Component responsibility matrix

| Component               | Owns                                                                                                         | Does not own                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| Streamlit UI            | Form rendering, input hints, HTTP orchestration, document iframe embed                                       | Business logic, DB access, LLM calls                   |
| FastAPI                 | Input validation (Pydantic), pipeline orchestration, transaction boundaries, HITL gating, structured logging | Domain logic inside agents, raw LLM prompts            |
| Agents (`app.agents.*`) | Reading the document, calling Claude, scoring math, summary generation, audit row writes                     | API request shape, mock RPS writes, transaction commit |
| `app.api.rps`           | The single mock-RPS write function                                                                           | Anything else                                          |
| Postgres                | Persistence of canonical state and audit trail                                                               | Files (lives in FileNet)                               |
| FileNet (local FS)      | Archived document content + metadata sidecar                                                                 | Any structured pending-request state                   |

## 8. Future work

- **Async pipeline.** Job queue; intake returns request_id immediately.
- **Authentication and RBAC.** SSO + role-gated endpoints (Staff vs Checker)
- **Eval harness.** Golden test cases (good docs, blurry docs, wrong-name docs, off-template docs); regression-tested in CI.

- **Multi-change-type support.** Implement ADDRESS / DATE_OF_BIRTH / CONTACT_EMAIL branches in `rps.commit_change` and corresponding intake form fields.
- **Conditional LangGraph edges.** Replace in-node halt checks with LangGraph conditional edges to skip extraction / scoring / summary on validation halt.
