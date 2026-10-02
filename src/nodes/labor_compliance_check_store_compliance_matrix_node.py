"""AgentCore Platform v1.0 - RET-C2-585 LaborComplianceCheckStoreComplianceMatrixNode (inner subgraph).

Combines LaborComplianceCheck (36協定/育成就労 rule engine) +
StoreComplianceMatrix (per-store matrix assembly + LLM-essential
narrative synthesis) per the the original draft's node flow, since both
operate on the same scheduling_data input with no branching between them.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import build_compliance_matrix, synthesize_store_summary


class LaborComplianceCheckStoreComplianceMatrixNode(FunctionNode):
    """Run the labor-compliance rule engine and build the per-store matrix + summary."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def __init__(self, llm: Any | None = None) -> None:
        super().__init__()
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # GraphNode subgraph boundary: extract_input() forwards
        # scheduling_data as the inner graph's user_input; scheduling_data
        # itself is not seeded in the fresh inner state (see
        # graphnode subgraph boundary field loss).
        scheduling_data = from_json(state.get("scheduling_data") or state.get("user_input", ""), None)

        if not isinstance(scheduling_data, list) or not scheduling_data:
            return {
                "status": AgentStatus.ERROR,
                "error_log": ["LaborComplianceCheckStoreComplianceMatrixNode: scheduling_data missing or empty"],
            }

        compliance_matrix = build_compliance_matrix(scheduling_data)
        store_summary = synthesize_store_summary(compliance_matrix, llm=self._llm)

        emit_trace_event(
            "store_compliance_matrix_built",
            {"stores": len(compliance_matrix)},
            state,
        )
        return {
            "compliance_matrix": to_json(compliance_matrix),
            "store_summary": store_summary,
            "status": AgentStatus.SUCCESS,
        }
