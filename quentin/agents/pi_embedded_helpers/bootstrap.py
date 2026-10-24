from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class BootstrapContext:
    cwd: str
    user: str
    shell: str
    python: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_bootstrap_context() -> BootstrapContext:
    return BootstrapContext(
        cwd=os.getcwd(),
        user=str(os.getenv("USER") or "unknown"),
        shell=str(os.getenv("SHELL") or "unknown"),
        python=str(os.getenv("PYTHONPATH") or ""),
    )

