#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT_DIR / "templates" / "agent_project_skeleton"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target_dir).resolve()
    if target.exists() and any(target.iterdir()) and not args.force:
        raise SystemExit(f"target exists and is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    _copy_tree(TEMPLATE_DIR, target)
    manifest = target / "project_manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"project_id={args.project_id}",
                f"template={TEMPLATE_DIR}",
                "initialized=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(target)
    return 0


def _copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        out = target / rel
        if path.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        if out.suffix == ".sh":
            out.chmod(0o755)


if __name__ == "__main__":
    raise SystemExit(main())
