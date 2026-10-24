from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import (
    _parse_cron_to_interval_seconds,
    _classify_summary_intent,
    _generate_planner_reply,
    _merge_rolling_summary,
    agents_list_tool,
    canvas_tool,
    channels_listener_tool,
    cron_tool,
    image_tool,
    discord_actions,
    nodes_tool,
    session_status_tool,
    slack_actions,
    telegram_actions,
    whatsapp_actions,
    sessions_announce_target,
    web_readability_tool,
)


def _ctx(root: Path):
    return SimpleNamespace(metadata={"repo_root": str(root)})


def test_parse_cron_to_interval_seconds_basic() -> None:
    assert _parse_cron_to_interval_seconds("*/5 * * * *") == 300
    assert _parse_cron_to_interval_seconds("* * * * *") == 60
    assert _parse_cron_to_interval_seconds("10m") == 600


def test_cron_tool_schedule_and_list(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    add = cron_tool({"action": "schedule", "name": "heartbeat", "task_input": "ping", "cron": "*/10 * * * *"}, ctx)
    assert add["status"] == "ok"
    assert add["task"].get("next_fire_ts") is not None
    out = cron_tool({"action": "list"}, ctx)
    assert out["status"] == "ok"
    assert "heartbeat" in out["tasks"]
    assert out["tasks"]["heartbeat"].get("next_fire_ts") is not None


def test_cron_tool_preview_returns_future_times(tmp_path: Path) -> None:
    out = cron_tool({"action": "preview", "cron": "*/15 * * * *", "count": 3}, _ctx(tmp_path))
    assert out["status"] == "ok"
    times = out.get("next_fire_times") or []
    assert len(times) == 3
    assert times[0] < times[1] < times[2]


def test_cron_tool_schedule_keeps_jitter_and_misfire_policy(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = cron_tool(
        {
            "action": "schedule",
            "name": "jittery",
            "task_input": "ping",
            "cron": "*/5 * * * *",
            "jitter_sec": 12,
            "misfire_policy": "catch_up",
        },
        ctx,
    )
    assert out["status"] == "ok"
    listed = cron_tool({"action": "list"}, ctx)
    task = listed["tasks"]["jittery"]
    assert task["jitter_sec"] == 12
    assert task["misfire_policy"] == "catch_up"


def test_cron_tool_run_due_enqueues_task(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    cron_tool(
        {
            "action": "schedule",
            "name": "due1",
            "task_input": "echo hi",
            "interval": "1s",
            "domain": "maintenance",
            "environment": "sandbox",
            "session_id": "cron",
            "priority": 3,
        },
        ctx,
    )
    out = cron_tool({"action": "run_due", "max_tasks": 10}, ctx)
    assert out["status"] == "ok"
    assert out["enqueued_count"] >= 1
    qf = tmp_path / "data" / "tasks" / "queue.jsonl"
    assert qf.exists()
    assert "echo hi" in qf.read_text(encoding="utf-8")


def test_sessions_announce_target_writes_record(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = sessions_announce_target(
        {"source_session_id": "s1", "target_session_id": "s2", "target": "continue task"},
        ctx,
    )
    assert out["status"] == "ok"
    p = tmp_path / "data" / "session_announcements.jsonl"
    assert p.exists()
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["target_session_id"] == "s2"


def test_sessions_announce_target_supports_list_and_consume(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    sessions_announce_target({"source_session_id": "a", "target_session_id": "b", "target": "step1"}, ctx)
    sessions_announce_target({"source_session_id": "a", "target_session_id": "b", "target": "step2"}, ctx)
    listed = sessions_announce_target({"action": "list", "target_session_id": "b"}, ctx)
    assert listed["status"] == "ok"
    assert listed["count"] >= 2
    consumed = sessions_announce_target({"action": "consume", "target_session_id": "b", "limit": 1}, ctx)
    assert consumed["status"] == "ok"
    assert consumed["count"] == 1
    listed2 = sessions_announce_target({"action": "list", "target_session_id": "b"}, ctx)
    assert listed2["count"] >= 1


def test_agents_list_reads_subagent_registry(tmp_path: Path) -> None:
    p = tmp_path / "data" / "subagent_status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "subagent:a": {
                    "label": "worker",
                    "status": "running",
                    "model": "qwen",
                    "parent_session_id": "root",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = agents_list_tool({}, _ctx(tmp_path))
    assert out["status"] == "ok"
    assert out["count"] == 1


def test_web_readability_cleans_noise_html() -> None:
    html = "<html><head><style>.x{}</style><script>alert(1)</script></head><body><h1>Hello</h1><p>World</p></body></html>"
    out = web_readability_tool({"html": html, "max_chars": 2000}, None)
    assert out["status"] == "ok"
    content = str(out["content"])
    assert "Hello" in content and "World" in content
    assert "alert(1)" not in content


def test_web_readability_applies_site_patch_for_github() -> None:
    html = """
    <html><body>
      <header>Top Nav</header>
      <nav>Side Nav</nav>
      <main><article><h1>Issue Title</h1><p>Body content</p></article></main>
      <footer>Footer</footer>
    </body></html>
    """
    out = web_readability_tool({"url": "https://github.com/org/repo/issues/1", "html": html}, None)
    assert out["status"] == "ok"
    assert out["site_patch"]["site"] == "github"
    assert "Top Nav" not in out["content"]
    assert "Issue Title" in out["content"]


def test_web_readability_applies_site_patch_for_devto() -> None:
    html = """
    <html><body>
      <aside class="crayons-layout__sidebar-left">left</aside>
      <article><h1>Dev Post</h1><p>Body</p></article>
      <div id="comments-container">comments</div>
    </body></html>
    """
    out = web_readability_tool({"url": "https://dev.to/a/b", "html": html}, None)
    assert out["status"] == "ok"
    assert out["site_patch"]["site"] == "devto"
    assert "comments" not in out["content"]
    assert "Dev Post" in out["content"]


def test_web_readability_applies_site_patch_for_stackoverflow_and_metrics() -> None:
    html = """
    <html><body>
      <aside class="left-sidebar">left links</aside>
      <main><article><h1>Question title</h1><p>Accepted answer text</p></article></main>
      <div id="comments">noisy comments</div>
    </body></html>
    """
    out = web_readability_tool({"url": "https://stackoverflow.com/questions/1/x", "html": html}, None)
    assert out["status"] == "ok"
    assert out["site_patch"]["site"] == "stackoverflow"
    assert "left links" not in out["content"]
    assert "noisy comments" not in out["content"]
    assert "Accepted answer text" in out["content"]
    dm = dict(out.get("diff_metrics") or {})
    assert int(dm.get("source_chars") or 0) > 0
    assert float(dm.get("tag_reduction_ratio") or 0.0) >= 0.0
    assert float(dm.get("clean_text_ratio_vs_source") or 0.0) > 0.0


def test_web_readability_applies_site_patch_for_medium() -> None:
    html = """
    <html><body>
      <div class="metabar">meta</div>
      <article><h1>Medium story</h1><p>Long body</p></article>
      <section aria-label="Responses">comments</section>
    </body></html>
    """
    out = web_readability_tool({"url": "https://medium.com/@a/post", "html": html}, None)
    assert out["status"] == "ok"
    assert out["site_patch"]["site"] == "medium"
    assert "meta" not in out["content"]
    assert "comments" not in out["content"]
    assert "Medium story" in out["content"]


def test_image_tool_includes_budget_fields(tmp_path: Path) -> None:
    # 1x1 transparent png
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "a.png"
    p.write_bytes(png)
    out = image_tool({"path": str(p)}, None)
    assert out["status"] == "ok"
    assert "token_budget" in out


def test_image_tool_ocr_mode_none(tmp_path: Path) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "none.png"
    p.write_bytes(png)
    out = image_tool({"path": str(p), "ocr_mode": "none", "text_hint": "h"}, None)
    assert out["status"] == "ok"
    assert out["ocr_engine"] == "none"


def test_image_tool_ocr_mode_vision_api(tmp_path: Path, monkeypatch) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "vision.png"
    p.write_bytes(png)

    def _fake_post(url, payload, timeout=15.0):
        _ = (url, payload, timeout)
        return {"status_code": 200, "body": json.dumps({"ocr_text": "vision text"}, ensure_ascii=False)}

    monkeypatch.setattr("quentin.tools.execution_parity._http_post_json", _fake_post)
    out = image_tool({"path": str(p), "ocr_mode": "vision_api", "vision_endpoint": "http://x"}, None)
    assert out["status"] == "ok"
    assert out["ocr_engine"] == "vision_api"
    assert "vision text" in str(out.get("ocr_text") or "")


def test_image_tool_auto_ocr_fallbacks_to_vision_when_low_confidence(tmp_path: Path, monkeypatch) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "fallback.png"
    p.write_bytes(png)

    def _fake_post(url, payload, timeout=15.0):
        _ = (url, payload, timeout)
        return {"status_code": 200, "body": json.dumps({"ocr_text": "vision fallback", "confidence": 0.92}, ensure_ascii=False)}

    monkeypatch.setattr("quentin.tools.execution_parity._http_post_json", _fake_post)
    out = image_tool(
        {
            "path": str(p),
            "ocr_mode": "auto",
            "ocr_min_confidence": 0.5,
            "vision_endpoint": "http://x",
            "text_hint": "",
        },
        None,
    )
    assert out["status"] == "ok"
    assert out["ocr_engine"] == "vision_api"
    assert out["ocr_fallback_used"] is True
    assert float(out.get("ocr_confidence") or 0.0) >= 0.9


def test_image_tool_can_save_ocr_memory_with_hint(tmp_path: Path) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "b.png"
    p.write_bytes(png)
    out = image_tool({"path": str(p), "text_hint": "hello", "save_ocr_memory": True}, _ctx(tmp_path))
    assert out["status"] == "ok"
    assert out.get("memory_saved") is True
    mem = tmp_path / "data" / "image_ocr_memory.jsonl"
    assert mem.exists()
    assert "hello" in mem.read_text(encoding="utf-8")


def test_canvas_tool_component_lifecycle(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    c1 = canvas_tool({"action": "create", "type": "ActionCard", "props": {"title": "T"}}, ctx)
    assert c1["status"] == "ok"
    cid = c1["component"]["component_id"]
    u1 = canvas_tool({"action": "update", "component_id": cid, "state": {"disabled": True}}, ctx)
    assert u1["status"] == "ok"
    assert u1["component"]["state"]["disabled"] is True
    g1 = canvas_tool({"action": "get", "component_id": cid}, ctx)
    assert g1["status"] == "ok"
    d1 = canvas_tool({"action": "delete", "component_id": cid}, ctx)
    assert d1["status"] == "ok"
    ls = canvas_tool({"action": "list"}, ctx)
    assert ls["status"] == "ok"
    assert all(str(c.get("component_id")) != cid for c in ls.get("components") or [])


def test_canvas_tool_transition_and_ack(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    c1 = canvas_tool({"action": "create", "type": "ActionCard", "props": {"title": "x"}}, ctx)
    cid = c1["component"]["component_id"]
    tr = canvas_tool({"action": "transition", "component_id": cid, "status": "running"}, ctx)
    assert tr["status"] == "ok"
    assert tr["component"]["status"] == "running"
    ack = canvas_tool({"action": "ack", "component_id": cid, "ack_type": "clicked"}, ctx)
    assert ack["status"] == "ok"
    p = tmp_path / "data" / "canvas_component_acks.jsonl"
    assert p.exists()
    assert "clicked" in p.read_text(encoding="utf-8")
    listed = canvas_tool({"action": "list_acks", "component_id": cid}, ctx)
    assert listed["status"] == "ok"
    assert listed["count"] >= 1


def test_canvas_tool_transition_policy_blocks_invalid_edge(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    c1 = canvas_tool({"action": "create", "type": "ActionCard", "props": {"title": "edge"}}, ctx)
    cid = c1["component"]["component_id"]
    tr1 = canvas_tool({"action": "transition", "component_id": cid, "status": "running"}, ctx)
    assert tr1["status"] == "ok"
    tr2 = canvas_tool({"action": "transition", "component_id": cid, "status": "pending"}, ctx)
    assert tr2["status"] == "error"
    assert "invalid transition edge" in str(tr2.get("error") or "")
    tr3 = canvas_tool({"action": "transition", "component_id": cid, "status": "pending", "force": True}, ctx)
    assert tr3["status"] == "ok"


def test_canvas_tool_ack_timeout_watcher(tmp_path: Path) -> None:
    import time

    ctx = _ctx(tmp_path)
    c1 = canvas_tool({"action": "create", "type": "ActionCard", "props": {"title": "watch"}}, ctx)
    cid = c1["component"]["component_id"]
    comp_file = tmp_path / "data" / "canvas_components.json"
    raw = json.loads(comp_file.read_text(encoding="utf-8"))
    raw["components"][cid]["updated_at"] = float(time.time() - 100)
    comp_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    out = canvas_tool({"action": "check_ack_timeouts", "timeout_sec": 30}, ctx)
    assert out["status"] == "ok"
    assert out["pending_count"] >= 1
    target = [x for x in out.get("pending_acks") or [] if str(x.get("component_id") or "") == cid]
    assert target
    assert str((target[0].get("retry_hint") or {}).get("action") or "") == "update"


def test_session_status_includes_handoff_edges(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    sessions_announce_target({"source_session_id": "a", "target_session_id": "b", "target": "t1"}, ctx)
    sessions_announce_target({"source_session_id": "a", "target_session_id": "b", "target": "t2"}, ctx)
    status = session_status_tool({}, ctx)
    assert status["status"] == "ok"
    assert isinstance(status.get("handoff_edges"), list)
    assert status["handoff_edges"][0]["source"] == "a"
    assert status["handoff_edges"][0]["target"] == "b"
    assert "b" in (status.get("dangling_handoff_targets") or [])


def test_session_status_detects_handoff_cycles(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    sessions_announce_target({"source_session_id": "a", "target_session_id": "b", "target": "t"}, ctx)
    sessions_announce_target({"source_session_id": "b", "target_session_id": "c", "target": "t"}, ctx)
    sessions_announce_target({"source_session_id": "c", "target_session_id": "a", "target": "t"}, ctx)
    status = session_status_tool({}, ctx)
    assert status["status"] == "ok"
    assert status["handoff_longest_chain_length"] >= 3
    assert "a" in (status.get("handoff_cycle_nodes") or [])


def test_nodes_tool_list_contains_discovery_status(tmp_path: Path) -> None:
    out = nodes_tool({"action": "list"}, _ctx(tmp_path))
    assert out["status"] == "ok"
    assert "discovery" in out


def test_nodes_tool_heartbeat_and_purge_stale(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    up = nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
    assert up["status"] == "ok"
    listed = nodes_tool({"action": "list", "ttl_sec": 0}, ctx)
    assert listed["status"] == "ok"
    assert listed["stale_count"] >= 1
    hb = nodes_tool({"action": "heartbeat", "node_id": "n1"}, ctx)
    assert hb["status"] == "ok"
    listed2 = nodes_tool({"action": "list", "ttl_sec": 999999}, ctx)
    assert listed2["stale_count"] == 0
    purge = nodes_tool({"action": "purge_stale", "ttl_sec": 0}, ctx)
    assert purge["status"] == "ok"


def test_nodes_tool_assign_and_release_task(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
    assign = nodes_tool({"action": "assign_task", "task_id": "t1"}, ctx)
    assert assign["status"] == "ok"
    assert assign["assigned"]["node_id"] == "n1"
    listed = nodes_tool({"action": "list_assignments"}, ctx)
    assert listed["count"] >= 1
    rel = nodes_tool({"action": "release_task", "task_id": "t1", "final_status": "done"}, ctx)
    assert rel["status"] == "ok"
    assert rel["removed"] == 1
    hist = nodes_tool({"action": "assignment_history"}, ctx)
    assert hist["status"] == "ok"
    assert any(str(x.get("task_id") or "") == "t1" and str(x.get("final_status") or "") == "done" for x in hist.get("history") or [])


def test_nodes_tool_reconcile_releases_finished_assignments(tmp_path: Path) -> None:
    from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

    ctx = _ctx(tmp_path)
    nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
    q = TaskQueue(repo_root=str(tmp_path))
    item = TaskQueueItem.new(input_text="x", domain="maintenance", environment="sandbox")
    q.append(item)
    nodes_tool({"action": "assign_task", "task_id": item.task_id, "node_id": "n1"}, ctx)
    q.mark_done(item.task_id, ok=True)
    rec = nodes_tool({"action": "reconcile_assignments"}, ctx)
    assert rec["status"] == "ok"
    assert rec["released_count"] >= 1
    hist = nodes_tool({"action": "assignment_history"}, ctx)
    assert hist["status"] == "ok"
    assert hist["count"] >= 1


def test_nodes_tool_reconcile_auto_assigns_pending(tmp_path: Path) -> None:
    from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

    ctx = _ctx(tmp_path)
    nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
    q = TaskQueue(repo_root=str(tmp_path))
    item = TaskQueueItem.new(input_text="p", domain="maintenance", environment="sandbox")
    q.append(item)
    rec = nodes_tool({"action": "reconcile_assignments", "auto_assign_pending": True}, ctx)
    assert rec["status"] == "ok"
    assert rec["new_assigned_count"] >= 1
    listed = nodes_tool({"action": "list_assignments"}, ctx)
    assert any(str(a.get("task_id") or "") == item.task_id for a in listed.get("assignments") or [])


def test_nodes_tool_reconcile_migrates_stale_node_assignment(tmp_path: Path) -> None:
    import time

    from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

    ctx = _ctx(tmp_path)
    now = time.time()
    reg = tmp_path / "data" / "nodes_registry.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(
        json.dumps(
            {
                "nodes": [
                    {"node_id": "n1", "host": "127.0.0.1", "status": "online", "heartbeat_ts": 1, "updated_at": 1},
                    {"node_id": "n2", "host": "127.0.0.2", "status": "online", "heartbeat_ts": now, "updated_at": now},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    q = TaskQueue(repo_root=str(tmp_path))
    item = TaskQueueItem.new(input_text="migrate-me", domain="maintenance", environment="sandbox")
    q.append(item)
    nodes_tool({"action": "assign_task", "task_id": item.task_id, "node_id": "n1"}, ctx)
    rec = nodes_tool({"action": "reconcile_assignments", "ttl_sec": 60, "migrate_stale_assignments": True}, ctx)
    assert rec["status"] == "ok"
    assert rec["migrated_count"] >= 1
    listed = nodes_tool({"action": "list_assignments"}, ctx)
    target = [a for a in listed.get("assignments") or [] if str(a.get("task_id") or "") == item.task_id]
    assert target
    assert target[0]["node_id"] == "n2"
    assert str((target[0].get("meta") or {}).get("migrated_from") or "") == "n1"


def test_nodes_tool_lease_acquire_and_release(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    a1 = nodes_tool({"action": "acquire_lease", "lease_key": "task-x", "node_id": "n1", "lease_ttl_sec": 30}, ctx)
    assert a1["status"] == "ok"
    assert a1["acquired"] is True
    a2 = nodes_tool({"action": "acquire_lease", "lease_key": "task-x", "node_id": "n2", "lease_ttl_sec": 30}, ctx)
    assert a2["status"] == "ok"
    assert a2["acquired"] is False
    st = nodes_tool({"action": "lease_status", "lease_key": "task-x"}, ctx)
    assert st["status"] == "ok"
    assert st["exists"] is True
    r1 = nodes_tool({"action": "release_lease", "lease_key": "task-x", "node_id": "n2"}, ctx)
    assert r1["status"] == "ok"
    assert r1["released"] is False
    r2 = nodes_tool({"action": "release_lease", "lease_key": "task-x", "node_id": "n1"}, ctx)
    assert r2["status"] == "ok"
    assert r2["released"] is True
    st2 = nodes_tool({"action": "lease_status", "lease_key": "task-x"}, ctx)
    assert st2["status"] == "ok"
    assert st2["exists"] is False


def test_nodes_tool_lease_takeover_after_expire(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    nodes_tool({"action": "acquire_lease", "lease_key": "task-y", "node_id": "n1", "lease_ttl_sec": 5}, ctx)
    lease_file = tmp_path / "data" / "nodes_leases.json"
    raw = json.loads(lease_file.read_text(encoding="utf-8"))
    raw["leases"]["task-y"]["expires_at"] = 1
    lease_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    a2 = nodes_tool({"action": "acquire_lease", "lease_key": "task-y", "node_id": "n2", "lease_ttl_sec": 10}, ctx)
    assert a2["status"] == "ok"
    assert a2["acquired"] is True
    assert str((a2.get("lease") or {}).get("node_id") or "") == "n2"


def test_nodes_tool_lease_renew_and_jitter(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    a1 = nodes_tool({"action": "acquire_lease", "lease_key": "task-z", "node_id": "n1", "lease_ttl_sec": 20}, ctx)
    assert a1["status"] == "ok"
    r1 = nodes_tool(
        {"action": "renew_lease", "lease_key": "task-z", "node_id": "n1", "lease_ttl_sec": 20, "lease_jitter_sec": 3},
        ctx,
    )
    assert r1["status"] == "ok"
    assert r1["renewed"] is True
    ttl = int((r1.get("lease") or {}).get("lease_ttl_sec") or 0)
    assert 17 <= ttl <= 23


def test_nodes_tool_leader_election_respects_priority(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    low = nodes_tool({"action": "elect_leader", "group_key": "g1", "node_id": "n1", "priority": 1, "lease_ttl_sec": 40}, ctx)
    assert low["status"] == "ok"
    assert low["elected"] is True
    high = nodes_tool({"action": "elect_leader", "group_key": "g1", "node_id": "n2", "priority": 9, "lease_ttl_sec": 40}, ctx)
    assert high["status"] == "ok"
    assert high["elected"] is True
    low2 = nodes_tool({"action": "elect_leader", "group_key": "g1", "node_id": "n1", "priority": 1, "lease_ttl_sec": 40}, ctx)
    assert low2["status"] == "ok"
    assert low2["elected"] is False
    assert str(low2.get("leader_node_id") or "") == "n2"
    st = nodes_tool({"action": "lease_status", "lease_key": "leader::g1"}, ctx)
    assert st["status"] == "ok"
    assert st["exists"] is True
    assert int((st.get("lease") or {}).get("epoch") or 0) >= 1
    assert str((st.get("lease") or {}).get("fencing_token") or "").startswith("g1:")


def test_nodes_tool_leader_election_quorum_and_epoch_fencing(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
    qfail = nodes_tool({"action": "elect_leader", "group_key": "g2", "node_id": "n1", "priority": 1, "quorum": 2}, ctx)
    assert qfail["status"] == "ok"
    assert qfail["elected"] is False
    assert qfail["reason"] == "quorum_not_met"
    nodes_tool({"action": "upsert", "node_id": "n2", "host": "127.0.0.2"}, ctx)
    e1 = nodes_tool({"action": "elect_leader", "group_key": "g2", "node_id": "n1", "priority": 1, "quorum": 2}, ctx)
    assert e1["status"] == "ok"
    assert e1["elected"] is True
    ep1 = int((e1.get("lease") or {}).get("epoch") or 0)
    e2 = nodes_tool({"action": "elect_leader", "group_key": "g2", "node_id": "n2", "priority": 9, "quorum": 2}, ctx)
    assert e2["status"] == "ok"
    assert e2["elected"] is True
    ep2 = int((e2.get("lease") or {}).get("epoch") or 0)
    assert ep2 == ep1 + 1
    stale = nodes_tool(
        {"action": "elect_leader", "group_key": "g2", "node_id": "n1", "priority": 10, "quorum": 2, "expected_epoch": ep1},
        ctx,
    )
    assert stale["status"] == "ok"
    assert stale["elected"] is False
    assert stale["reason"] == "fenced_out"
    renew_stale = nodes_tool(
        {"action": "renew_lease", "lease_key": "leader::g2", "node_id": "n2", "expected_epoch": ep1, "lease_ttl_sec": 30},
        ctx,
    )
    assert renew_stale["status"] == "ok"
    assert renew_stale["renewed"] is False
    assert renew_stale["reason"] == "fenced_out"


def test_whatsapp_actions_defaults_to_dry_run() -> None:
    import asyncio

    out = asyncio.run(whatsapp_actions({"text": "hello", "dry_run": True}, None))
    assert out["status"] == "ok"
    assert out["dry_run"] is True
    assert isinstance(out.get("delivery_receipt"), dict)


def test_messaging_actions_include_delivery_receipt() -> None:
    import asyncio

    s = asyncio.run(slack_actions({"text": "x", "dry_run": True}, None))
    d = asyncio.run(discord_actions({"text": "x", "dry_run": True}, None))
    t = asyncio.run(telegram_actions({"text": "x", "dry_run": True}, None))
    assert s["delivery_receipt"]["mode"] == "dry_run"
    assert d["delivery_receipt"]["mode"] == "dry_run"
    assert t["delivery_receipt"]["mode"] == "dry_run"


def test_discord_actions_supports_thread_ingest_and_fetch(tmp_path: Path) -> None:
    import asyncio

    ctx = _ctx(tmp_path)
    ingest = asyncio.run(
        discord_actions({"action": "ingest", "thread_id": "th1", "text": "user msg", "user_id": "u1"}, ctx)
    )
    assert ingest["status"] == "ok"
    sent = asyncio.run(discord_actions({"text": "agent msg", "dry_run": True, "thread_id": "th1"}, ctx))
    assert sent["status"] == "ok"
    fetch = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "th1"}, ctx))
    assert fetch["status"] == "ok"
    assert fetch["count"] >= 2


def test_channels_listener_status(monkeypatch) -> None:
    class _LM:
        def status(self, platform=None):
            return {"status": "ok", "count": 0, "listeners": []}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    out = channels_listener_tool({"action": "status"}, None)
    assert out["status"] == "ok"
    assert out["count"] == 0


def test_channels_listener_start_routes_inbound_to_thread_store(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    ctx = _ctx(tmp_path)

    class _LM:
        def start(self, platform, config, on_message):
            from quentin.infra.channels.base import InboundMessage

            asyncio.run(
                on_message(
                    InboundMessage(
                        text="hello from inbound",
                        sender_id="u1",
                        channel_id=platform,
                        metadata={"channel_id": "c1"},
                    )
                )
            )
            return {"status": "ok", "started": True}

        def stop(self, platform):
            return {"status": "ok", "stopped": True}

        def poll(self, platform, from_seq=0, limit=100):
            return {"status": "ok", "events": [], "count": 0, "next_seq": from_seq, "latest_seq": 0}

        def status(self, platform=None):
            return {"status": "ok", "listeners": [], "count": 0}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    out = channels_listener_tool({"action": "start", "platform": "discord", "token": "x"}, ctx)
    assert out["status"] == "ok"
    threads = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "discord:c1"}, ctx))
    assert threads["status"] == "ok"
    assert threads["count"] >= 1
    assert "hello from inbound" in str(threads["messages"][-1]["text"])


def test_channels_listener_dedupes_replayed_event(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    ctx = _ctx(tmp_path)

    class _LM:
        def start(self, platform, config, on_message):
            from quentin.infra.channels.base import InboundMessage

            m1 = InboundMessage(text="same", sender_id="u1", channel_id=platform, message_id="m1", metadata={"channel_id": "c1"})
            m2 = InboundMessage(text="same", sender_id="u1", channel_id=platform, message_id="m1", metadata={"channel_id": "c1"})
            asyncio.run(on_message(m1))
            asyncio.run(on_message(m2))
            return {"status": "ok", "started": True}

        def stop(self, platform):
            return {"status": "ok", "stopped": True}

        def poll(self, platform, from_seq=0, limit=100):
            return {"status": "ok", "events": [], "count": 0, "next_seq": from_seq, "latest_seq": 0}

        def status(self, platform=None):
            return {"status": "ok", "listeners": [], "count": 0}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    channels_listener_tool({"action": "start", "platform": "discord", "token": "x"}, ctx)
    threads = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "discord:c1"}, ctx))
    assert threads["status"] == "ok"
    # one user message only due to dedupe
    user_msgs = [m for m in threads.get("messages") or [] if str(m.get("role") or "") == "user"]
    assert len(user_msgs) == 1


def test_channels_listener_applies_edit_delete_and_thread_move_events(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    ctx = _ctx(tmp_path)

    class _LM:
        def start(self, platform, config, on_message):
            from quentin.infra.channels.base import InboundMessage

            asyncio.run(
                on_message(
                    InboundMessage(
                        text="original",
                        sender_id="u1",
                        channel_id=platform,
                        message_id="m2",
                        metadata={"channel_id": "c1"},
                    )
                )
            )
            asyncio.run(
                on_message(
                    InboundMessage(
                        text="edited",
                        sender_id="u1",
                        channel_id=platform,
                        message_id="m2",
                        metadata={"channel_id": "c1", "event_kind": "edit"},
                    )
                )
            )
            asyncio.run(
                on_message(
                    InboundMessage(
                        text="",
                        sender_id="u1",
                        channel_id=platform,
                        message_id="m2",
                        metadata={"channel_id": "c1", "event_kind": "delete"},
                    )
                )
            )
            asyncio.run(
                on_message(
                    InboundMessage(
                        text="moved",
                        sender_id="u1",
                        channel_id=platform,
                        message_id="m3",
                        metadata={"channel_id": "c2", "event_kind": "thread_move", "old_thread_id": "discord:c1"},
                    )
                )
            )
            return {"status": "ok", "started": True}

        def stop(self, platform):
            return {"status": "ok", "stopped": True}

        def poll(self, platform, from_seq=0, limit=100):
            return {"status": "ok", "events": [], "count": 0, "next_seq": from_seq, "latest_seq": 0}

        def status(self, platform=None):
            return {"status": "ok", "listeners": [], "count": 0}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    channels_listener_tool({"action": "start", "platform": "discord", "token": "x"}, ctx)
    c1 = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "discord:c1"}, ctx))
    assert c1["status"] == "ok"
    assert any(str(m.get("text") or "") == "[deleted]" for m in c1.get("messages") or [])
    assert any("message moved to discord:c2" in str(m.get("text") or "") for m in c1.get("messages") or [])
    c2 = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "discord:c2"}, ctx))
    assert c2["status"] == "ok"
    assert any("message moved from discord:c1" in str(m.get("text") or "") for m in c2.get("messages") or [])


def test_channels_listener_dead_letter_view_and_clear(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    ctx = _ctx(tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("io fail")

    monkeypatch.setattr("quentin.tools.execution_parity._thread_append", _boom)

    class _LM:
        def start(self, platform, config, on_message):
            from quentin.infra.channels.base import InboundMessage

            asyncio.run(on_message(InboundMessage(text="x", sender_id="u1", channel_id=platform, message_id="m1", metadata={"channel_id": "c1"})))
            return {"status": "ok", "started": True}

        def stop(self, platform):
            return {"status": "ok", "stopped": True}

        def poll(self, platform, from_seq=0, limit=100):
            return {"status": "ok", "events": [], "count": 0, "next_seq": from_seq, "latest_seq": 0}

        def status(self, platform=None):
            return {"status": "ok", "listeners": [], "count": 0}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    channels_listener_tool({"action": "start", "platform": "discord", "token": "x"}, ctx)
    dlq = channels_listener_tool({"action": "dead_letters", "platform": "discord"}, ctx)
    assert dlq["status"] == "ok"
    assert dlq["count"] >= 1
    clr = channels_listener_tool({"action": "clear_dead_letters", "platform": "discord"}, ctx)
    assert clr["status"] == "ok"


def test_channels_listener_auto_reply_writes_outbound(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    ctx = _ctx(tmp_path)

    class _LM:
        def start(self, platform, config, on_message):
            from quentin.infra.channels.base import InboundMessage

            asyncio.run(
                on_message(
                    InboundMessage(
                        text="ping",
                        sender_id="u2",
                        channel_id=platform,
                        metadata={"channel_id": "c9"},
                    )
                )
            )
            return {"status": "ok", "started": True}

        def stop(self, platform):
            return {"status": "ok", "stopped": True}

        def poll(self, platform, from_seq=0, limit=100):
            return {"status": "ok", "events": [], "count": 0, "next_seq": from_seq, "latest_seq": 0}

        def status(self, platform=None):
            return {"status": "ok", "listeners": [], "count": 0}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    out = channels_listener_tool(
        {
            "action": "start",
            "platform": "discord",
            "token": "x",
            "auto_reply": True,
            "auto_reply_template": "ack:{text}",
        },
        ctx,
    )
    assert out["status"] == "ok"
    threads = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "discord:c9"}, ctx))
    assert threads["status"] == "ok"
    assert any("ack:ping" in str(m.get("text") or "") for m in threads.get("messages") or [])
    outbound = tmp_path / "data" / "channels" / "outbound_discord.jsonl"
    assert outbound.exists()
    assert "ack:ping" in outbound.read_text(encoding="utf-8")


def test_channels_listener_auto_reply_planner_mode(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    ctx = _ctx(tmp_path)

    def _fake_gen(**kwargs):
        return {"status": "ok", "mode": "planner", "reply": "planner says hi"}

    monkeypatch.setattr("quentin.tools.execution_parity._generate_planner_reply", _fake_gen)

    class _LM:
        def start(self, platform, config, on_message):
            from quentin.infra.channels.base import InboundMessage

            asyncio.run(
                on_message(
                    InboundMessage(
                        text="ask planner",
                        sender_id="u3",
                        channel_id=platform,
                        metadata={"channel_id": "c3"},
                    )
                )
            )
            return {"status": "ok", "started": True}

        def stop(self, platform):
            return {"status": "ok", "stopped": True}

        def poll(self, platform, from_seq=0, limit=100):
            return {"status": "ok", "events": [], "count": 0, "next_seq": from_seq, "latest_seq": 0}

        def status(self, platform=None):
            return {"status": "ok", "listeners": [], "count": 0}

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    out = channels_listener_tool(
        {"action": "start", "platform": "discord", "token": "x", "auto_reply": True, "auto_reply_mode": "planner"},
        ctx,
    )
    assert out["status"] == "ok"
    threads = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": "discord:c3"}, ctx))
    assert any("planner says hi" in str(m.get("text") or "") for m in threads.get("messages") or [])


def test_generate_planner_reply_fallback_on_error(monkeypatch) -> None:
    class _BoomContainer:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("x")

    monkeypatch.setattr("quentin.bootstrap.container.Container", _BoomContainer)
    out = _generate_planner_reply(
        text="hello",
        platform="discord",
        thread_id="discord:c1",
        fallback_template="fallback:{text}",
    )
    assert out["status"] == "ok"
    assert "fallback:hello" in str(out.get("reply") or "")
    assert "fallback" in str(out.get("mode") or "")


def test_generate_planner_reply_includes_thread_context(monkeypatch) -> None:
    captured = {"input_text": "", "metadata": {}}

    class _FakeTask:
        def __init__(self, **kwargs):
            captured["input_text"] = str(kwargs.get("input_text") or "")
            captured["metadata"] = dict(kwargs.get("metadata") or {})
            for k, v in kwargs.items():
                setattr(self, k, v)

    class _FakeLoop:
        def run_task(self, task):
            class _R:
                final_output = "ok"

            return _R()

    class _FakeContainer:
        def __init__(self, *args, **kwargs):
            self.cognitive_loop = _FakeLoop()

    monkeypatch.setattr("quentin.bootstrap.container.Container", _FakeContainer)
    monkeypatch.setattr("quentin.cognitive.loop.CognitiveTask", _FakeTask)
    out = _generate_planner_reply(
        text="latest question",
        platform="discord",
        thread_id="discord:c1",
        thread_summary="Thread summary:\n- user: objective",
        thread_history=[
            {"role": "user", "text": "hi"},
            {"role": "agent", "text": "hello"},
        ],
    )
    assert out["status"] == "ok"
    assert out["mode"] == "planner"
    assert "Thread summary:" in captured["input_text"]
    assert "Conversation context:" in captured["input_text"]
    assert "[user] hi" in captured["input_text"]
    assert "[agent] hello" in captured["input_text"]
    assert "Latest user message:" in captured["input_text"]
    assert captured["metadata"].get("history_count") == 2


def test_thread_rolls_summary_after_many_messages(tmp_path: Path) -> None:
    import asyncio

    ctx = _ctx(tmp_path)
    tid = "sum-thread"
    for i in range(45):
        asyncio.run(discord_actions({"action": "ingest", "thread_id": tid, "text": f"m{i}"}, ctx))
    out = asyncio.run(discord_actions({"action": "fetch_thread", "thread_id": tid}, ctx))
    assert out["status"] == "ok"
    assert out["count"] <= 32
    assert "Thread summary:" in str(out.get("rolling_summary") or "")


def test_merge_rolling_summary_dedupes_topic_lines() -> None:
    old = "Thread summary:\n- user: fix login timeout in oauth callback\n- agent: asked for stack trace"
    new = "Thread summary:\n- user: fix login timeout in oauth callback please\n- user: add retries for webhook delivery"
    out = _merge_rolling_summary(old, new)
    lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(lines) == 3
    assert any("oauth callback" in ln for ln in lines)
    assert any("stack trace" in ln for ln in lines)
    assert any("webhook delivery" in ln for ln in lines)


def test_merge_rolling_summary_keeps_different_intents() -> None:
    old = "Thread summary:\n- user: how to fix oauth timeout?"
    new = "Thread summary:\n- user: fix oauth timeout completed"
    out = _merge_rolling_summary(old, new)
    lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    # question vs done should not be collapsed into one.
    assert len(lines) == 2


def test_classify_summary_intent_supports_mode_switch(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_THREAD_INTENT_CLASSIFIER", "rule")
    assert _classify_summary_intent("how to fix this?") == "question"
    monkeypatch.setenv("QUENTIN_THREAD_INTENT_CLASSIFIER", "none")
    assert _classify_summary_intent("how to fix this?") == "statement"
    monkeypatch.setenv("QUENTIN_THREAD_INTENT_CLASSIFIER", "unknown_mode")
    assert _classify_summary_intent("timeout error in task") == "failure"


def test_classify_summary_intent_rules_v2(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_THREAD_INTENT_CLASSIFIER", "rules_v2")
    assert _classify_summary_intent("please update the retry policy") == "request_change"
    assert _classify_summary_intent("how should we do this?") == "request_info"
    assert _classify_summary_intent("timeout error in webhook worker") == "report_issue"
    assert _classify_summary_intent("next step is to patch adapter") == "plan"
    assert _classify_summary_intent("done, merged the fix") == "status_update"


def test_session_status_includes_listener_health(monkeypatch, tmp_path: Path) -> None:
    class _LM:
        def status(self, platform=None):
            return {
                "status": "ok",
                "count": 2,
                "listeners": [
                    {
                        "platform": "discord",
                        "status": "running",
                        "restart_reasons": {"rate_limit": 2, "network_error": 1},
                        "rate_limit_per_min": 60,
                        "backoff_profile": "exponential",
                    },
                    {
                        "platform": "slack",
                        "status": "running",
                        "restart_reasons": {"auth_error": 1},
                        "rate_limit_per_min": 45,
                        "backoff_profile": "linear",
                    },
                ],
            }

    monkeypatch.setattr("quentin.infra.channels.listener_manager.listener_manager", _LM())
    out = session_status_tool({}, _ctx(tmp_path))
    assert out["status"] == "ok"
    assert out["listener_count"] == 2
    assert len(out.get("listeners") or []) == 2
    assert int((out.get("listener_restart_reasons") or {}).get("rate_limit") or 0) == 2
    assert int((out.get("listener_restart_reasons") or {}).get("auth_error") or 0) == 1
    assert int((out.get("listener_rate_limits") or {}).get("discord") or 0) == 60
    assert str((out.get("listener_backoff_profiles") or {}).get("slack") or "") == "linear"


def test_session_status_includes_canvas_ack_health(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    c1 = canvas_tool({"action": "create", "type": "ActionCard", "props": {"title": "x"}}, ctx)
    cid = c1["component"]["component_id"]
    comp_file = tmp_path / "data" / "canvas_components.json"
    raw = json.loads(comp_file.read_text(encoding="utf-8"))
    raw["components"][cid]["updated_at"] = 1
    comp_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    out = session_status_tool({"canvas_ack_timeout_sec": 10}, ctx)
    assert out["status"] == "ok"
    assert out["canvas_active_component_count"] >= 1
    assert out["canvas_ack_pending_count"] >= 1
    assert any(str(x.get("component_id") or "") == cid for x in out.get("canvas_ack_pending") or [])
