from langgraph.graph import StateGraph, END
from app.models import ProjectState
from .nodes import (
    lead_plan_node,
    dispatch_dev_node,
    wait_dev_node,
    dispatch_qa_node,
    wait_qa_node,
    lead_integrate_node,
    diagnose_phase_node,
    rollback_phase_node,
    phase_done_node,
    phase_fail_node,
)


def create_autoloop_graph() -> StateGraph:
    workflow = StateGraph(ProjectState)

    workflow.add_node("lead_plan", lead_plan_node)
    workflow.add_node("dispatch_dev", dispatch_dev_node)
    workflow.add_node("wait_dev", wait_dev_node)
    workflow.add_node("dispatch_qa", dispatch_qa_node)
    workflow.add_node("wait_qa", wait_qa_node)
    workflow.add_node("lead_integrate", lead_integrate_node)
    workflow.add_node("diagnose_phase", diagnose_phase_node)
    workflow.add_node("rollback_phase", rollback_phase_node)
    workflow.add_node("phase_done", phase_done_node)
    workflow.add_node("phase_fail", phase_fail_node)

    workflow.set_entry_point("lead_plan")

    workflow.add_edge("lead_plan", "dispatch_dev")
    workflow.add_edge("dispatch_dev", "wait_dev")

    workflow.add_conditional_edges(
        "wait_dev",
        lambda state: state.next_action,
        {
            "wait_dev": "wait_dev",
            "dispatch_qa": "dispatch_qa",
            "phase_fail": "phase_fail",
        },
    )

    workflow.add_edge("dispatch_qa", "wait_qa")

    workflow.add_conditional_edges(
        "wait_qa",
        lambda state: state.next_action,
        {
            "wait_qa": "wait_qa",
            "lead_integrate": "lead_integrate",
            "phase_fail": "phase_fail",
        },
    )

    workflow.add_conditional_edges(
        "lead_integrate",
        lambda state: state.next_action,
        {
            "phase_done": "phase_done",
            "diagnose_phase": "diagnose_phase",
            "rollback_phase": "rollback_phase",
            "phase_fail": "phase_fail",
            "lead_plan": "lead_plan",
        },
    )

    workflow.add_conditional_edges(
        "diagnose_phase",
        lambda state: state.next_action,
        {
            "rollback_phase": "rollback_phase",
            "phase_fail": "phase_fail",
        },
    )

    workflow.add_conditional_edges(
        "rollback_phase",
        lambda state: state.next_action,
        {
            "dispatch_dev": "dispatch_dev",
            "lead_plan": "lead_plan",
            "phase_fail": "phase_fail",
        },
    )

    workflow.add_edge("phase_done", END)
    workflow.add_edge("phase_fail", END)

    return workflow.compile()
