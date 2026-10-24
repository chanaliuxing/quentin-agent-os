import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def check(obj, methods, name):
    missing = [m for m in methods if not hasattr(obj, m)]
    if missing:
        print("FAILED: " + name + " missing " + str(missing))
        return False
    print("OK: " + name)
    return True

def run():
    from quentin.runtime.system_events import system_events
    s_ok = check(system_events, ["consume_pending", "enqueue_event"], "SystemEvents")

    from quentin.tools.manager import ToolManager
    tm = ToolManager()
    t_ok = check(tm, ["call_tool", "add_before_hook", "set_global_policy"], "ToolManager")

    from quentin.execution.skill_executor import Executor
    exe = Executor(repo_root=".", model_router=None, tool_manager=tm)
    e_ok = check(exe, ["run_step"], "Executor")

    from quentin.cognitive.loop_impl import CognitiveLoop
    print("CognitiveLoop: OK")

    if not (s_ok and t_ok and e_ok):
        sys.exit(1)

if __name__ == "__main__":
    run()
    print("INTEGRITY_PASSED")
