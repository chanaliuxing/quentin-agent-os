from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path

from dotenv import load_dotenv
from quentin.memory.fabric import MemoryFabric


def _probe_runtime(repo_root: Path, strict: bool, q: mp.Queue) -> None:
    try:
        store_env = str(os.getenv("QUENTIN_MEMORY_STORE") or "").strip().lower()
        if store_env != "champion":
            q.put(
                (
                    7,
                    {
                        "status": "not_ready",
                        "reason": "memory_store_not_champion",
                        "QUENTIN_MEMORY_STORE": store_env or None,
                    },
                )
            )
            return

        fabric = MemoryFabric(repo_root=repo_root)
        stats = fabric.stats()
        store_name = str(stats.get("store") or "")
        vec = stats.get("vector") if isinstance(stats.get("vector"), dict) else {}
        vec_backend = str((vec or {}).get("backend") or "")
        vec_ready = bool((vec or {}).get("ready"))

        ok = True
        reasons: list[str] = []
        if store_name != "ChampionMemoryStore":
            ok = False
            reasons.append(f"store={store_name}")
        if vec_backend != "qdrant":
            ok = False
            reasons.append(f"vector_backend={vec_backend}")
        if bool(strict) and (not vec_ready):
            ok = False
            reasons.append("vector_not_ready")

        status = "ok" if ok else "not_ready"
        payload = {
            "status": status,
            "store": store_name,
            "vector_backend": vec_backend,
            "vector_ready": vec_ready,
            "reasons": reasons,
        }
        q.put((0 if ok else 8, payload))
    except Exception as e:  # noqa: BLE001
        q.put((9, {"status": "not_ready", "reason": "runtime_probe_exception", "error": repr(e)}))


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=repo_root / ".env", override=False)

    parser = argparse.ArgumentParser(description="Verify Champion runtime is explicitly enabled and active.")
    parser.add_argument("--strict", action="store_true", help="Require qdrant vector backend ready.")
    parser.add_argument("--timeout-sec", type=int, default=30, help="Timeout for runtime probe.")
    args = parser.parse_args()
    q: mp.Queue = mp.Queue(maxsize=1)
    proc = mp.Process(target=_probe_runtime, args=(repo_root, bool(args.strict), q), daemon=True)
    proc.start()
    proc.join(timeout=max(1, int(args.timeout_sec or 30)))
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=3.0)
        print(json.dumps({"status": "not_ready", "reason": "runtime_probe_timeout"}, ensure_ascii=False))
        return 10
    if q.empty():
        print(json.dumps({"status": "not_ready", "reason": "runtime_probe_no_result"}, ensure_ascii=False))
        return 11
    rc, payload = q.get()
    print(json.dumps(payload, ensure_ascii=False))
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
