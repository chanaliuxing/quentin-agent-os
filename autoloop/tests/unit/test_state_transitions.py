from app.models import ProjectState


def test_valid_transition_is_accepted():
    state = ProjectState(project_id="p1", prd_path="prd.md", next_action="lead_plan")
    target = state.set_next_action("dispatch_dev", reason="test")
    assert target == "dispatch_dev"
    assert state.next_action == "dispatch_dev"
    assert state.transition_history[-1].accepted is True


def test_invalid_transition_is_rejected_to_fallback():
    state = ProjectState(project_id="p1", prd_path="prd.md", next_action="lead_plan")
    target = state.set_next_action("lead_integrate", reason="invalid")
    assert target == "phase_fail"
    assert state.next_action == "phase_fail"
    assert state.transition_history[-1].accepted is False


def test_replay_transitions():
    state = ProjectState(project_id="p1", prd_path="prd.md", next_action="lead_plan")
    state.set_next_action("dispatch_dev", reason="a")
    state.set_next_action("wait_dev", reason="b")
    state.set_next_action("phase_fail", reason="c")
    assert state.replay_transitions() == "phase_fail"
