from pathlib import Path
from typing import List, Optional
import os

class PathGuard:
    """
    Security Guard: Ensures file operations are restricted to allowed directories.
    """
    def __init__(self, repo_root: Path, allowed_roots: Optional[List[str]] = None):
        self.repo_root = repo_root.resolve()
        # Default roots are conservative and aligned with blueprint v3:
        # - self-programming is restricted to explicitly mutable areas.
        if allowed_roots is None:
            # Conservative defaults (unit-test contract):
            # - allow mutations only in explicitly "safe" write areas.
            self.allowed_roots = [
                "mutable",
                "generated",
                "extensions/tools",
                "quentin/mutable",
                "quentin/skills",
                "meta_agent/tools",
            ]
            self.allowed_roots.extend(self._extra_allowed_roots_from_env())
        else:
            # Allow callers to explicitly disable root restrictions by passing [].
            self.allowed_roots = list(allowed_roots)

        self.allowed_roots = self._normalize_roots(self.allowed_roots)

    @staticmethod
    def _extra_allowed_roots_from_env() -> List[str]:
        raw = str(os.getenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", "") or "").strip()
        if not raw:
            return []
        extras: List[str] = []
        for item in raw.split(","):
            value = item.strip().strip("/")
            if value:
                extras.append(value)
        return extras

    @staticmethod
    def _normalize_roots(roots: List[str]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for root in roots:
            v = str(root or "").strip().replace("\\", "/").strip("/")
            if not v or v in seen:
                continue
            seen.add(v)
            normalized.append(v)
        return normalized

    @staticmethod
    def _is_under_allowed_root(rel_path: Path, allowed_root: str) -> bool:
        prefix = Path(allowed_root)
        rel_parts = rel_path.parts
        prefix_parts = prefix.parts
        if len(prefix_parts) > len(rel_parts):
            return False
        return rel_parts[: len(prefix_parts)] == prefix_parts

    def ensure_allowed_path(self, rel_path: str) -> Path:
        """
        Validates that the given relative path points to a file inside the allowed roots.
        Returns the absolute resolved path.
        """
        path_obj = Path(rel_path)
        if path_obj.is_absolute():
            raise ValueError(f"Absolute path not allowed: {rel_path}")

        # Resolve patch target relative to repo root
        abs_path = (self.repo_root / path_obj).resolve()

        # 1. Must be under repo_root
        if self.repo_root not in abs_path.parents and abs_path != self.repo_root:
             raise ValueError(f"Target file outside repo_root: {abs_path}")

        # 2. Must match allowed roots
        if self.allowed_roots:
            # We check relative path against allowed prefixes
            try:
                rel_to_root = abs_path.relative_to(self.repo_root)
            except ValueError:
                 raise ValueError(f"Target path {abs_path} is not relative to repo root {self.repo_root}")

            norm_rel_str = str(rel_to_root).replace("\\\\", "/")
            if not any(self._is_under_allowed_root(rel_to_root, prefix) for prefix in self.allowed_roots):
                raise ValueError(
                    f"Target file '{norm_rel_str}' is not under allowed roots: {self.allowed_roots}"
                )

        return abs_path
