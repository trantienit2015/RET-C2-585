# RET-C2-585 - Unit tests: per-node success + error/edge paths.

from framework.schemas.agent_status import AgentStatus

from src.nodes.labor_compliance_check_store_compliance_matrix_node import (
    LaborComplianceCheckStoreComplianceMatrixNode,
)
from src.nodes.post_process_node import OutputValidateNode
from src.nodes.pre_process_node import InputValidateSchedulingDataQueryNode
from src.nodes.summary_report_format_node import SummaryReportFormatNode
from src.schemas.state import from_json, to_json

CONNECTOR = [
    {"store_id": "ST-001", "worker_id": "W1", "hours_worked": 50, "is_foreign_worker": True, "night_shift_coverage_count": 1},
    {"store_id": "ST-002", "worker_id": "W2", "hours_worked": 30, "is_foreign_worker": False, "night_shift_coverage_count": 3},
]


class TestInputValidateSchedulingDataQueryNode:
    def test_success(self):
        state = {"user_input": to_json({"store_ids": ["ST-001"]})}
        r = InputValidateSchedulingDataQueryNode(scheduling_connector=CONNECTOR).execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        data = from_json(r["scheduling_data"], [])
        assert len(data) == 1

    def test_empty_input_error(self):
        assert InputValidateSchedulingDataQueryNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_worker_pii_rejected(self):
        state = {"user_input": "worker email reviewer@example.com in payload"}
        assert InputValidateSchedulingDataQueryNode().execute(state)["status"] == AgentStatus.ERROR

    def test_not_json_object_error(self):
        assert InputValidateSchedulingDataQueryNode().execute({"user_input": "not json"})["status"] == AgentStatus.ERROR


class TestLaborComplianceCheckStoreComplianceMatrixNode:
    def test_success_high_severity_store(self):
        state = {"scheduling_data": to_json([CONNECTOR[0]])}
        r = LaborComplianceCheckStoreComplianceMatrixNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        matrix = from_json(r["compliance_matrix"], [])
        assert matrix[0]["severity"] == "H"

    def test_success_compliant_store(self):
        state = {"scheduling_data": to_json([CONNECTOR[1]])}
        r = LaborComplianceCheckStoreComplianceMatrixNode().execute(state)
        matrix = from_json(r["compliance_matrix"], [])
        assert matrix[0]["severity"] == "L"

    def test_missing_scheduling_data_error(self):
        assert LaborComplianceCheckStoreComplianceMatrixNode().execute({"scheduling_data": ""})["status"] == AgentStatus.ERROR


class TestSummaryReportFormatNode:
    def test_success(self):
        matrix = [{"store_id": "ST-001", "36kyotei_flags": [], "foreign_worker_flags": [], "night_coverage_flags": [], "severity": "L", "remediation_priority": "none"}]
        state = {"compliance_matrix": to_json(matrix), "store_summary": "All stores compliant."}
        r = SummaryReportFormatNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert "ST-001" in r["formatted_report"]

    def test_missing_matrix_error(self):
        assert SummaryReportFormatNode().execute({"compliance_matrix": ""})["status"] == AgentStatus.ERROR


class TestOutputValidateNode:
    def test_success_compliant_report(self):
        state = {"formatted_report": "Multi-Store Labor Compliance Gap Report (1 store(s))"}
        r = OutputValidateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS

    def test_worker_pii_error(self):
        state = {"formatted_report": "Contact reviewer@example.com"}
        assert OutputValidateNode().execute(state)["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_worker_pii(self):
        bad_state = {"formatted_report": "reviewer@example.com"}
        out = OutputValidateNode()._extra_security_gate_output(bad_state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_passthrough_compliant_report(self):
        good_state = {"formatted_report": "Clean aggregate report."}
        assert OutputValidateNode()._extra_security_gate_output(good_state) is good_state
