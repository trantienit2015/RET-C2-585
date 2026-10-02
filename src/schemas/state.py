"""AgentCore Platform v1.0 - RET-C2-585 state schema.

Retail Multi-Store Labor Compliance Gap Analysis Report Agent
(DocGenerationAgent pattern). Flat TypedDict extension of AgentState
(ADR-005). Structured payloads (dict/list) are JSON-string-encoded before
being stored in state fields.
"""

import json
from typing import Any

from framework.schemas.agent_state import AgentState


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class State(AgentState):
    """Agent state for RET-C2-585.

    scheduling_data: JSON list[dict] - anonymized per-store scheduling
      records {store_id, worker_id, hours_worked, is_foreign_worker,
      night_shift_coverage_count}, fetched via the scheduling connector.
    compliance_matrix: JSON list[dict] - per-store {store_id,
      36kyotei_flags, foreign_worker_flags, night_coverage_flags,
      severity, remediation_priority}.
    store_summary: str - LLM-synthesized per-store gap narrative.
    formatted_report: str - final report (aggregate flags only, no
      individual worker identifiers).
    """

    scheduling_data: str
    compliance_matrix: str
    store_summary: str
    formatted_report: str
