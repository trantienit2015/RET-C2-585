"""AgentCore Platform v1.0 - RET-C2-585 inner domain workflow graph.

Cat 2 inner graph: deterministic 36協定/育成就労/night-coverage rule
engine + per-store matrix assembly + LLM-essential summary synthesis
(Tool + LLM) -> deterministic report assembly. Instantiated by
LaborComplianceGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR):
    START -> labor_compliance_check_store_compliance_matrix -> summary_report_format -> END
"""

from typing import Any

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from langgraph.graph import END, START

from src.nodes.labor_compliance_check_store_compliance_matrix_node import (
    LaborComplianceCheckStoreComplianceMatrixNode,
)
from src.nodes.summary_report_format_node import SummaryReportFormatNode
from src.schemas.state import State


class LaborComplianceWorkflowGraph(BaseGraph):
    """Inner graph for the RET-C2-585 labor compliance gap analysis workflow."""

    @property
    def name(self) -> str:
        return "ret-labor-compliance-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config: llm is optional (deterministic fallback).
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract.
        llm = self.config.get("llm")

        self._nodes["labor_compliance_check_store_compliance_matrix"] = LaborComplianceCheckStoreComplianceMatrixNode(
            llm=llm
        )
        self._nodes["summary_report_format"] = SummaryReportFormatNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "labor_compliance_check_store_compliance_matrix")
        self._sg.add_conditional_edges(
            "labor_compliance_check_store_compliance_matrix",
            lambda s: END if self._is_error(s) else "summary_report_format",
            {"summary_report_format": "summary_report_format", END: END},
        )
        self._sg.add_edge("summary_report_format", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        return state.get("status") in (AgentStatus.ERROR, AgentStatus.ERROR.value)

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "summary_report_format"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "compliance_matrix": state.get("compliance_matrix"),
            "store_summary": state.get("store_summary"),
            "output": state.get("formatted_report"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
