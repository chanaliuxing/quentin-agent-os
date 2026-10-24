# meta_agent/blueprint/self_update_v2.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import datetime as dt
import json
import shutil
import os

from meta_agent.blueprint.patch_types import BlueprintPatch
from meta_agent.llm.cli_clients import CLIModelClient, make_codex_cli_client
from quentin.traces.core import JsonlTraceRecorder
from meta_agent.blueprint.version_store import BlueprintVersionStore

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class BlueprintSelfUpdateConfig:
    blueprint_path: Path = Path("blueprint/blueprint.md")
    patch_log_path: Path = Path("data/blueprint/patches.jsonl")
    backup_dir: Path = Path("data/blueprint/backups")
    require_llm_guard: bool = True
    allow_auto_apply_low_risk: bool = True
    enable_versioning: bool = True
    versions_root_dir: Path = Path("data/blueprint/versions")

class BlueprintSelfUpdateEngineV2:
    def __init__(self, config: Optional[BlueprintSelfUpdateConfig] = None, guard_llm: Optional[CLIModelClient] = None):
        self.config = config or BlueprintSelfUpdateConfig()
        self.guard_llm = guard_llm or make_codex_cli_client()
        self.config.backup_dir.mkdir(parents=True, exist_ok=True)
        self.config.patch_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._version_store = BlueprintVersionStore(self.config.versions_root_dir) if self.config.enable_versioning else None

    def apply_patch(self, patch: BlueprintPatch, auto: bool = True) -> BlueprintPatch:
        trace.record_event(event_type="blueprint_patch_attempt", trace_id=patch.id, payload={"patch_id": patch.id, "auto": auto})
        
        if auto and not self._can_auto_apply(patch):
            patch.status = "rejected"
        elif self.config.require_llm_guard and not self._run_llm_guard(patch):
            patch.status = "rejected"
        else:
            old_text = self.config.blueprint_path.read_text(encoding="utf-8") if self.config.blueprint_path.exists() else ""
            self._backup_blueprint()
            self._apply_to_file(patch)
            new_text = self.config.blueprint_path.read_text(encoding="utf-8")
            
            if self._version_store:
                try:
                    self._version_store.create_version_from_patch(patch=patch, old_text=old_text, new_text=new_text)
                except Exception as e:
                    trace.record_event(event_type="blueprint_version_create_error", trace_id=patch.id, payload={"patch_id": patch.id, "error": repr(e)})
            
            patch.status = "applied"

        self._log_patch(patch)
        trace.record_event(event_type=f"blueprint_patch_{patch.status}", trace_id=patch.id, payload={"patch_id": patch.id})
        return patch

    def _can_auto_apply(self, patch: BlueprintPatch) -> bool:
        return self.config.allow_auto_apply_low_risk and patch.risk_level == "low"

    def _run_llm_guard(self, patch: BlueprintPatch) -> bool:
        """
        Guardrail for blueprint mutations.

        Policy:
        - If guard client is a stub/unavailable, deny (unless explicitly overridden).
        - Ask the CLI model for a JSON verdict; accept only explicit approvals.
        """
        allow_stub = os.environ.get("BLUEPRINT_LLM_GUARD_ALLOW_STUB", "").strip().lower() in ("1", "true", "yes", "on")
        if type(self.guard_llm).__name__ == "StubCLIModelClient" and not allow_stub:
            trace.record_event(event_type="blueprint_llm_guard_unavailable", trace_id=patch.id, payload={"decision": "deny"})
            return False

        system = "You are a strict governance guard. Decide if the blueprint text patch is safe to apply."
        user = json.dumps(
            {
                "patch": patch.__dict__,
                "policy": {
                    "allow_only_low_risk_auto": True,
                    "deny_if_secret_like": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        try:
            raw = self.guard_llm.generate(system=system, user=user)
        except Exception as e:  # noqa: BLE001
            trace.record_event(event_type="blueprint_llm_guard_error", trace_id=patch.id, payload={"error": repr(e)})
            return False

        # Prefer JSON outputs; allow simple "approve"/"deny" strings.
        verdict = None
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                verdict = obj.get("verdict") or obj.get("decision") or obj.get("allow")
        except Exception:
            verdict = raw.strip().lower()

        if isinstance(verdict, bool):
            return verdict
        if isinstance(verdict, str):
            v = verdict.strip().lower()
            if v in ("approve", "approved", "allow", "allowed", "yes", "true"):
                return True
            if v in ("deny", "denied", "reject", "rejected", "no", "false"):
                return False
        return False

    def _backup_blueprint(self) -> None:
        if self.config.blueprint_path.exists():
            dest = self.config.backup_dir / f"{self.config.blueprint_path.name}.{now_utc().strftime('%Y%m%dT%H%M%S')}.bak"
            shutil.copy2(self.config.blueprint_path, dest)

    def _apply_to_file(self, patch: BlueprintPatch) -> None:
        text = self.config.blueprint_path.read_text(encoding="utf-8") if self.config.blueprint_path.exists() else ""
        new_text = self._apply_text_patch(text, patch)
        self.config.blueprint_path.write_text(new_text, encoding="utf-8")

    def _apply_text_patch(self, text: str, patch: BlueprintPatch) -> str:
        # Simplified logic
        return f"{text.rstrip()}\n\n{patch.new_content.strip()}\n"

    def _log_patch(self, patch: BlueprintPatch) -> None:
        rec = {"ts": now_iso(), "patch": patch.__dict__}
        with self.config.patch_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
