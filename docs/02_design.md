# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `RETWorkforceSchedulingGapReportAgent`
- **L1 Base**: AgentBaseGraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Cat 2: outer `AgentBaseGraph` (fixed 5-node backbone) + `GraphNode` in the
`main` slot wrapping an inner `BaseGraph` (2-step linear domain workflow).

### Node Configuration (outer)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version/session_id/trust_level | - | - | InitializeNode (default) |
| pre_process | `InputValidateSchedulingDataQueryNode` — S-1/S-2 gate (worker-PII/在留カード scan) + Tool-call to the scheduling connector | `user_input` | `scheduling_data` | FunctionNode |
| main | `LaborComplianceGraphNode` — wraps inner workflow | `scheduling_data` | `compliance_matrix`, `store_summary`, `formatted_report` | GraphNode |
| post_process | `OutputValidateNode` — non-suppressible worker-PII re-check | `formatted_report` | (validated) | FunctionNode |
| finalize | response_metadata, total_time_ms | - | - | FinalizeNode (default) |

### Node Configuration (inner, per the locked node flow)

| Node | Responsibility |
|------|-----------------|
| `LaborComplianceCheckStoreComplianceMatrixNode` | Deterministic 36協定/育成就労法/night-coverage rule engine (config-driven thresholds) + per-store matrix assembly + LLM-essential per-store gap narrative synthesis (deterministic fallback when no LLM is configured) |
| `SummaryReportFormatNode` | Deterministic report assembly (Tool layer, no LLM) |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry)
                                          pre_process
```

Inner (wrapped by `main`):
```
START → labor_compliance_check_store_compliance_matrix → summary_report_format → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `scheduling_data` | str (JSON list[dict]) | anonymized per-store scheduling records (worker_id only, no name/contact) | Yes |
| `compliance_matrix` | str (JSON list[dict]) | per-store `{store_id, 36kyotei_flags, foreign_worker_flags, night_coverage_flags, severity, remediation_priority}` | Yes |
| `store_summary` | str | LLM-synthesized per-store gap narrative | Yes |
| `formatted_report` | str | final report (aggregate flags only, no individual worker identifiers) | Yes |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [x] SecurityViolationError
- [x] S-1: `required_trust_level = INTERNAL` on every node — worker
      scheduling data is internal enterprise HR data.
- [x] S-2: worker-PII/在留カード pattern detection in
      `InputValidateSchedulingDataQueryNode` — pass-through anonymized
      records (worker_id only) expected; raw PII in the query itself is
      rejected.
- [x] S-3: `_extra_security_gate_output()` — non-suppressible re-check on
      `OutputValidateNode` that the report contains no worker
      PII/在留カード pattern — aggregate per-store flags only, no
      individual worker identifiers, no raw nationality/visa data. Own-dict
      field re-check only, per the S-3 hook self-consistency rule.
- [x] S-4: `emit_trace_event()` — `ret_labor_compliance_gap_report_generated`
      and `output_validate_s3_recheck_blocked`; audit logs contain no raw
      employee payload, only report-generation metadata.

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `LaborComplianceGraphNode` wraps
  `LaborComplianceWorkflowGraph`.
- **Composition target**: inner `BaseGraph` (2-node linear domain workflow).
- **Error propagation strategy**: `propagate` (fail fast — re-raise inner
  errors as `SubgraphError`, default). No HITL in this template.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| Level 2 pattern | ChatAgent (original draft) | DocGenerationAgent | DocGenerationAgent | Correction: this is a batch-style gap-analysis report generator, not a conversation agent |
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Cat 2 fixed multi-step workflow, no autonomous loop needed |
| Composition pattern | Standalone nodes | GraphNode (subgraph) | GraphNode | Domain complexity (rule engine + matrix assembly + narrative synthesis) is encapsulated inside the inner workflow per the locked node flow |
| Compliance rule checks | LLM-based | Deterministic (Tool, config-driven rule engine) | Deterministic | Per the design decision: 36協定/育成就労 thresholds are config-driven rule checks — the LLM-essential value is the per-store contextual narrative, not the threshold logic |
| Node flow mapping | 6 separate nodes matching the original draft exactly | Combine LaborComplianceCheck+StoreComplianceMatrix (inner node 1) | Combined pair | Both operate on the same scheduling_data input with no branching/retry boundary between them |
| Extract_input envelope | Multi-field JSON envelope | Forward `scheduling_data` directly | Forward directly | `scheduling_data` is already the complete payload the inner graph needs — no independent outer-classified field is lost across the GraphNode boundary |
| Output content | Include individual worker records | Aggregate per-store flags only, non-suppressible | Aggregate-only | Per the the original draft's explicit S-3 spec: no individual worker identifiers, no raw nationality/visa data in output |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=ret`, `agent_name=ret-c2-585`), so a
secret provisioned for one path resolves identically on the other.

**Deployment-provided LLM client.** The three Azure OpenAI connection values
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — the bare resource endpoint — and
`AZURE_OPENAI_DEPLOYMENT`) are resolved through the agent's own secret provider, never from the
process environment. Both entry points build the client only when all three resolve and pass it in
as `config["llm"]`; when any is absent the key stays unset and the graph keeps its deterministic
path. The manifest declares the three secrets and the provider extra.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
