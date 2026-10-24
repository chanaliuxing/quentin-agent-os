from abc import ABC, abstractmethod
from typing import Dict, Any
from quentin.tools.manager import ToolManager


class DomainAdapter(ABC):
    """
    所有领域适配器的抽象基类：
    - 把「抽象 task」变成领域内可执行的步骤
    - 注册领域专有工具 / skill
    """

    name: str

    @abstractmethod
    def register_tools(self, tool_manager: ToolManager) -> None:
        """
        在 ToolManager 里注册本领域的工具。
        """
        ...

    @abstractmethod
    async def normalize_task(self, raw_task: Dict[str, Any]) -> Dict[str, Any]:
        """
        把外部传进来的任务，转成标准 Task（含 domain/goal 等）。
        """
        ...
