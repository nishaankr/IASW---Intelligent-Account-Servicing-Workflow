"""LangGraph wiring for the IASW pipeline.

The graph is linear:
    START - validation - extraction - scoring - summary - END

Validation may set state.halt = "CUSTOMER_NOT_FOUND"
We use linear edges + in-node halt checks rather than LangGraph conditional edges because the linear shape reads more clearlyand works for our scope
We can swap to conditional edges later if the graph grows more complex branching

The graph is compiled once at module import — StateGraph.compile() runs at startup, not per request.

Use:
    from app.agents.graph import run_pipeline
    final_state = run_pipeline(initial_state)
"""

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    extraction_node,
    scoring_node,
    summary_node,
    validation_node,
)
from app.agents.state import AgentState
from app.observability import get_logger

log = get_logger(__name__)


def _build_graph():
    """Construct and compile the IASW pipeline graph."""
    graph = StateGraph(AgentState)

    # Register each agent function as a node. The string name is what shows up in logs
    graph.add_node("validation", validation_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("scoring", scoring_node)
    graph.add_node("summary", summary_node)

    # Linear flow: each node feeds straight into the next. START / END are LangGraph nodes for the entry and exit of the graph.
    graph.add_edge(START, "validation")
    graph.add_edge("validation", "extraction")
    graph.add_edge("extraction", "scoring")
    graph.add_edge("scoring", "summary")
    graph.add_edge("summary", END)

    return graph.compile()


# Module-level compiled graph.
_compiled = _build_graph()


def run_pipeline(initial_state: AgentState) -> AgentState:
    """Execute the agent pipeline and return the final state.

    This function is intentionally not allowed to call PendingRequest table

    The API layer owns writing to trhe RPS, which keeps the HITL context safe

    Audit rows are still written by each node via the `_agent_run` contextmanager
    """
    state = {**initial_state}

    state.setdefault("errors", [])

    log.info("pipeline_start", request_id=state.get("request_id"))
    final_state = _compiled.invoke(state)
    log.info(
        "pipeline_complete",
        request_id=state.get("request_id"),
        halt=final_state.get("halt"),
        overall_confidence=final_state.get("overall_confidence"),
        recommended_action=final_state.get("recommended_action"),
    )
    return final_state


def render_mermaid() -> str:
#Return the compiled graph as a Mermaid diagram string.


    return _compiled.get_graph().draw_mermaid()