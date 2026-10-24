from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

from quentin.blueprint.spec import load_default_spec_v3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="blueprints/meta_agent_v3.yaml", help="output yaml path")
    args = ap.parse_args()

    spec = load_default_spec_v3()
    obj: Dict[str, Any] = {
        "version": spec.version,
        "codename": spec.codename,
        "capabilities": [c.to_dict() for c in spec.capabilities],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml

        out_path.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        # Fallback: very simple YAML-ish dump.
        lines = [f"version: {obj['version']}", f"codename: {obj['codename']}", "capabilities:"]
        for c in obj["capabilities"]:
            lines.append(f"  - id: {c['id']}")
            lines.append(f"    section: {c['section']}")
            lines.append(f"    name: {c['name']}")
            lines.append(f"    description: {c['description']}")
            lines.append(f"    required: {str(bool(c.get('required', True))).lower()}")
            lines.append(f"    maturity_target: {c.get('maturity_target')}")
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(str(out_path))


if __name__ == "__main__":
    main()

