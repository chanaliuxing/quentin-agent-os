from typing import List, Dict, Any

from meta_agent.council import CouncilManager, CouncilConfig


class TaskCouncil:
    """
    Lightweight council gate for remediation tasks.
    Uses CouncilManager to approve/reject tasks; falls back to auto-approve on errors.
    """

    def __init__(self, max_rounds: int = 1):
        self.council = CouncilManager(config=CouncilConfig(max_rounds=max_rounds))

    def review(self, tasks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        approved = []
        rejected = []
        needs_info = []
        for task in tasks:
            try:
                question = f"Should we approve remediation task {task.get('req_id')}? Type: {task.get('task_type')}"
                context = {
                    "task": task,
                    "recommendation": task.get("recommendation"),
                    "missing_items": task.get("missing_items", []),
                }
                outcome = self.council.run(question, context=context)
                verdict = outcome.final_output.verdict
                if verdict == "approve":
                    approved.append(task)
                elif verdict == "revise":
                    needs_info.append(task)
                else:
                    rejected.append(task)
            except Exception:
                approved.append(task)  # fail-open to avoid blocking
        return {"approved": approved, "rejected": rejected, "needs_info": needs_info}
