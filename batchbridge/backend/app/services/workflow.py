from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import AGENT_RUNNERS
from app.services.mcp_client import EvidenceMCPClient

AgentType = Literal["triage", "traceability", "escalation"]


class InvestigationState(TypedDict, total=False):
    case_id: str
    agent_type: AgentType
    proposal: dict[str, Any]
    human_decision: dict[str, Any]


async def run_selected_agent(state: InvestigationState) -> InvestigationState:
    agent_type = state["agent_type"]
    runner = AGENT_RUNNERS.get(agent_type)
    if runner is None:
        raise ValueError(f"Unknown agent type: {agent_type}")
    client = EvidenceMCPClient()
    async with client.session() as session:
        proposal = await runner(client, session, state["case_id"])
    return {"proposal": proposal}


def human_gate(state: InvestigationState) -> InvestigationState:
    # Pause the graph until an authorized reviewer records a decision.
    decision = interrupt(
        {
            "message": f"Human approval is required for the {state['agent_type']} proposal.",
            "agent_type": state["agent_type"],
            "proposal": state["proposal"],
        }
    )
    return {"human_decision": decision}


def build_investigation_graph():
    builder = StateGraph(InvestigationState)
    builder.add_node("run_selected_agent", run_selected_agent)
    builder.add_node("human_gate", human_gate)
    builder.add_edge(START, "run_selected_agent")
    builder.add_edge("run_selected_agent", "human_gate")
    builder.add_edge("human_gate", END)
    return builder.compile(checkpointer=InMemorySaver())


investigation_graph = build_investigation_graph()
