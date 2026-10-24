from __future__ import annotations

import argparse
import importlib.util
import os
import sqlite3
from pathlib import Path


def _candidate_extension_paths(path: str) -> list[Path]:
    p = Path(path).expanduser()
    if p.suffix:
        return [p]
    return [p, Path(f"{p}.dylib"), Path(f"{p}.so"), Path(f"{p}.dll")]


def _loadable_with_path(path: str) -> tuple[bool, str]:
    candidates = _candidate_extension_paths(path)
    existing = [p for p in candidates if p.exists()]
    if not existing:
        return False, f"path_not_found:{candidates[0]}"
    try:
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        load_target = existing[0]
        conn.load_extension(str(load_target))
        conn.close()
        return True, f"loaded:{load_target}"
    except Exception as e:
        return False, f"load_failed:{e}"


def _loadable_from_module() -> tuple[bool, str]:
    spec = importlib.util.find_spec("sqlite_vec")
    if spec is None:
        return False, "python_module_missing:sqlite_vec"
    try:
        import sqlite_vec  # type: ignore

        path = sqlite_vec.loadable_path()
        return _loadable_with_path(path)
    except Exception as e:
        return False, f"python_module_present_but_unusable:{e}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check sqlite-vec environment readiness.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when sqlite-vec is not loadable.",
    )
    args = parser.parse_args()

    env_path = (os.getenv("QUENTIN_SQLITE_VEC_PATH") or "").strip()
    checks = []
    if env_path:
        ok, msg = _loadable_with_path(env_path)
        checks.append({"source": "env_path", "ok": ok, "detail": msg})
        if ok:
            print({"status": "ok", "source": "env_path", "detail": msg})
            return

    ok, msg = _loadable_from_module()
    checks.append({"source": "python_module", "ok": ok, "detail": msg})
    if ok:
        print({"status": "ok", "source": "python_module", "detail": msg})
        return

    print({"status": "not_ready", "checks": checks})
    if bool(args.strict):
        raise SystemExit(5)


if __name__ == "__main__":
    main()
