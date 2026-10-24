from __future__ import annotations
import uuid
import time
import subprocess
import threading
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class BackgroundProcess:
    def __init__(self, process: subprocess.Popen, command: str):
        self.id = f"proc_{uuid.uuid4().hex[:8]}"
        self.process = process
        self.command = command
        self.start_time = time.time()
        self.stdout_buffer: List[str] = []
        self.stderr_buffer: List[str] = []
        self.stdout_events: List[Dict[str, Any]] = []
        self._stdout_seq: int = 0
        self._input_seq: int = 0
        self._stop_event = threading.Event()
        self.waiting_for_input = False # P5: Interaction State
        self.last_prompt = ""
        self._replay_keys: set[str] = set()
        
        # P5: Surgery Seventy - Echo Sanitization (OpenClaw Parity)
        from quentin.utils.echo_sanitizer import EchoSanitizer
        self.echo_sanitizer = EchoSanitizer()
        self.echo_sanitizer.register_command(command) # Initial command is an echo candidate
        
        # P5: Surgery Sixty-nine - Replay Support (OpenClaw Parity)
        from quentin.infra.terminal.replay_buffer import ReplayBuffer
        self.replay_buffer = ReplayBuffer()
        
        # Thread to drain buffers without blocking
        self.drain_thread = threading.Thread(target=self._drain_io, daemon=True)
        self.drain_thread.start()

    def next_input_seq(self) -> int:
        self._input_seq += 1
        return self._input_seq

    def mark_replay_key(self, key: str) -> bool:
        """
        Returns True when key is new and recorded; False when duplicate.
        """
        k = str(key or "").strip()
        if not k:
            return True
        if k in self._replay_keys:
            return False
        self._replay_keys.add(k)
        # Keep memory bounded.
        if len(self._replay_keys) > 256:
            self._replay_keys = set(list(self._replay_keys)[-128:])
        return True

    def slice_stdout_events(self, from_seq: int = 0, max_lines: int = 200) -> Dict[str, Any]:
        fs = max(0, int(from_seq or 0))
        ml = max(1, int(max_lines or 200))
        events = [e for e in self.stdout_events if int(e.get("seq") or 0) > fs][:ml]
        next_seq = fs
        if events:
            next_seq = int(events[-1].get("seq") or fs)
        return {
            "events": events,
            "next_seq": next_seq,
            "latest_seq": int(self._stdout_seq),
        }

    async def replay_steps(self, steps: List[Any]):
        """
        Physically re-injects stdin based on history with hash verification.
        """
        import hashlib
        for step in steps:
            # 1. Verify physical state before injection
            current_tail = "".join(self.stdout_buffer[-2:]) # Last 2 lines
            current_hash = hashlib.md5(current_tail.strip().encode("utf-8")).hexdigest()
            
            if current_hash != step.expected_prompt_hash:
                logger.error(f"Replay: PHYSICAL DRIFT detected at step {step.step_index}. Aborting.")
                raise RuntimeError(f"replay_failed: drift at step {step.step_index}")
            
            # 2. Inject stdin (Turbo Mode)
            self.process.stdin.write(step.input_text + "\n")
            self.process.stdin.flush()
            # Give short time for process to react
            await asyncio.sleep(0.1) 

    def _drain_io(self):
        # Non-blocking read from process pipes
        from quentin.utils.stream_utils import StreamUtils
        from quentin.utils.terminal_detector import TerminalDetector
        last_hash = None
        
        while self.process.poll() is None and not self._stop_event.is_set():
            line = self.process.stdout.readline()
            if line:
                # P5: Surgery Seventy - Filter command echoes (OpenClaw Parity)
                if self.echo_sanitizer.is_echo(line):
                    continue

                # P5: Surgery Sixty-four - Interaction Detection (OpenClaw Parity)
                if TerminalDetector.is_waiting_for_input(line):
                    self.waiting_for_input = True
                    self.last_prompt = TerminalDetector.get_prompt_hint(line)
                else:
                    self.waiting_for_input = False

                # P5: Surgery Sixty-one - Stream Hashing & Collapsing (OpenClaw Parity)
                current_hash = StreamUtils.get_semantic_hash(line)
                
                if StreamUtils.should_collapse(last_hash, current_hash) and self.stdout_buffer:
                    # Physically update last line instead of appending
                    # This keeps progress updates in a single evolving line
                    self.stdout_buffer[-1] = f"[Progress] {line.strip()}\n"
                    self._stdout_seq += 1
                    self.stdout_events.append({"seq": self._stdout_seq, "line": self.stdout_buffer[-1]})
                else:
                    self.stdout_buffer.append(line)
                    self._stdout_seq += 1
                    self.stdout_events.append({"seq": self._stdout_seq, "line": line})
                    last_hash = current_hash
                if len(self.stdout_events) > 3000:
                    self.stdout_events = self.stdout_events[-1500:]
                    
            err = self.process.stderr.readline()
            if err: self.stderr_buffer.append(err)
            
    def get_status(self) -> Dict[str, Any]:
        is_running = self.process.poll() is None
        if is_running and self.waiting_for_input:
            phase = "waiting_input"
        elif is_running and (time.time() - self.start_time) < 0.3 and len(self.stdout_buffer) == 0:
            phase = "starting"
        elif is_running:
            phase = "running"
        else:
            phase = "error" if int(self.process.returncode or 0) != 0 else "exited"
        return {
            "id": self.id,
            "command": self.command,
            "is_running": is_running,
            "exit_code": self.process.returncode,
            "phase": phase,
            "uptime_sec": int(time.time() - self.start_time),
            "stdout_len": len(self.stdout_buffer),
            "stderr_len": len(self.stderr_buffer),
            "stdout_seq": int(self._stdout_seq),
            "input_seq": int(self._input_seq),
            "last_prompt": str(self.last_prompt or ""),
        }

    def terminate(self):
        self._stop_event.set()
        if self.process.poll() is None:
            self.process.terminate()

class ProcessManager:
    """
    P5: Ported from OpenClaw's background process registry.
    Manages long-running detached shell tasks.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProcessManager, cls).__new__(cls)
            cls._instance.processes: Dict[str, BackgroundProcess] = {}
        return cls._instance

    def register(self, process: subprocess.Popen, command: str) -> str:
        bg_proc = BackgroundProcess(process, command)
        self.processes[bg_proc.id] = bg_proc
        return bg_proc.id

    def get(self, proc_id: str) -> Optional[BackgroundProcess]:
        return self.processes.get(proc_id)

    def cleanup(self):
        """Kills all background tasks on system shutdown."""
        for p in self.processes.values():
            p.terminate()
        self.processes.clear()

process_manager = ProcessManager()
