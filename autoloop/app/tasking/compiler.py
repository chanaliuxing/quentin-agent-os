from __future__ import annotations

from app.models import ModuleExecutionView, TaskPacket
from app.tasking.packets import build_task_packet


class TaskPacketCompiler:
    def compile_for_agent(
        self,
        *,
        run_id: str,
        phase_id: str,
        module_view: ModuleExecutionView,
        agent: str,
    ) -> TaskPacket:
        return build_task_packet(
            run_id=run_id,
            phase_id=phase_id,
            agent=agent,
            module_view=module_view,
        )
