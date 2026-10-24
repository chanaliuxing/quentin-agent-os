import subprocess
import logging
import time
import os
import signal
import uuid
from typing import Dict, Any, Optional, List
from quentin.infra.concurrency.cancellation import CancellationToken
from quentin.infra.concurrency.abort_signal import abort_registry

logger = logging.getLogger(__name__)
SHELL_PROTOCOL_VERSION = "v2"

def _err_with_hint(error: str, *, hint: str = "", next_actions: list[str] | None = None, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "status": "error",
        "error": error,
        "protocol_version": SHELL_PROTOCOL_VERSION,
    }
    if hint:
        out["hint"] = hint
    if next_actions:
        out["next_actions"] = list(next_actions)
    if extra:
        out.update(extra)
    return out

_SANDBOX_DRIVER = None

_SHELL_SIGNAL_MAP = {
    "SIGINT": signal.SIGINT,
    "INT": signal.SIGINT,
    "CTRL_C": signal.SIGINT,
    "SIGTERM": signal.SIGTERM,
    "TERM": signal.SIGTERM,
    "SIGKILL": signal.SIGKILL,
    "KILL": signal.SIGKILL,
}


def _normalize_signal_name(v: Any) -> str:
    return str(v or "").strip().upper()


def _resolve_signal(v: Any) -> Optional[int]:
    name = _normalize_signal_name(v)
    if not name:
        return None
    mapped = _SHELL_SIGNAL_MAP.get(name)
    if mapped is not None:
        return int(mapped)
    try:
        return int(name)
    except Exception:
        return None


def _parse_signal_ladder(params: Dict[str, Any]) -> List[int]:
    raw = params.get("signal_ladder")
    if isinstance(raw, list):
        vals = raw
    else:
        text = str(raw or "SIGINT,SIGTERM,SIGKILL")
        vals = [x.strip() for x in text.split(",") if x.strip()]
    out: List[int] = []
    for v in vals:
        sig = _resolve_signal(v)
        if sig is not None:
            out.append(sig)
    if not out:
        out = [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]
    return out


def _parse_signal_waits(params: Dict[str, Any], ladder_len: int) -> List[float]:
    raw = params.get("signal_wait_ms")
    waits: List[float] = []
    if isinstance(raw, list):
        try:
            waits = [max(0.0, float(x) / 1000.0) for x in raw]
        except Exception:
            waits = []
    elif raw is not None:
        try:
            one = max(0.0, float(raw) / 1000.0)
            waits = [one for _ in range(max(0, ladder_len - 1))]
        except Exception:
            waits = []
    if not waits:
        waits = [0.15 for _ in range(max(0, ladder_len - 1))]
    if len(waits) < max(0, ladder_len - 1):
        waits = waits + [waits[-1] if waits else 0.15] * (ladder_len - 1 - len(waits))
    return waits[: max(0, ladder_len - 1)]

