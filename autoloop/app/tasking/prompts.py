from __future__ import annotations

from pathlib import Path

from app.models import PromptPacket, TaskPacket


class PromptRenderer:
    def __init__(self, template_path: Path | None = None) -> None:
        self.template_path = template_path or (
            Path(__file__).resolve().parents[2] / "templates" / "tasks" / "task_packet.md"
        )

    def render_markdown(self, packet: TaskPacket) -> str:
        sections = [
            "# Task Packet",
            "",
            "## Packet Header",
            f"- `task_id`: `{packet.task_id}`",
            f"- `run_id`: `{packet.run_id}`",
            f"- `phase_id`: `{packet.phase_id}`",
            f"- `module_id`: `{packet.module_id}`",
            f"- `agent`: `{packet.agent}`",
            "",
            "## Source Of Truth References",
            *[f"- `{ref}`" for ref in packet.sor_refs],
            "",
            "## Inputs",
            *[f"- `{artifact_id}`" for artifact_id in packet.input_artifact_ids],
            "",
            "## Writable Scope",
            *[f"- `{path}`" for path in packet.writable_paths],
            "",
            "## Expected Output Contract",
            f"- `contract`: `{packet.expected_output_contract}`",
            "",
            "## Gate Expectations",
            *[f"- `{gate}`" for gate in packet.gate_expectations],
            "",
            "## Execution Rules",
            "- Only modify files inside the writable scope.",
            "- Treat Source-of-Truth references as authoritative.",
            "- Write structured result output that can be validated against the result packet schema.",
            "- Record blockers with explicit artifact or gate references.",
        ]
        return "\n".join(sections)

    def render_system_prompt(self, packet: TaskPacket) -> str:
        return (
            f"You are the {packet.agent} agent for module {packet.module_id}. "
            f"Only modify declared writable paths and treat SoR references as authoritative."
        )

    def build_prompt_packet(self, packet: TaskPacket) -> PromptPacket:
        markdown = self.render_markdown(packet)
        return PromptPacket(
            prompt_id=f"prompt_{packet.task_id}",
            task_id=packet.task_id,
            run_id=packet.run_id,
            phase_id=packet.phase_id,
            module_id=packet.module_id,
            agent=packet.agent,
            system_prompt=self.render_system_prompt(packet),
            user_prompt=markdown,
            rendered_task_markdown=markdown,
        )
