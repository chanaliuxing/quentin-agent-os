from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import signal
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentConfig:
    name: str
    role: str
    session_id: str | None
    keywords: list[str]
    workdir: str | None = None
    model: str | None = None
    keep_session: bool = False
    init_prompt_file: str | None = None


@dataclass
class TodoItem:
    item_id: str
    title: str
    owner: str
    source_heading: str
    excerpt: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _runtime_dir(repo_root: Path) -> Path:
    return repo_root / "autoloop" / "runtime"


def _session_bindings_path(repo_root: Path) -> Path:
    return _runtime_dir(repo_root) / "session_bindings.json"


def _active_sessions_path(repo_root: Path) -> Path:
    return _runtime_dir(repo_root) / "active_sessions.json"


def _load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config: {path}")
    return data


def _agents_from_config(cfg: dict[str, Any]) -> list[AgentConfig]:
    out: list[AgentConfig] = []
    for raw in cfg.get("agents", []):
        out.append(
            AgentConfig(
                name=str(raw["name"]),
                role=str(raw["role"]),
                session_id=str(raw["session_id"]).strip() if raw.get("session_id") else None,
                keywords=[str(x).lower() for x in raw.get("keywords", [])],
                workdir=str(raw["workdir"]).strip() if raw.get("workdir") else None,
                model=str(raw["model"]).strip() if raw.get("model") else None,
                keep_session=bool(raw.get("keep_session", False)),
                init_prompt_file=str(raw["init_prompt_file"]).strip() if raw.get("init_prompt_file") else None,
            )
        )
    return out


def _agent_workdir(repo_root: Path, cfg: dict[str, Any], agent: AgentConfig) -> Path:
    worktree_root = str(cfg.get("worktree_root", "worktrees")).strip() or "worktrees"
    if agent.workdir:
        p = Path(agent.workdir)
        return (p if p.is_absolute() else repo_root / p).resolve()
    return (repo_root / worktree_root / f"{agent.name}-agent").resolve()


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_worktree_registered(repo_root: Path, workdir: Path) -> bool:
    proc = _run_git(repo_root, ["worktree", "list", "--porcelain"])
    if proc.returncode != 0:
        return False
    needle = f"worktree {workdir}"
    return any(line.strip() == needle for line in proc.stdout.splitlines())


def _enforce_directory_binding(repo_root: Path, cfg: dict[str, Any], agents: list[AgentConfig]) -> None:
    bindings = _load_json_file(_session_bindings_path(repo_root), default={"by_session": {}, "by_workdir": {}})
    by_session = bindings.get("by_session", {}) if isinstance(bindings, dict) else {}
    by_workdir = bindings.get("by_workdir", {}) if isinstance(bindings, dict) else {}
    for agent in agents:
        wd = str(_agent_workdir(repo_root, cfg, agent))
        if not agent.session_id:
            continue
        sid = str(agent.session_id)
        prev_wd = by_session.get(sid)
        prev_sid = by_workdir.get(wd)
        if prev_wd and prev_wd != wd:
            raise RuntimeError(f"Session binding violation: session {sid} was bound to {prev_wd}, not {wd}")
        if prev_sid and prev_sid != sid:
            raise RuntimeError(f"Directory binding violation: workdir {wd} already bound to session {prev_sid}")
        by_session[sid] = wd
        by_workdir[wd] = sid
    _save_json_file(_session_bindings_path(repo_root), {"by_session": by_session, "by_workdir": by_workdir, "ts": _utc_now()})