def shell_run_command(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    global _SANDBOX_DRIVER
    command = params.get("command")
    if not command:
        return _err_with_hint("Missing command", hint="Provide a non-empty shell command string.")

    # P0: Idempotent mkdir optimization (reduce redundant "mkdir -p" noise)
    # This is a best-effort fast path; it does not change correctness.
    try:
        import re
        from pathlib import Path

        m = re.fullmatch(r"\s*mkdir\s+-p\s+([^\s;&|]+)\s*", str(command))
        if m:
            target = Path(m.group(1)).expanduser()
            if target.exists() and target.is_dir():
                return {
                    "status": "ok",
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "result": f"skipped: directory already exists: {target}",
                    "skipped": True,
                    "skip_reason": "already_exists",
                }
    except Exception:
        pass

    # P5: Docker Isolation
    if os.getenv("QUENTIN_SANDBOX_ENABLED", "0") == "1":
        if _SANDBOX_DRIVER is None:
            from quentin.infra.sandbox.docker_driver import DockerSandboxDriver
            _SANDBOX_DRIVER = DockerSandboxDriver()
            if _SANDBOX_DRIVER.is_available():
                _SANDBOX_DRIVER.start(os.getcwd())
            else:
                return _err_with_hint("Docker unavailable", hint="Start Docker or disable sandbox mode.")
        
        exit_code, stdout, stderr = _SANDBOX_DRIVER.exec_run(command)
        return {
            "status": "ok" if exit_code == 0 else "error",
            "returncode": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "result": stdout if exit_code == 0 else stderr
        }

    # --- [6.2.2] Enhanced Non-Interactive Guard ---
    interactive_commands = {"nano", "vim", "vi", "emacs", "top", "htop", "less", "more", "man"}
    import re
    for cmd in interactive_commands:
        # Match pattern: start of line or separator, followed by optional path, then the command, then space or end of line
        pattern = rf"(^|[;&|])\s*(\S+/)?{cmd}(\s+|$)"
        if re.search(pattern, command):
            return _err_with_hint(
                f"Interactive command '{cmd}' detected and blocked in automation. "
                f"Use non-interactive tools like 'fs.write_file', 'grep', or 'cat' instead.",
                hint="Interactive TTY programs are not supported by the automation runtime.",
                next_actions=["Replace with non-interactive equivalent command."],
            )
        
    cancel_token: Optional[CancellationToken] = None
    session_id: Optional[str] = None
    if context:
        if hasattr(context, "cancel_token"):
            cancel_token = context.cancel_token
        if hasattr(context, "metadata") and isinstance(context.metadata, dict):
            session_id = context.metadata.get("session_id")
        elif isinstance(context, dict):
            session_id = context.get("session_id")

    # P5: Surgery Sixty-two - Mode Auto-degradation (OpenClaw Parity)
    is_restricted = params.get("_restricted_mode", False)
    
    # P5: Surgery Seventy-five - Kernel-level Isolation (OpenClaw Parity)
    from quentin.infra.isolation.kernel_isolator import KernelIsolator
    wrapped_command = KernelIsolator.wrap_command(command, restricted=is_restricted)
    signal_ladder = _parse_signal_ladder(params)
    signal_waits = _parse_signal_waits(params, len(signal_ladder))

    try:
        # Start the process in a new process group
        process = subprocess.Popen(
            wrapped_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            start_new_session=True 
        )
        
        # P5: OpenClaw Parity - Immediate Abort Callback
        if session_id:
            abort_sig = abort_registry.get_signal(session_id)
            if abort_sig.is_aborted:
                _kill_process_group(process.pid)
                return _err_with_hint("Process aborted immediately by session signal", aborted=True)
            
            def _on_signal_abort(reason):
                logger.warning(f"ShellTool: killing process {process.pid} due to session abort: {reason}")
                _apply_signal_ladder(
                    process.pid,
                    signal_ladder=signal_ladder,
                    waits_sec=signal_waits,
                    reason="abort_signal",
                )
            
            abort_sig.on_abort(_on_signal_abort)

        # Optional background mode: return quickly with proc_id for interactive control.
        try:
            yield_seconds = float(params.get("yield_seconds") or 0.0)
        except Exception:
            yield_seconds = 0.0
        if yield_seconds > 0:
            from quentin.infra.terminal.process_manager import process_manager

            proc_id = process_manager.register(process, str(command))
            deadline = time.time() + max(0.05, yield_seconds)
            while process.poll() is None and time.time() < deadline:
                time.sleep(0.05)
            bg = process_manager.get(proc_id)
            stdout_preview = "".join((bg.stdout_buffer if bg else [])[-20:]) if bg else ""
            stderr_preview = "".join((bg.stderr_buffer if bg else [])[-20:]) if bg else ""
            if process.poll() is None:
                return {
                    "status": "running",
                    "phase": "running",
                    "mode": "background",
                    "protocol_version": SHELL_PROTOCOL_VERSION,
                    "proc_id": proc_id,
                    "execution_id": proc_id,
                    "is_running": True,
                    "stdout": stdout_preview,
                    "stderr": stderr_preview,
                    "result": stdout_preview,
                }
            exit_code = process.returncode
            return {
                "status": "ok" if int(exit_code or 0) == 0 else "error",
                "phase": "exited",
                "mode": "background",
                "protocol_version": SHELL_PROTOCOL_VERSION,
                "proc_id": proc_id,
                "execution_id": proc_id,
                "is_running": False,
                "returncode": exit_code,
                "stdout": stdout_preview,
                "stderr": stderr_preview,
                "result": stdout_preview if int(exit_code or 0) == 0 else stderr_preview,
            }
        
        # Periodic check for cancellation and timeout
        command_l = str(command).strip().lower()
        timeout = params.get("timeout_seconds")
        if timeout is None:
            if command_l.startswith("gemini ") or " gemini " in command_l:
                timeout = os.getenv("QUENTIN_SHELL_TIMEOUT_GEMINI_S", "900")
        if timeout is None or str(timeout).strip() == "":
            timeout = 120
        try:
            timeout = float(timeout)
        except Exception:
            timeout = 120.0
        start_time = time.time()
        last_output_time = time.time()
        last_wall_ts = start_time
        stalled_clock_ticks = 0
        
        # Use selector or poll if we needed streaming, but for simple daemon:
        while process.poll() is None:
            now_ts = time.time()
            if now_ts <= last_wall_ts:
                stalled_clock_ticks += 1
            else:
                stalled_clock_ticks = 0
                last_wall_ts = now_ts
            # Safety hatch for test/mocked environments where clock is frozen
            # and sleep may be patched to no-op, preventing timeout progression.
            if stalled_clock_ticks > 5000:
                logger.warning("ShellTool: detected stalled clock while process is still running; forcing graceful stop.")
                _apply_signal_ladder(
                    process.pid,
                    signal_ladder=signal_ladder,
                    waits_sec=signal_waits,
                    reason="stalled_clock",
                )
                return _err_with_hint(
                    "Command timed out (stalled clock safeguard)",
                    hint="Execution clock did not progress; process was stopped safely.",
                    next_actions=["Retry command.", "Check timer/runtime hooks."],
                    timeout_seconds=timeout,
                )
            # 1. Check for global cancellation
            if cancel_token and cancel_token.is_cancelled():
                logger.warning(f"ShellTool: Aborting process tree (cancel signal): {command}")
                _apply_signal_ladder(
                    process.pid,
                    signal_ladder=signal_ladder,
                    waits_sec=signal_waits,
                    reason="cancelled",
                )
                return _err_with_hint(
                    f"Command aborted: {cancel_token.reason() or 'Unknown reason'}",
                    hint="The task was cancelled during command execution.",
                    next_actions=["Retry if cancellation was accidental.", "Run a narrower command scope."],
                    aborted=True,
                )
            
            # 2. Check for absolute timeout
            if timeout > 0 and (now_ts - start_time > timeout):
                logger.warning(f"ShellTool: Killing timed-out process ({timeout}s): {command}")
                _apply_signal_ladder(
                    process.pid,
                    signal_ladder=signal_ladder,
                    waits_sec=signal_waits,
                    reason="timeout",
                )
                return _err_with_hint(
                    f"Command timed out after {timeout}s",
                    hint="The command exceeded the shell tool timeout budget.",
                    next_actions=["Limit command scope.", "Split into smaller commands."],
                    timeout_seconds=timeout,
                )
            
            # 3. Best-effort activity check (Future: read buffers asynchronously)
            time.sleep(0.2)
            
        stdout, stderr = process.communicate()
        
        return {
            "status": "ok" if process.returncode == 0 else "error",
            "phase": "exited",
            "mode": "foreground",
            "protocol_version": SHELL_PROTOCOL_VERSION,
            "execution_id": f"fg_{uuid.uuid4().hex[:12]}",
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "result": stdout if process.returncode == 0 else stderr
        }
    except Exception as e:
        return _err_with_hint(str(e))

def shell_ls(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path = params.get("path", ".")
    return shell_run_command({"command": f"ls -F {path}"}, context)

def shell_cat(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path = params.get("path")
    if not path:
        return _err_with_hint("Missing path", hint="Specify file path to read.")
    return shell_run_command({"command": f"cat {path}"}, context)

def shell_grep(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    pattern = params.get("pattern")
    path = params.get("path", ".")
    if not pattern:
        return _err_with_hint("Missing pattern", hint="Specify text pattern to search.")
    return shell_run_command({"command": f"grep -r {pattern} {path}"}, context)

def shell_poll_results(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's background polling.
    Fetches latest stdout/stderr and interaction state.
    """
    proc_id = params.get("proc_id")
    if not proc_id:
        return _err_with_hint("Missing proc_id", hint="Provide the ID returned by shell_run_command (if yield_seconds was used).")
        
    from quentin.infra.terminal.process_manager import process_manager
    proc = process_manager.get(proc_id)
    if not proc:
        return _err_with_hint(f"Process {proc_id} not found", hint="The process might have been cleaned up or ID is invalid.")
        
    status = proc.get_status()
    # P5: Surgery Sixty-four - Interaction State Passthrough (OpenClaw Parity)
    waiting_for_input = getattr(proc, "waiting_for_input", False)
    last_prompt = getattr(proc, "last_prompt", "")
    
    # ANSI Hygiene
    from quentin.infra.terminal.ansi_sanitizer import AnsiSanitizer
    stdout = "".join(proc.stdout_buffer)
    stderr = "".join(proc.stderr_buffer)
    max_output_chars = int(params.get("max_output_chars") or 20000)
    if max_output_chars > 0:
        if len(stdout) > max_output_chars:
            stdout = stdout[-max_output_chars:]
        if len(stderr) > max_output_chars:
            stderr = stderr[-max_output_chars:]
    cursor = int(params.get("cursor") or 0)
    if cursor < 0:
        cursor = 0
    stdout_delta = stdout[cursor:] if cursor <= len(stdout) else ""
    next_cursor = len(stdout)
    from_seq = int(params.get("from_seq") or 0)
    max_lines = int(params.get("max_lines") or 200)
    seq_block = proc.slice_stdout_events(from_seq=from_seq, max_lines=max_lines)
    tail_lines = int(params.get("tail_lines") or 0)
    stdout_tail = ""
    if tail_lines > 0:
        stdout_tail = "".join(proc.stdout_buffer[-max(1, tail_lines):])

    res = {
        "status": "ok" if not waiting_for_input else "waiting_for_input",
        "phase": str(status.get("phase") or ("running" if status["is_running"] else "exited")),
        "mode": "background",
        "protocol_version": SHELL_PROTOCOL_VERSION,
        "proc_id": proc_id,
        "execution_id": proc_id,
        "is_running": status["is_running"],
        "stdout": AnsiSanitizer.sanitize(stdout),
        "stdout_delta": AnsiSanitizer.sanitize(stdout_delta),
        "stdout_tail": AnsiSanitizer.sanitize(stdout_tail),
        "cursor": cursor,
        "next_cursor": next_cursor,
        "stdout_events": [
            {"seq": int(e.get("seq") or 0), "line": AnsiSanitizer.sanitize(str(e.get("line") or ""))}
            for e in list(seq_block.get("events") or [])
        ],
        "from_seq": from_seq,
        "next_seq": int(seq_block.get("next_seq") or from_seq),
        "latest_seq": int(seq_block.get("latest_seq") or 0),
        "stderr": AnsiSanitizer.sanitize(stderr),
        "exit_code": status["exit_code"],
        "last_prompt": str(status.get("last_prompt") or ""),
    }
    if waiting_for_input:
        res["hint"] = f"Terminal is waiting for input: '{last_prompt}'. Use 'shell.send_input' to respond."
        
    return res

def shell_send_input(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's interactive input.
    Sends text to a background process and records it for replay.
    """
    proc_id = params.get("proc_id")
    text = params.get("text")
    if not proc_id or text is None:
        return _err_with_hint("Missing proc_id or text", hint="Provide the target process ID and the string to send.")
        
    from quentin.infra.terminal.process_manager import process_manager
    proc = process_manager.get(proc_id)
    if not proc:
        return _err_with_hint(f"Process {proc_id} not found")
        
    # P5: Surgery Sixty-nine - Record for Replay before physical write
    current_view = "".join(proc.stdout_buffer[-3:]) # Snapshot last 3 lines
    replay_key = str(params.get("replay_key") or "").strip()
    if replay_key and not proc.mark_replay_key(replay_key):
        return {
            "status": "ok",
            "phase": str(proc.get_status().get("phase") or "running"),
            "mode": "background",
            "protocol_version": SHELL_PROTOCOL_VERSION,
            "proc_id": proc_id,
            "execution_id": proc_id,
            "deduped": True,
            "replay_key": replay_key,
            "result": "duplicate replay_key ignored",
        }
    proc.replay_buffer.record_step(text, current_view)
    
    # P5: Surgery Seventy - Register echo candidate
    if hasattr(proc, "echo_sanitizer"):
        proc.echo_sanitizer.register_command(text)
    
    try:
        # Atomic Stdin Write
        if proc.process.stdin:
            proc.process.stdin.write(text + "\n")
            proc.process.stdin.flush()
            input_seq = proc.next_input_seq()
            return {
                "status": "ok",
                "phase": str(proc.get_status().get("phase") or "running"),
                "mode": "background",
                "protocol_version": SHELL_PROTOCOL_VERSION,
                "proc_id": proc_id,
                "execution_id": proc_id,
                "input_seq": int(input_seq),
                "replay_safe": bool(replay_key),
                "replay_key": replay_key if replay_key else None,
                "result": f"Sent input to {proc_id}",
            }
        else:
            return {"status": "error", "error": "Process stdin is not available (check if it was started with PIPE)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def shell_send_signal(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    OpenClaw-parity signal forwarding to background PTY process.
    """
    _ = context
    proc_id = params.get("proc_id")
    raw = _normalize_signal_name(params.get("signal") or "SIGINT")
    action = str(params.get("action") or "signal").strip().lower()
    if not proc_id:
        return _err_with_hint("Missing proc_id", hint="Provide process id returned by shell.run_command.")
    sig = _resolve_signal(raw)
    if sig is None:
        return _err_with_hint(f"Unknown signal: {raw}", hint="Use SIGINT/SIGTERM/SIGKILL or numeric signal.")

    from quentin.infra.terminal.process_manager import process_manager
    proc = process_manager.get(str(proc_id))
    if not proc:
        return _err_with_hint(f"Process {proc_id} not found")
    try:
        if action == "graceful_stop":
            ladder = _parse_signal_ladder(params)
            waits = _parse_signal_waits(params, len(ladder))
            _apply_signal_ladder(
                proc.process.pid,
                signal_ladder=ladder,
                waits_sec=waits,
                reason="graceful_stop",
            )
            raw = ",".join([str(s) for s in ladder])
            sig = ladder[-1]
        else:
            _signal_process_group(proc.process.pid, int(sig))
        return {
            "status": "ok",
            "phase": "running" if proc.process.poll() is None else "exited",
            "mode": "background",
            "protocol_version": SHELL_PROTOCOL_VERSION,
            "proc_id": proc_id,
            "execution_id": proc_id,
            "action": action,
            "signal": raw,
            "signal_num": int(sig),
        }
    except Exception as e:
        return _err_with_hint(f"Failed to send signal: {e}")

def shell_mkdir(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path = params.get("path")
    if not path:
        return _err_with_hint("Missing path", hint="Specify directory path to create.")
    
    # P1: Prevent usage on files (Graceful Softening)
    if any(str(path).endswith(ext) for ext in (".py", ".yaml", ".yml", ".json", ".md", ".txt", ".sh", ".toml", ".ini")):
        from pathlib import Path
        parent = Path(str(path)).parent
        if str(parent) != ".":
            logger.info(f"ShellTool: Softening mkdir for file-like path {path} -> {parent}")
            res = shell_run_command({"command": f"mkdir -p {parent}"}, context)
            if res.get("status") == "ok":
                res["hint"] = f"Note: '{path}' looks like a file. I've created the parent directory '{parent}' instead. Reminder: `fs.write_file` creates parent directories automatically."
            return res
        else:
            return _err_with_hint(
                f"mkdir path looks like a file: {path}",
                hint="mkdir is ONLY for directories. To create a file with content, use 'fs.write_file' instead.",
                next_actions=["Use fs.write_file for file creation."]
            )

    return shell_run_command({"command": f"mkdir -p {path}"}, context)

def interactive_shell_tool(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    # Placeholder for persistent shell interaction
    return {
        "status": "error",
        "error": "Interactive shell session not yet implemented.",
        "hint": "Use shell.run_command for single command execution."
    }

def _kill_process_group(pid: int):
    # Compatibility helper used by legacy tests/hooks.
    _signal_process_group(pid, signal.SIGKILL)


def _signal_process_group(pid: int, sig: int) -> None:
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass
    except Exception:
        # Fallback to direct signal on process
        try:
            os.kill(pid, sig)
        except Exception:
            pass


def _graceful_stop_process_group(pid: int, *, reason: str = "") -> None:
    # Gentle ladder: SIGINT -> SIGTERM -> SIGKILL
    _apply_signal_ladder(
        pid,
        signal_ladder=[signal.SIGINT, signal.SIGTERM, signal.SIGKILL],
        waits_sec=[0.15, 0.15],
        reason=reason,
    )


def _apply_signal_ladder(
    pid: int,
    *,
    signal_ladder: List[int],
    waits_sec: List[float],
    reason: str = "",
) -> None:
    _ = reason
    if not signal_ladder:
        _kill_process_group(pid)
        return
    for i, sig in enumerate(signal_ladder):
        _signal_process_group(pid, int(sig))
        if i < len(waits_sec):
            time.sleep(max(0.0, float(waits_sec[i])))
