from quentin.memory.session_deltas import SessionDeltaWriter, SessionDeltaConfig


class _DummyMemory:
    def __init__(self):
        self.writes = []

    def remember_atomic(self, **kwargs):
        self.writes.append(kwargs)


class _AllowKernel:
    class _Result:
        allow = True
    def guard_action(self, action):
        return self._Result()


def test_session_delta_throttle() -> None:
    mem = _DummyMemory()
    cfg = SessionDeltaConfig(enabled=True, throttle_seconds=999, min_events=1, max_chars=200)
    writer = SessionDeltaWriter(memory_fabric=mem, safety_kernel=_AllowKernel(), config=cfg)

    writer.observe_execution(
        session_id="s1",
        trace_id="t1",
        attempt_index=1,
        task_domain="core",
        task_environment="sandbox",
        plan_summary="do x",
        actions_summary="did y",
        final_output="ok",
    )
    writer.observe_execution(
        session_id="s1",
        trace_id="t1",
        attempt_index=2,
        task_domain="core",
        task_environment="sandbox",
        plan_summary="do x",
        actions_summary="did y",
        final_output="ok",
    )
    assert len(mem.writes) == 1


def test_session_delta_disabled_in_prod() -> None:
    mem = _DummyMemory()
    cfg = SessionDeltaConfig(enabled=True, allow_in_prod=False)
    writer = SessionDeltaWriter(memory_fabric=mem, safety_kernel=_AllowKernel(), config=cfg)
    writer.observe_execution(
        session_id="s1",
        trace_id="t1",
        attempt_index=1,
        task_domain="core",
        task_environment="prod",
        plan_summary="do x",
        actions_summary="did y",
        final_output="ok",
    )
    assert len(mem.writes) == 0


def test_session_delta_triggers_on_message_threshold() -> None:
    mem = _DummyMemory()
    cfg = SessionDeltaConfig(
        enabled=True,
        throttle_seconds=999,
        min_events=999,  # ensure count gate alone won't trigger
        max_chars=200,
        delta_bytes=999999,
        delta_messages=2,
    )
    writer = SessionDeltaWriter(memory_fabric=mem, safety_kernel=_AllowKernel(), config=cfg)

    writer.observe_execution(
        session_id="s1",
        trace_id="t1",
        attempt_index=1,
        task_domain="core",
        task_environment="sandbox",
        plan_summary="a",
        actions_summary="b",
        final_output="c",
    )
    assert len(mem.writes) == 0

    writer.observe_execution(
        session_id="s1",
        trace_id="t1",
        attempt_index=2,
        task_domain="core",
        task_environment="sandbox",
        plan_summary="a",
        actions_summary="b",
        final_output="c",
    )
    assert len(mem.writes) == 1