def prepare_worktrees(repo_root: Path, cfg: dict[str, Any]) -> None:
    agents = _agents_from_config(cfg)
    _enforce_directory_binding(repo_root, cfg, agents)
    git_cfg = cfg.get("git_strategy", {}) if isinstance(cfg.get("git_strategy"), dict) else {}
    use_worktrees = bool(git_cfg.get("use_worktree_branches", True))
    base_branch = str(git_cfg.get("base_branch", "main"))
    branch_prefix = str(git_cfg.get("agent_branch_prefix", "agent"))

    for agent in agents:
        wd = _agent_workdir(repo_root, cfg, agent)
        wd.mkdir(parents=True, exist_ok=True)
        if use_worktrees:
            branch = f"{branch_prefix}/{agent.name}"
            if not _git_worktree_registered(repo_root, wd):
                if wd.exists():
                    shutil.rmtree(wd)
                add = _run_git(repo_root, ["worktree", "add", "--force", "-B", branch, str(wd), base_branch])
                if add.returncode != 0:
                    raise RuntimeError(f"git worktree add failed for {agent.name}: {add.stderr.strip()}")
            checkout_ok = False
            for _ in range(3):
                checkout = subprocess.run(
                    ["git", "checkout", branch],
                    cwd=str(wd),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if checkout.returncode == 0:
                    checkout_ok = True
                    break
                if "index.lock" in (checkout.stderr or ""):
                    lock_path = repo_root / ".git" / "worktrees" / f"{agent.name}-agent" / "index.lock"
                    lock_path.unlink(missing_ok=True)
                    time.sleep(0.5)
                    continue
                break
            if not checkout_ok:
                raise RuntimeError(f"git checkout failed in {wd}: {checkout.stderr.strip()}")
        marker = wd / ".autoloop_agent"
        marker.write_text(
            f"agent={agent.name}\nrole={agent.role}\nsession_id={agent.session_id}\nupdated_at={_utc_now()}\n",
            encoding="utf-8",
        )


def _parse_blueprint_sections(blueprint_text: str) -> list[tuple[str, str]]:
    lines = blueprint_text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Blueprint Root"
    current_body: list[str] = []
    heading_re = re.compile(r"^(#{1,6}\s+.+|\d+(?:\.\d+)*\s+.+)$")

    for line in lines:
        if heading_re.match(line.strip()):
            if current_body:
                sections.append((current_heading, current_body))
            current_heading = line.strip()
            current_body = []
            continue
        if line.strip():
            current_body.append(line.rstrip())

    if current_body:
        sections.append((current_heading, current_body))
    return [(h, "\n".join(b)) for h, b in sections]


def _score_section(text: str, agent: AgentConfig) -> int:
    lower = text.lower()
    return sum(lower.count(kw) for kw in agent.keywords)


def _build_todos(sections: list[tuple[str, str]], agents: list[AgentConfig]) -> list[TodoItem]:
    todos: list[TodoItem] = []
    for idx, (heading, body) in enumerate(sections, start=1):
        plain = f"{heading}\n{body}".strip()
        if len(plain) < 80:
            continue
        scores = [(agent.name, _score_section(plain, agent)) for agent in agents]
        owner, best = max(scores, key=lambda x: x[1])
        if best <= 0:
            owner = "planning"
        excerpt = " ".join(body.split())[:260]
        title = re.sub(r"^[#\d\.\s]+", "", heading).strip() or f"Section {idx}"
        todos.append(
            TodoItem(
                item_id=f"T{idx:04d}",
                title=title[:100],
                owner=owner,
                source_heading=heading,
                excerpt=excerpt,
            )
        )
    return todos


def _phase_count(todos: list[TodoItem], agents: list[AgentConfig], per_phase: int) -> int:
    max_count = 1
    for agent in agents:
        count = len([t for t in todos if t.owner == agent.name])
        max_count = max(max_count, math.ceil(max(1, count) / max(1, per_phase)))
    return max_count


def _phase_tasks_for_agent(
    all_todos: list[TodoItem], agent_name: str, phase_index: int, per_phase: int
) -> list[TodoItem]:
    owned = [x for x in all_todos if x.owner == agent_name]
    start = phase_index * per_phase
    end = start + per_phase
    return owned[start:end]


def _phase_dir(repo_root: Path, phase_no: int) -> Path:
    return repo_root / "autoloop" / "phases" / f"phase_{phase_no:02d}"


def _task_file(repo_root: Path, phase_no: int, agent: str) -> Path:
    return _phase_dir(repo_root, phase_no) / "tasks" / f"{agent}.md"


def _result_file(repo_root: Path, phase_no: int, agent: str) -> Path:
    return _phase_dir(repo_root, phase_no) / "results" / f"{agent}.md"


def _ensure_phase_layout(repo_root: Path, phase_no: int) -> None:
    phase = _phase_dir(repo_root, phase_no)
    (phase / "tasks").mkdir(parents=True, exist_ok=True)
    (phase / "results").mkdir(parents=True, exist_ok=True)
    (repo_root / "autoloop" / "runtime" / "hooks").mkdir(parents=True, exist_ok=True)
    (repo_root / "autoloop" / "runtime" / "logs").mkdir(parents=True, exist_ok=True)


def _write_task_md(
    *,
    repo_root: Path,
    phase_no: int,
    agent: AgentConfig,
    tasks: list[TodoItem],
) -> None:
    path = _task_file(repo_root, phase_no, agent.name)
    if not tasks:
        path.write_text(
            f"# Phase {phase_no:02d} - {agent.name}\n\n"
            "## Status\n\n"
            "No task assigned in this phase.\n",
            encoding="utf-8",
        )
        return

    lines = [
        f"# Phase {phase_no:02d} - {agent.name} ({agent.role})",
        "",
        "## Objectives",
        "",
    ]
    for item in tasks:
        lines.extend(
            [
                f"- [ ] `{item.item_id}` {item.title}",
                f"  - Source: `{item.source_heading}`",
                f"  - Context: {item.excerpt}",
            ]
        )
    lines.extend(
        [
            "",
            "## Mandatory Output",
            "",
            "1. 完成项勾选为 `[x]`，并补充实现说明",
            "2. 每次文件改动后提交 commit（信息包含 `agent:` 和改动摘要）",
            "3. 将所有 commit hash、文件清单写入结果文档",
            "4. 如果任务无法完成，写明阻塞点与建议修复方案",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_result_stub(repo_root: Path, phase_no: int, agent: str) -> None:
    path = _result_file(repo_root, phase_no, agent)
    if not path.exists():
        path.write_text(
            f"# Phase {phase_no:02d} Result - {agent}\n\n"
            "## Status\n\n"
            "- pending\n\n"
            "## Commits\n\n"
            "- (fill by agent)\n\n"
            "## Changed Files\n\n"
            "- (fill by agent)\n",
            encoding="utf-8",
        )


def _build_agent_prompt(
    *,
    repo_root: Path,
    phase_no: int,
    agent: AgentConfig,
    task_path: Path,
    result_path: Path,
) -> str:
    return (
        f"你是 {agent.role}。\n"
        f"工作目录: {repo_root}\n"
        f"请读取任务文档: {task_path}\n"
        f"完成后写入结果文档: {result_path}\n"
        "执行要求:\n"
        "1) 严格只做任务文档中的事项。\n"
        "2) 每次改动文件后立即提交 commit，message 必须包含 `agent:"
        f"{agent.name}`。\n"
        "3) 结果文档必须列出 commit hash 与改动文件。\n"
        "4) 完成后在结果文档写 `Status: done`。\n"
        "5) 最终回复只输出 `AGENT_DONE`。\n"
        f"当前 phase: {phase_no:02d}\n"
    )


def _run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    log_path: Path,
) -> tuple[int, float]:
    start = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except Exception:
                pass
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
                proc.wait(timeout=10)
            return 124, time.time() - start
    return int(proc.returncode or 0), time.time() - start


def _run_codex_and_collect(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    log_path: Path,
) -> tuple[int, float, dict[str, Any]]:
    rc, duration = _run_subprocess(cmd, cwd=cwd, timeout_s=timeout_s, log_path=log_path)
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    events: list[dict[str, Any]] = []
    for line in log_text.splitlines():
        s = line.strip()
        if not s.startswith("{"):
            continue
        try:
            item = json.loads(s)
            if isinstance(item, dict):
                events.append(item)
        except Exception:
            continue
    thread_ids = [e.get("thread_id") for e in events if e.get("type") == "thread.started"]
    messages = [
        str((e.get("item") or {}).get("text", ""))
        for e in events
        if e.get("type") == "item.completed" and isinstance(e.get("item"), dict) and (e.get("item") or {}).get("type") == "agent_message"
    ]
    payload = {
        "thread_ids": [x for x in thread_ids if isinstance(x, str)],
        "messages": messages,
        "events": len(events),
    }
    return rc, duration, payload


def _hook_path(repo_root: Path, name: str) -> Path:
    return repo_root / "autoloop" / "runtime" / "hooks" / f"{name}.json"


def _write_hook(repo_root: Path, name: str, payload: dict[str, Any]) -> None:
    p = _hook_path(repo_root, name)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_active_sessions(repo_root: Path, agents: list[AgentConfig]) -> dict[str, str]:
    data = _load_json_file(_active_sessions_path(repo_root), default={})
    raw = dict(data) if isinstance(data, dict) else {}
    valid_names = {a.name for a in agents}
    out = {k: str(v) for k, v in raw.items() if k in valid_names and str(v).strip()}
    changed = False
    for agent in agents:
        if agent.name not in out and agent.session_id:
            out[agent.name] = str(agent.session_id)
            changed = True
    if set(raw.keys()) != set(out.keys()):
        changed = True
    if changed:
        _save_json_file(_active_sessions_path(repo_root), out)
    return out


def _phase_summary_text(repo_root: Path, phase_no: int, agent_name: str) -> str:
    if phase_no <= 1:
        return "first phase"
    prev = _result_file(repo_root, phase_no - 1, agent_name)
    if not prev.exists():
        return "no previous result"
    text = prev.read_text(encoding="utf-8", errors="replace")
    slim = "\n".join(text.splitlines()[:80])
    return slim[:3000]


def _rotate_session_if_needed(
    *,
    repo_root: Path,
    cfg: dict[str, Any],
    phase_no: int,
    agent: AgentConfig,
    active_session_id: str,
    workdir: Path,
) -> str:
    rotation = cfg.get("session_rotation", {}) if isinstance(cfg.get("session_rotation"), dict) else {}
    if not bool(rotation.get("enabled", False)):
        return active_session_id
    every = int(rotation.get("rotate_every_phases", 1) or 1)
    if every <= 0 or phase_no <= 1 or (phase_no - 1) % every != 0:
        return active_session_id

    summary = _phase_summary_text(repo_root, phase_no, agent.name)
    prompt = (
        f"你是 {agent.role}。这是 session 轮换初始化。\n"
        f"上一阶段摘要:\n{summary}\n\n"
        "请只回复 `SESSION_ROTATE_READY`。"
    )
    cmd = ["codex", "exec", prompt, "--json", "--dangerously-bypass-approvals-and-sandbox"]
    log = repo_root / "autoloop" / "runtime" / "logs" / f"phase_{phase_no:02d}_{agent.name}_rotate.log"
    rc, _duration, payload = _run_codex_and_collect(cmd, cwd=workdir, timeout_s=1200, log_path=log)
    if rc != 0:
        return active_session_id
    thread_ids = payload.get("thread_ids") if isinstance(payload, dict) else None
    if isinstance(thread_ids, list) and thread_ids and isinstance(thread_ids[0], str):
        new_session = str(thread_ids[0])
        _write_hook(
            repo_root,
            f"phase_{phase_no:02d}_{agent.name}_session_rotated",
            {
                "phase": phase_no,
                "agent": agent.name,
                "old_session": active_session_id,
                "new_session": new_session,
                "ts": _utc_now(),
            },
        )
        return new_session
    return active_session_id


def _load_init_prompt(repo_root: Path, agent: AgentConfig) -> str:
    default = (
        f"你是 {agent.role}。\n"
        "这是初始化会话。请只回复 `SESSION_BOOTSTRAP_READY`。\n"
        "后续你将从 markdown 任务文档读取工作要求。"
    )
    if not agent.init_prompt_file:
        return default
    p = Path(agent.init_prompt_file)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    if not p.exists():
        return default
    return p.read_text(encoding="utf-8", errors="replace").strip() or default


def init_sessions(repo_root: Path, cfg: dict[str, Any], only_agent: str = "", force_new: bool = False) -> dict[str, Any]:
    agents = _agents_from_config(cfg)
    prepare_worktrees(repo_root, cfg)
    active = _load_active_sessions(repo_root, agents)
    changed = False
    created: dict[str, str] = {}
    kept: dict[str, str] = {}

    for agent in agents:
        if only_agent and agent.name != only_agent:
            continue
        if agent.keep_session and agent.session_id:
            active[agent.name] = str(agent.session_id)
            kept[agent.name] = str(agent.session_id)
            changed = True
            continue
        if active.get(agent.name) and not force_new:
            kept[agent.name] = str(active[agent.name])
            continue
        workdir = _agent_workdir(repo_root, cfg, agent)
        prompt = _load_init_prompt(repo_root, agent)
        cmd = ["codex", "exec"]
        if agent.model:
            cmd += ["-m", agent.model]
        cmd += [prompt, "--json", "--dangerously-bypass-approvals-and-sandbox"]
        log = repo_root / "autoloop" / "runtime" / "logs" / f"init_session_{agent.name}.log"
        rc, _dur, payload = _run_codex_and_collect(cmd, cwd=workdir, timeout_s=1500, log_path=log)
        thread_ids = payload.get("thread_ids") if isinstance(payload, dict) else None
        captured_thread = (
            str(thread_ids[0])
            if isinstance(thread_ids, list) and thread_ids and isinstance(thread_ids[0], str)
            else ""
        )
        if captured_thread:
            session_id = captured_thread
            active[agent.name] = session_id
            created[agent.name] = session_id
            changed = True
            _write_hook(
                repo_root,
                f"session_init_{agent.name}",
                {
                    "agent": agent.name,
                    "session_id": session_id,
                    "cwd": str(workdir),
                    "status": "created" if rc == 0 else "created_with_warning",
                    "returncode": rc,
                    "ts": _utc_now(),
                },
            )
            continue

        if active.get(agent.name):
            kept[agent.name] = str(active[agent.name])
            _write_hook(
                repo_root,
                f"session_init_{agent.name}_fallback_keep",
                {
                    "agent": agent.name,
                    "session_id": str(active[agent.name]),
                    "cwd": str(workdir),
                    "status": "fallback_keep",
                    "returncode": rc,
                    "ts": _utc_now(),
                },
            )
            continue
        raise RuntimeError(f"Failed to init session for {agent.name}; see {log}")

    if changed:
        _save_json_file(_active_sessions_path(repo_root), active)
    return {"active_sessions": active, "created": created, "kept": kept, "ts": _utc_now()}


def plan_from_blueprint(repo_root: Path, cfg: dict[str, Any]) -> int:
    agents = _agents_from_config(cfg)
    blueprint_path = Path(str(cfg["blueprint_path"]))
    sections = _parse_blueprint_sections(blueprint_path.read_text(encoding="utf-8", errors="replace"))
    todos = _build_todos(sections, agents)
    phase_total = _phase_count(todos, agents, int(cfg.get("tasks_per_phase_per_agent", 3)))
    per_phase = int(cfg.get("tasks_per_phase_per_agent", 3))

    for phase_no in range(1, phase_total + 1):
        _ensure_phase_layout(repo_root, phase_no)
        valid_names = {a.name for a in agents}
        for bucket in ("tasks", "results"):
            folder = _phase_dir(repo_root, phase_no) / bucket
            for old in folder.glob("*.md"):
                if old.stem not in valid_names:
                    old.unlink(missing_ok=True)
        for agent in agents:
            tasks = _phase_tasks_for_agent(todos, agent.name, phase_no - 1, per_phase)
            _write_task_md(repo_root=repo_root, phase_no=phase_no, agent=agent, tasks=tasks)
            _write_result_stub(repo_root, phase_no, agent.name)

    summary = {
        "generated_at": _utc_now(),
        "phase_total": phase_total,
        "todo_total": len(todos),
        "by_agent": {a.name: len([x for x in todos if x.owner == a.name]) for a in agents},
    }
    (repo_root / "autoloop" / "runtime").mkdir(parents=True, exist_ok=True)
    (repo_root / "autoloop" / "runtime" / "plan_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return phase_total


def run_phase(repo_root: Path, cfg: dict[str, Any], phase_no: int, dry_run: bool, rerun_failed_only: bool = False) -> int:
    agents = _agents_from_config(cfg)
    prepare_worktrees(repo_root, cfg)
    _ensure_phase_layout(repo_root, phase_no)
    timeout_s = int(cfg.get("resume_timeout_seconds", 5400))
    retry_limit = int(cfg.get("max_retries_per_agent", 2) or 2)
    retry_backoff_s = float(cfg.get("retry_backoff_seconds", 8) or 8)
    codex_base = [str(x) for x in cfg.get("codex_command", ["codex", "exec", "resume"])]
    codex_extra = [str(x) for x in cfg.get("codex_extra_args", ["--json"])]
    active_sessions = _load_active_sessions(repo_root, agents)
    init_result = init_sessions(repo_root, cfg)
    active_sessions = dict(init_result.get("active_sessions", {}))

    phase_start = _utc_now()
    _write_hook(
        repo_root,
        f"phase_{phase_no:02d}_started",
        {"phase": phase_no, "ts": phase_start, "dry_run": dry_run},
    )

    ran_agents = 0
    failures = 0
    for agent in agents:
        if rerun_failed_only and not _hook_path(repo_root, f"phase_{phase_no:02d}_{agent.name}_failed").exists():
            continue
        task = _task_file(repo_root, phase_no, agent.name)
        result = _result_file(repo_root, phase_no, agent.name)
        task_text = task.read_text(encoding="utf-8", errors="replace") if task.exists() else ""
        has_task = "No task assigned in this phase." not in task_text
        if not has_task:
            result.write_text(
                f"# Phase {phase_no:02d} Result - {agent.name}\n\nStatus: skipped (no task)\n",
                encoding="utf-8",
            )
            _write_hook(
                repo_root,
                f"phase_{phase_no:02d}_{agent.name}_skipped",
                {"phase": phase_no, "agent": agent.name, "status": "skipped", "ts": _utc_now()},
            )
            continue

        ran_agents += 1
        workdir = _agent_workdir(repo_root, cfg, agent)
        session_id = str(active_sessions.get(agent.name) or agent.session_id or "")
        if not session_id:
            raise RuntimeError(f"No active session for agent {agent.name}; run `init-sessions` first.")
        if not agent.keep_session:
            session_id = _rotate_session_if_needed(
                repo_root=repo_root,
                cfg=cfg,
                phase_no=phase_no,
                agent=agent,
                active_session_id=session_id,
                workdir=workdir,
            )
        active_sessions[agent.name] = session_id
        prompt = _build_agent_prompt(
            repo_root=repo_root,
            phase_no=phase_no,
            agent=agent,
            task_path=task,
            result_path=result,
        )
        cmd = list(codex_base)
        if agent.model:
            cmd += ["-m", agent.model]
        cmd += [session_id, prompt] + codex_extra
        log = repo_root / "autoloop" / "runtime" / "logs" / f"phase_{phase_no:02d}_{agent.name}.log"

        if dry_run:
            log.write_text(
                "DRY RUN\n"
                + f"cwd={workdir}\n"
                + shlex.join(cmd)
                + "\n",
                encoding="utf-8",
            )
            _write_hook(
                repo_root,
                f"phase_{phase_no:02d}_{agent.name}_dry_run",
                {
                    "phase": phase_no,
                    "agent": agent.name,
                    "status": "dry_run",
                    "cmd": cmd,
                    "cwd": str(workdir),
                    "session_id": session_id,
                    "ts": _utc_now(),
                },
            )
            continue

        rc = 1
        duration = 0.0
        payload: dict[str, Any] = {}
        for attempt in range(1, retry_limit + 1):
            rc, duration, payload = _run_codex_and_collect(cmd, cwd=workdir, timeout_s=timeout_s, log_path=log)
            if rc == 0:
                break
            _write_hook(
                repo_root,
                f"phase_{phase_no:02d}_{agent.name}_retry_{attempt}",
                {
                    "phase": phase_no,
                    "agent": agent.name,
                    "attempt": attempt,
                    "returncode": rc,
                    "ts": _utc_now(),
                },
            )
            if attempt < retry_limit:
                time.sleep(retry_backoff_s)
        status = "done" if rc == 0 else "failed"
        if rc != 0:
            failures += 1
        _write_hook(
            repo_root,
            f"phase_{phase_no:02d}_{agent.name}_{status}",
            {
                "phase": phase_no,
                "agent": agent.name,
                "status": status,
                "returncode": rc,
                "duration_s": round(duration, 2),
                "log": str(log),
                "cwd": str(workdir),
                "session_id": session_id,
                "events": int(payload.get("events", 0)) if isinstance(payload, dict) else 0,
                "ts": _utc_now(),
            },
        )

    _write_hook(
        repo_root,
        f"phase_{phase_no:02d}_all_agents_done",
        {
            "phase": phase_no,
            "ran_agents": ran_agents,
            "failures": failures,
            "status": "done" if failures == 0 else "partial_failed",
            "ts": _utc_now(),
        },
    )
    _save_json_file(_active_sessions_path(repo_root), active_sessions)
    return 0 if failures == 0 else 1


def _run_check_commands(repo_root: Path, commands: list[str]) -> int:
    for command in commands:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            return proc.returncode
    return 0


def _git_overlap_report(repo_root: Path, phase_no: int) -> dict[str, Any]:
    raw = subprocess.run(
        "git log --pretty=format:'%H|%s' --name-only --since='24 hours ago'",
        shell=True,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    file_to_agents: dict[str, set[str]] = {}
    current_agent = "unknown"
    for line in raw.splitlines():
        if "|" in line:
            subject = line.split("|", 1)[1]
            match = re.search(r"agent:([a-zA-Z0-9_-]+)", subject)
            current_agent = match.group(1) if match else "unknown"
            continue
        if not line.strip() or line.endswith(".md") is False and "/" not in line:
            continue
        file_to_agents.setdefault(line.strip(), set()).add(current_agent)
    overlap = {k: sorted(v) for k, v in file_to_agents.items() if len(v) > 1}
    report = {"phase": phase_no, "overlap_files": overlap, "generated_at": _utc_now()}
    out = repo_root / "autoloop" / "runtime" / f"phase_{phase_no:02d}_overlap_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _merge_agent_branches_to_integration(repo_root: Path, cfg: dict[str, Any]) -> None:
    git_cfg = cfg.get("git_strategy", {}) if isinstance(cfg.get("git_strategy"), dict) else {}
    if not bool(git_cfg.get("use_worktree_branches", True)):
        return
    base_branch = str(git_cfg.get("base_branch", "main"))
    integration = str(git_cfg.get("integration_branch", "integration/autoloop"))
    prefix = str(git_cfg.get("agent_branch_prefix", "agent"))
    agents = _agents_from_config(cfg)

    checkout_base = _run_git(repo_root, ["checkout", base_branch])
    if checkout_base.returncode != 0:
        raise RuntimeError(f"Cannot checkout {base_branch}: {checkout_base.stderr.strip()}")

    ensure_integration = _run_git(repo_root, ["checkout", "-B", integration, base_branch])
    if ensure_integration.returncode != 0:
        raise RuntimeError(f"Cannot prepare integration branch {integration}: {ensure_integration.stderr.strip()}")

    for agent in agents:
        branch = f"{prefix}/{agent.name}"
        merge = _run_git(repo_root, ["merge", "--no-ff", "--no-edit", branch])
        if merge.returncode != 0:
            _run_git(repo_root, ["merge", "--abort"])
            raise RuntimeError(f"Merge conflict while merging {branch} into {integration}")


def smoke_resume(repo_root: Path, cfg: dict[str, Any], agent_name: str) -> int:
    agents = _agents_from_config(cfg)
    prepare_worktrees(repo_root, cfg)
    init_data = init_sessions(repo_root, cfg, only_agent=agent_name)
    active_sessions = dict(init_data.get("active_sessions", {}))
    target = next((a for a in agents if a.name == agent_name), None)
    if target is None:
        raise ValueError(f"Unknown agent: {agent_name}")
    session_id = str(active_sessions.get(target.name) or target.session_id or "")
    if not session_id:
        raise RuntimeError(f"No session available for agent {target.name}")
    cmd = [str(x) for x in cfg.get("codex_command", ["codex", "exec", "resume"])]
    if target.model:
        cmd += ["-m", target.model]
    workdir = _agent_workdir(repo_root, cfg, target)
    workdir.mkdir(parents=True, exist_ok=True)
    marker = f"RESUME_OK|agent={target.name}|cwd={workdir}"
    cmd += [session_id, f"仅回复: {marker}"]
    cmd += [str(x) for x in cfg.get("codex_extra_args", ["--json"])]
    log = repo_root / "autoloop" / "runtime" / "logs" / f"smoke_{target.name}.log"
    rc, _duration, payload = _run_codex_and_collect(cmd, cwd=workdir, timeout_s=900, log_path=log)
    print(log.read_text(encoding="utf-8", errors="replace"))
    if rc != 0:
        return rc
    thread_ids = payload.get("thread_ids") if isinstance(payload, dict) else []
    messages = payload.get("messages") if isinstance(payload, dict) else []
    got_thread = bool(thread_ids and str(thread_ids[0]) == session_id)
    got_agent = bool(messages and str(messages[-1]).strip() == marker)
    got_cwd = str(workdir).endswith(f"{target.name}-agent") or str(workdir) == str(_agent_workdir(repo_root, cfg, target))
    ok = got_thread and got_agent and got_cwd
    _write_hook(
        repo_root,
        f"smoke_resume_{target.name}",
        {
            "agent": target.name,
            "session_id": session_id,
            "cwd": str(workdir),
            "thread_ok": got_thread,
            "agent_ok": got_agent,
            "cwd_ok": got_cwd,
            "status": "ok" if ok else "failed",
            "ts": _utc_now(),
        },
    )
    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Team lead autoloop orchestrator for Codex resume sessions.")
    parser.add_argument("--config", default="autoloop/config.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--blueprint", default="")

    p_smoke = sub.add_parser("smoke-resume")
    p_smoke.add_argument("--agent", required=True)

    sub.add_parser("prepare-worktrees")
    p_init = sub.add_parser("init-sessions")
    p_init.add_argument("--agent", default="")
    p_init.add_argument("--force-new", action="store_true")

    p_run = sub.add_parser("run-phase")
    p_run.add_argument("--phase", type=int, required=True)
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--rerun-failed-only", action="store_true")

    p_rerun = sub.add_parser("rerun-failed")
    p_rerun.add_argument("--phase", type=int, required=True)

    p_all = sub.add_parser("run-all")
    p_all.add_argument("--max-phases", type=int, default=0)
    p_all.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    cfg_path = Path(args.config).resolve()
    cfg = _load_config(cfg_path)
    repo_root = Path(str(cfg.get("repo_root", ".")).strip() or ".").resolve()

    if args.cmd == "plan":
        if args.blueprint:
            cfg["blueprint_path"] = str(Path(args.blueprint).resolve())
        plan_from_blueprint(repo_root, cfg)
        return 0

    if args.cmd == "smoke-resume":
        return smoke_resume(repo_root, cfg, args.agent)

    if args.cmd == "prepare-worktrees":
        prepare_worktrees(repo_root, cfg)
        print(json.dumps({"status": "ok", "ts": _utc_now()}, ensure_ascii=False))
        return 0

    if args.cmd == "init-sessions":
        out = init_sessions(
            repo_root,
            cfg,
            only_agent=str(getattr(args, "agent", "") or ""),
            force_new=bool(getattr(args, "force_new", False)),
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "run-phase":
        rc = run_phase(repo_root, cfg, args.phase, args.dry_run, getattr(args, "rerun_failed_only", False))
        if rc != 0:
            return rc
        if not args.dry_run:
            _merge_agent_branches_to_integration(repo_root, cfg)
            checks = [str(x) for x in cfg.get("phase_verify_commands", [])]
            chk_rc = _run_check_commands(repo_root, checks)
            _git_overlap_report(repo_root, args.phase)
            return chk_rc
        return 0

    if args.cmd == "rerun-failed":
        rc = run_phase(repo_root, cfg, args.phase, dry_run=False, rerun_failed_only=True)
        if rc != 0:
            return rc
        _merge_agent_branches_to_integration(repo_root, cfg)
        checks = [str(x) for x in cfg.get("phase_verify_commands", [])]
        chk_rc = _run_check_commands(repo_root, checks)
        _git_overlap_report(repo_root, args.phase)
        return chk_rc

    if args.cmd == "run-all":
        phase_total = plan_from_blueprint(repo_root, cfg)
        max_phases = args.max_phases if args.max_phases > 0 else phase_total
        checks = [str(x) for x in cfg.get("phase_verify_commands", [])]
        for phase_no in range(1, min(phase_total, max_phases) + 1):
            rc = run_phase(repo_root, cfg, phase_no, args.dry_run)
            if rc != 0:
                return rc
            if not args.dry_run:
                _merge_agent_branches_to_integration(repo_root, cfg)
                chk_rc = _run_check_commands(repo_root, checks)
                _git_overlap_report(repo_root, phase_no)
                if chk_rc != 0:
                    return chk_rc
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
