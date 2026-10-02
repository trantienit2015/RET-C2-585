"""AgentCore Platform v1.0 - RET-C2-585 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain
complexity is encapsulated in LaborComplianceGraphNode (the `main` slot),
which wraps the inner LaborComplianceWorkflowGraph. Do NOT override
add_edges().

Backbone: initialize -> pre_process(InputValidateSchedulingDataQuery) ->
          main(GraphNode) -> post_process(OutputValidate) -> finalize

LaborComplianceGraphNode lives here (not under src/nodes/) - the PB-6
invoke-order test only discovers BaseNode subclasses under src/nodes/,
and a GraphNode's __call__ intentionally skips the standard S-2/S-4/S-3
lifecycle (gating is delegated to the inner subgraph).
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import OutputValidateNode
from src.nodes.pre_process_node import InputValidateSchedulingDataQueryNode
from src.schemas.state import State


class LaborComplianceGraphNode(GraphNode):
    """Wraps the inner labor-compliance-check/matrix/report workflow (Cat 2 composition)."""

    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template.
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any | None = None) -> None:
        super().__init__()
        self._llm = llm

    def get_subgraph(self) -> AgentBaseGraph:
        from src.graph.domain_workflow_graph import LaborComplianceWorkflowGraph

        sg = LaborComplianceWorkflowGraph(config={"llm": self._llm})
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # scheduling_data is already the complete payload the inner graph
        # needs - no multi-field envelope required.
        # Progress (non-terminal) event for the caller, emitted as the subgraph step
        # begins. Outside the Marketplace runtime this is a no-op emitter.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        emit_trace_event(
            "ret_labor_compliance_workflow_dispatched", {"correlation_id": state.get("correlation_id", "")}, state
        )
        value = state.get("scheduling_data", state.get("user_input", ""))
        return value if isinstance(value, str) else str(value)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "ret_labor_compliance_workflow_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            "compliance_matrix": sub_result.get("compliance_matrix"),
            "store_summary": sub_result.get("store_summary"),
            "formatted_report": sub_result.get("output"),
            "result": sub_result.get("output"),
            "status": sub_result.get("status"),
        }


class RETWorkforceSchedulingGapReportAgent(AgentBaseGraph):
    """RET-C2-585 - Retail Multi-Store Labor Compliance Gap Analysis Report Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "ret-c2-585"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        scheduling_connector = self.config.get("scheduling_connector")
        llm = self.config.get("llm")

        self._nodes["pre_process"] = InputValidateSchedulingDataQueryNode(scheduling_connector=scheduling_connector)
        self._nodes["main"] = LaborComplianceGraphNode(llm=llm)
        self._nodes["post_process"] = OutputValidateNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Stable alias for the standalone entry point import (src/api/server.py).
Graph = RETWorkforceSchedulingGapReportAgent
