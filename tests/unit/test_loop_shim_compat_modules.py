from __future__ import annotations

from quentin.cognitive import loop_api_shims, loop_runtime_shims
from quentin.cognitive import loop_shims, loop_tail_shims


def test_compat_module_reexports_api_shims() -> None:
    assert loop_shims.install_loop_shims is loop_api_shims.install_loop_shims


def test_compat_module_reexports_runtime_shims() -> None:
    assert loop_tail_shims.install_loop_tail_shims is loop_runtime_shims.install_loop_tail_shims
