# RET-C2-585 — Test Specification

## Test Strategy

Deterministic-core: no LLM required, full suite runs offline. Store
summary synthesis accepts an optional `llm` client and falls back to
deterministic reasoning when absent.

## Unit Tests (`tests/unit/test_nodes.py`)

| Node | Cases |
|---|---|
| InputValidateSchedulingDataQueryNode | success (scheduling data fetched for requested stores); empty user_input→ERROR; worker-PII pattern present→ERROR (S-2); not a JSON object with store_ids→ERROR |
| LaborComplianceCheckStoreComplianceMatrixNode | success (high-severity store with multiple flags); success (compliant store, low severity); missing scheduling_data→ERROR |
| SummaryReportFormatNode | success (report includes per-store lines); missing compliance_matrix→ERROR |
| OutputValidateNode | success (compliant report); worker-PII present→ERROR (non-suppressible hook) |

## Integration Tests (`tests/integration/test_graph.py`)

| ID | Test | Expected |
|---|---|---|
| I-1 | scheduling data with an overtime + foreign-worker violation | pipeline completes (≥4 nodes); report flags high severity |
| I-2 | scheduling data fully compliant | pipeline completes; report shows low severity |
| I-3 | empty user_input | ERROR |
| I-4 | input containing a 在留カード pattern | ERROR (S-2) |

> Per the S-2 gate's effect on the success path, integration tests
> assert pipeline-completion invariants rather than an exact terminal status
> for success cases — unit tests already pin the success-path logic
> deterministically.

## Proof-of-Boundary Tests (`tests/proof_of_boundary/`)

| PB-ID | Boundary | Test | Expected Result |
|-------|----------|------|----------------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass |
| PB-6 | Invoke execution order | S-1 → node_start → S-2 → execute → S-3 → node_complete | Order verified |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result |
|-------|------|-------|----------------|
| BL-01 | 36協定 overtime flag | worker record with hours_worked > 45 | overtime_exceeded flag present |
| BL-02 | 育成就労法 foreign-worker flag | foreign worker with hours_worked > 40 | foreign_worker_hour_cap_exceeded flag present |
| BL-03 | night-coverage flag | store with night_shift_coverage_count < 2 | insufficient_night_coverage flag present |
| BL-04 | severity escalation | store with 2+ total flags | severity=H |

## Non-suppressible output tests (critical)

- `formatted_report` must never contain worker PII or 在留カード patterns
  — aggregate per-store flags only (unit + I-1/I-2 + I-4).
- The post_process S-3 hook re-checks `formatted_report`'s own field only
  (S-3 hook self-consistency rule) — never cross-references separate
  state fields read independently.

## Test Execution Summary
- Execution date: 2026-07-08
- Total tests: see CI `run-tests` job output
- Coverage: deterministic-core, no LLM dependency

## 1. Deployment path tests

### TC-DEP-01 Marketplace entry point identity — `tests/unit/test_cli_entry_point.py`

| Case | Expected |
|---|---|
| Identity is concrete | `agent_name` / `namespace` are non-empty and not the runner default |
| Identity matches the HTTP entry point | the values equal what `src/api/server.py` passes to `secrets_factory`; where that entry point provisions no secrets, they equal the manifest `namespace` and the lower-cased template id |
| The runner call uses the constants | `run_agent_marketplace` is called with the module constants, not inline literals |

### TC-DEP-02 Standalone entry point boundary — `tests/proof_of_boundary/test_server_llm_injection.py`

| Case | Expected |
|---|---|
| Boots with no credential provisioned | the module imports and the app/agent objects are constructed |
| External bearer never reaches the internal level | resolves to the verified-external level |
| Staging runner credential reaches the internal level | resolves to the internal level |
| Wrong or missing bearer while auth is enabled | rejected with 401 |
