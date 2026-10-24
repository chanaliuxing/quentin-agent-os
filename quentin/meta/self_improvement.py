from __future__ import annotations

"""
Compatibility wrapper.

This module previously contained an experimental/legacy self-improvement manager with
unfinished patch generation logic. The canonical implementation lives under
`quentin/self_improvement/manager.py`.
"""

from quentin.self_improvement.manager import SelfImprovementManager

__all__ = ["SelfImprovementManager"]

