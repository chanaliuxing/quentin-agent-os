from typing import Dict, Any
from quentin.domain.base import DomainAdapter


class DesktopAdapter(DomainAdapter):
    name = "desktop"

    def register_tools(self, tool_manager):
        # 示例：注册一个假工具
        from quentin.mutable.skills.common_text_tools import simple_summarizer

        tool_manager.register("DESKTOP_SUMMARIZE", lambda params: simple_summarizer(params))

    async def normalize_task(self, raw_task: Dict[str, Any]) -> Dict[str, Any]:
        """
        raw_task 示例：
        {
          "goal": "Open browser and search 'Project Quentin'",
          "app": "chrome"
        }
        转成 Orchestrator 所需的标准格式。
        """
        return {
            "task_id": raw_task.get("task_id", "desktop-task"),
            "domain": "desktop",
            "goal": raw_task["goal"],
            "meta": {"app": raw_task.get("app", "chrome")},
        }
