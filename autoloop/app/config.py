from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_root: Path = Field(default_factory=lambda: Path.cwd())
    autoloop_data_dir: str = "runtime"
    autoloop_phases_dir: str = "phases"
    autoloop_worktrees_dir: str = "worktrees"

    openai_api_key: str = ""
    deepseek_api_key: str = ""
    llm_provider: Literal["openai", "deepseek"] = "openai"
    llm_model: str = "gpt-4o"
    execution_profile: Literal["dev", "prod"] = "dev"

    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "autoloop-tasks"
    temporal_mock_mode: bool = True

    agent_runner_type: Literal["codex", "gemini", "claude", "mock"] = "codex"
    codex_session_id: str = ""
    agent_specs_json: str = ""
    gemini_session_id: str = ""
    claude_session_id: str = ""
    agent_timeout_seconds: int = 1800
    agent_total_timeout_seconds: int = 420
    planner_min_window_seconds: int = 120
    reviewer_min_window_seconds: int = 120
    agent_max_retries: int = 2
    codex_agent_max_retries: int = 0
    contract_repair_max_attempts: int = 2
    codex_resume_enabled: bool = True
    codex_ephemeral_fallback_enabled: bool = True
    codex_prefer_ephemeral: bool = False
    codex_probe_enabled: bool = True
    codex_probe_timeout_seconds: int = 20
    codex_resume_probe_timeout_seconds: int = 30
    codex_timeout_profile: Literal["codex_fast", "codex_balanced", "codex_debug", "custom"] = "codex_balanced"
    codex_fast_attempt_timeout_seconds: int = 45
    codex_fast_total_timeout_seconds: int = 180
    codex_balanced_attempt_timeout_seconds: int = 90
    codex_balanced_total_timeout_seconds: int = 420
    codex_debug_attempt_timeout_seconds: int = 120
    codex_debug_total_timeout_seconds: int = 600
    codex_attempt_timeout_seconds: int = 90
    codex_fail_on_state_db_warning: bool = False

    git_author_name: str = "AutoLoop"
    git_author_email: str = "autoloop@example.com"
    git_overlap_threshold: int = 2
    git_auto_resolve_conflicts: bool = False

    max_review_loops_per_module: int = 2
    max_planner_reviewer_loops: int = 3
    wait_node_max_cycles: int = 2

    otel_enabled: bool = True
    otel_exporter: Literal["console", "file", "otlp"] = "console"
    otel_endpoint: str = "http://localhost:4317"
    otel_log_level: str = "INFO"
    otel_service_name: str = "autoloop"

    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    gate_compile_command: str = "python -m compileall app"
    gate_unit_test_command: str = "python -m pytest tests/unit -q"
    gate_integration_test_command: str = "python -m pytest tests/integration -q"
    gate_regression_test_command: str = "python -m pytest tests -q"
    gate_static_scan_command: str = "python -m pytest tests/unit/test_models.py -q"
    gate_benchmark_command: str = ""
    auto_review_enabled: bool = True
    auto_review_min_confidence: float = 0.85
    auto_review_max_auto_resumes: int = 1
    auto_review_profile: Literal["normal", "strict"] = "normal"
    governance_review_enabled: bool = True
    governance_review_auto_resume: bool = True
    recovery_safe_mode: Literal["policy", "shadow", "canary", "full"] = "policy"

    @property
    def runtime_dir(self) -> Path:
        return self.project_root / self.autoloop_data_dir

    @property
    def phases_dir(self) -> Path:
        return self.project_root / self.autoloop_phases_dir

    @property
    def worktrees_dir(self) -> Path:
        return self.project_root / self.autoloop_worktrees_dir

    @property
    def hooks_dir(self) -> Path:
        return self.runtime_dir / "hooks"

    @property
    def logs_dir(self) -> Path:
        return self.runtime_dir / "logs"

    @property
    def pids_dir(self) -> Path:
        return self.runtime_dir / "pids"

    def ensure_dirs(self) -> None:
        for dir_path in [
            self.runtime_dir,
            self.phases_dir,
            self.worktrees_dir,
            self.hooks_dir,
            self.logs_dir,
            self.pids_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def apply_codex_timeout_profile(self) -> None:
        profile = str(self.codex_timeout_profile).strip().lower()
        if profile == "custom":
            return
        mapping = {
            "codex_fast": (
                self.codex_fast_attempt_timeout_seconds,
                self.codex_fast_total_timeout_seconds,
            ),
            "codex_balanced": (
                self.codex_balanced_attempt_timeout_seconds,
                self.codex_balanced_total_timeout_seconds,
            ),
            "codex_debug": (
                self.codex_debug_attempt_timeout_seconds,
                self.codex_debug_total_timeout_seconds,
            ),
        }
        selected = mapping.get(profile)
        if not selected:
            return
        attempt_timeout, total_timeout = selected
        self.codex_attempt_timeout_seconds = max(1, int(attempt_timeout))
        self.agent_total_timeout_seconds = max(1, int(total_timeout))


settings = Settings()
