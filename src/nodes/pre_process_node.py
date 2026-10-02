"""AgentCore Platform v1.0 - RET-C2-585 InputValidateSchedulingDataQueryNode (outer pre_process).

Combines InputValidate (S-1/S-2: trust gate + worker-PII/在留カード scan)
+ SchedulingDataQuery (Tool-call to the scheduling connector) per the
the original draft's node flow, since both operate on the raw input with no
branching between them.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import has_worker_pii


class InputValidateSchedulingDataQueryNode(FunctionNode):
    """Validate the query and fetch anonymized scheduling records."""

    # Worker scheduling data is internal enterprise HR data - authenticated
    # internal callers (area supervisors/franchise operators) only.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def __init__(self, scheduling_connector: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._scheduling_connector = scheduling_connector or []

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        user_input = state.get("user_input", "")

        if not user_input or not user_input.strip():
            return {
                "status": AgentStatus.ERROR,
                "error_log": ["InputValidateSchedulingDataQueryNode: user_input is empty or missing"],
            }

        if has_worker_pii(user_input):
            return {
                "status": AgentStatus.ERROR,
                "error_log": [
                    "InputValidateSchedulingDataQueryNode: input contains worker PII/在留カード pattern - rejected (S-2)"
                ],
            }

        query = from_json(user_input, None)
        if not isinstance(query, dict) or not query.get("store_ids"):
            return {
                "status": AgentStatus.ERROR,
                "error_log": ["InputValidateSchedulingDataQueryNode: user_input must be a JSON object with store_ids"],
            }

        store_ids = set(query["store_ids"])
        scheduling_data = [r for r in self._scheduling_connector if r.get("store_id") in store_ids]

        emit_trace_event(
            "scheduling_data_selected",
            {"stores_requested": len(store_ids), "records_selected": len(scheduling_data)},
            state,
        )
        return {
            "scheduling_data": to_json(scheduling_data),
            "status": AgentStatus.SUCCESS,
        }
