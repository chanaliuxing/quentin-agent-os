from app.models import AgentRole, AgentStatus
from app.runners.base import AgentRunResult
from app.temporal import activities


def test_infer_failure_type_subprocess_nonzero_exit():
    result = AgentRunResult(status=AgentStatus.FAILED, exit_code=2, stdout="", stderr="", error_message="boom")
    failure_type = activities._infer_failure_type(
        agent_role=AgentRole.DEV,
        error_message="process failed",
        result=result,
        output_text='{"not":"matching_contract"}',
        contract_valid=True,
        contract_error="",
    )
    assert failure_type == "AGENT_SUBPROCESS_NONZERO_EXIT"


def test_infer_failure_type_output_missing():
    failure_type = activities._infer_failure_type(
        agent_role=AgentRole.QA,
        error_message="",
        result=None,
        output_text="",
        contract_valid=None,
        contract_error="",
    )
    assert failure_type == "AGENT_OUTPUT_MISSING"


def test_infer_failure_type_contract_violation():
    failure_type = activities._infer_failure_type(
        agent_role=AgentRole.DEV,
        error_message="contract validation failed",
        output_text='{"status":"failed"}',
        contract_valid=False,
        contract_error="schema mismatch",
    )
    assert failure_type == "AGENT_CONTRACT_VIOLATION"


def test_infer_failure_type_parse_failed():
    failure_type = activities._infer_failure_type(
        agent_role=AgentRole.REVIEWER,
        error_message="runner returned markdown",
        output_text="not-json-output",
        contract_valid=True,
        contract_error="",
    )
    assert failure_type == "AGENT_RESULT_PARSE_FAILED"


def test_infer_failure_type_runner_session_degraded():
    failure_type = activities._infer_failure_type(
        agent_role=AgentRole.PLANNER,
        error_message="state db migration warning and falling_back",
    )
    assert failure_type == "AGENT_RUNNER_SESSION_DEGRADED"
