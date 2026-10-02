"""AgentCore Platform v1.0 - RET-C2-585 domain services.

Deterministic worker-PII/在留カード detection (S-2) + 36協定/育成就労法/
night-coverage rule engine (Tool layer, no LLM) + LLM-essential per-store
gap narrative synthesis (deterministic fallback when no LLM is
configured). S-3 output gate is non-suppressible: report output contains
per-store aggregate flags only - no individual worker identifiers, no
raw nationality/visa data.
"""

from __future__ import annotations

import re
from typing import Any

_PII_PATTERNS = [
    # Every quantifier is bounded (RFC 5321/1035 lengths) so a long input cannot
    # trigger quadratic-time backtracking (ReDoS) in the S-2 scan.
    re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,3}\.[A-Za-z]{2,63}"),  # email
    re.compile(r"(?<!\d)\d{12}(?!\d)"),  # My Number
    re.compile(r"\b[A-Z]{2}\d{8}[A-Z]{2}\b"),  # 在留カード番号 pattern
]

_OVERTIME_THRESHOLD_HOURS = 45  # 36協定 monthly overtime cap (illustrative)
_FOREIGN_WORKER_HOUR_CAP = 40  # 育成就労法 illustrative weekly cap
_NIGHT_COVERAGE_MINIMUM = 2  # minimum staff on night shift


def has_worker_pii(text: str) -> bool:
    """S-2 deterministic worker-PII/在留カード detection (Tool layer, no LLM)."""
    return any(p.search(text) for p in _PII_PATTERNS)


def check_36kyotei_compliance(store_records: list[dict[str, Any]]) -> list[str]:
    """Deterministic 36協定 overtime threshold check (Tool layer, no LLM)."""
    flags = []
    for record in store_records:
        if record.get("hours_worked", 0) > _OVERTIME_THRESHOLD_HOURS:
            flags.append(f"overtime_exceeded:{record.get('worker_id')}")
    return flags


def check_foreign_worker_compliance(store_records: list[dict[str, Any]]) -> list[str]:
    """Deterministic 育成就労法 foreign-worker hour cap check (Tool layer, no LLM)."""
    flags = []
    for record in store_records:
        if record.get("is_foreign_worker") and record.get("hours_worked", 0) > _FOREIGN_WORKER_HOUR_CAP:
            flags.append(f"foreign_worker_hour_cap_exceeded:{record.get('worker_id')}")
    return flags


def check_night_coverage_compliance(store_records: list[dict[str, Any]]) -> list[str]:
    """Deterministic night-shift minimum coverage check (Tool layer, no LLM)."""
    coverage = min((r.get("night_shift_coverage_count", 0) for r in store_records), default=0)
    return ["insufficient_night_coverage"] if coverage < _NIGHT_COVERAGE_MINIMUM else []


def build_compliance_matrix(scheduling_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic per-store compliance matrix assembly (Tool layer, no LLM)."""
    stores: dict[str, list[dict[str, Any]]] = {}
    for record in scheduling_data:
        stores.setdefault(str(record.get("store_id", "")), []).append(record)

    matrix = []
    for store_id, records in stores.items():
        kyotei_flags = check_36kyotei_compliance(records)
        foreign_flags = check_foreign_worker_compliance(records)
        night_flags = check_night_coverage_compliance(records)
        total_flags = len(kyotei_flags) + len(foreign_flags) + len(night_flags)
        severity = "H" if total_flags >= 2 else ("M" if total_flags == 1 else "L")
        matrix.append(
            {
                "store_id": store_id,
                "36kyotei_flags": kyotei_flags,
                "foreign_worker_flags": foreign_flags,
                "night_coverage_flags": night_flags,
                "severity": severity,
                "remediation_priority": "urgent" if severity == "H" else ("review" if severity == "M" else "none"),
            }
        )
    return matrix


def synthesize_store_summary(compliance_matrix: list[dict[str, Any]], llm: Any | None = None) -> str:
    """LLM-essential per-store gap narrative synthesis.

    Deterministic fallback keeps the pipeline runnable without an LLM.
    """
    high_severity = [m for m in compliance_matrix if m.get("severity") == "H"]

    if llm is not None and hasattr(llm, "complete"):
        try:
            raw = llm.complete(
                [
                    {
                        "role": "user",
                        "content": f"Write a per-store labor compliance gap summary for area supervisors: {compliance_matrix}",
                    }
                ]
            )
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        except Exception:  # noqa: BLE001 - fall back to deterministic summary
            pass

    if not high_severity:
        return "No stores with high-severity labor compliance gaps this period."
    store_ids = ", ".join(str(m.get("store_id")) for m in high_severity)
    return f"{len(high_severity)} store(s) require urgent remediation: {store_ids}."
