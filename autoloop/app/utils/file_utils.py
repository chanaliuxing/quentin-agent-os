from pathlib import Path
from app.models import AgentRole
from app.config import settings


def get_phase_dir(phase_id: str) -> Path:
    return settings.phases_dir / phase_id


def get_task_file(phase_id: str, agent: AgentRole, module_name: str | None = None) -> Path:
    phase_dir = get_phase_dir(phase_id)
    if module_name:
        return phase_dir / "tasks" / f"{module_name}_{agent.value}.md"
    return phase_dir / "tasks" / f"{agent.value}.md"


def get_result_file(phase_id: str, agent: AgentRole, module_name: str | None = None) -> Path:
    phase_dir = get_phase_dir(phase_id)
    if module_name:
        return phase_dir / "results" / f"{module_name}_{agent.value}.md"
    return phase_dir / "results" / f"{agent.value}.md"


def get_contract_file(phase_id: str, module_name: str, contract_name: str) -> Path:
    phase_dir = get_phase_dir(phase_id)
    return phase_dir / "tasks" / "contracts" / f"{module_name}_{contract_name}.json"


def ensure_phase_dirs(phase_id: str) -> None:
    phase_dir = get_phase_dir(phase_id)
    (phase_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (phase_dir / "tasks" / "contracts").mkdir(parents=True, exist_ok=True)
    (phase_dir / "results").mkdir(parents=True, exist_ok=True)


def read_task(task_file: Path) -> str:
    if not task_file.exists():
        return ""
    return task_file.read_text()


def write_result(result_file: Path, content: str) -> None:
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(content)


def write_task(task_file: Path, content: str) -> None:
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text(content)
