"""AgentCore Platform v1.0 - RET-C2-585 OutputValidateNode (outer post_process slot).

S-3 output gate: non-suppressible re-check that the report contains no
individual worker identifiers or raw nationality/visa data (aggregate
flags only). Own-dict field re-check only (S-3 self-consistency rule -
s3 hook cross state recheck fragile).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import has_worker_pii


class OutputValidateNode(FunctionNode):
    """Validate the report contains no worker PII - aggregate flags only."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        formatted_report = state.get("formatted_report", "")

        if has_worker_pii(formatted_report):
            return {
                "status": AgentStatus.ERROR,
                "error_log": ["OutputValidateNode: report contains worker PII/在留カード pattern"],
            }

        # S-4: audit store_id + compliance_check_type only, never raw
        # employee payload.
        emit_trace_event("ret_labor_compliance_gap_report_generated", {}, state)

        return {
            "formatted_output": formatted_report,
            "status": AgentStatus.SUCCESS,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Non-suppressible re-check on the output dict's own field."""
        formatted_report = state.get("formatted_report", "")
        if has_worker_pii(formatted_report):
            emit_trace_event("output_validate_s3_recheck_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR,
                "error_log": ["OutputValidateNode: S-3 re-check blocked a report containing worker PII"],
            }
        return state
