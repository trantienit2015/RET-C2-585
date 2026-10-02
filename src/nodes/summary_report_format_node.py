"""AgentCore Platform v1.0 - RET-C2-585 SummaryReportFormatNode (inner subgraph).

Deterministic report assembly (Tool layer, no LLM). Runs after
LaborComplianceCheckStoreComplianceMatrixNode within the SAME inner
subgraph invocation - compliance_matrix/store_summary are already in
state (no GraphNode boundary crossing between inner nodes).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json


class SummaryReportFormatNode(FunctionNode):
    """Assemble the final per-store compliance gap report."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        compliance_matrix = from_json(state.get("compliance_matrix", ""), None)
        store_summary = state.get("store_summary", "")

        if not isinstance(compliance_matrix, list):
            return {
                "status": AgentStatus.ERROR,
                "error_log": ["SummaryReportFormatNode: compliance_matrix missing or invalid"],
            }

        lines = [f"Multi-Store Labor Compliance Gap Report ({len(compliance_matrix)} store(s))", "", store_summary, ""]
        for entry in compliance_matrix:
            lines.append(
                f"- {entry.get('store_id')}: severity={entry.get('severity')}, "
                f"36kyotei={len(entry.get('36kyotei_flags', []))}, "
                f"foreign_worker={len(entry.get('foreign_worker_flags', []))}, "
                f"night_coverage={len(entry.get('night_coverage_flags', []))}, "
                f"priority={entry.get('remediation_priority')}"
            )

        emit_trace_event(
            "compliance_report_formatted",
            {"stores": len(compliance_matrix)},
            state,
        )
        return {
            "formatted_report": "\n".join(lines),
            "status": AgentStatus.SUCCESS,
        }
