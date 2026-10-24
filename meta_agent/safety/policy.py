# meta_agent/safety/policy.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Pattern
from pathlib import Path
import re


@dataclass
class SafetyPolicy:
    """
    安全策略 v1：
    - 路径白名单 / 黑名单
    - 高风险路径 / 模式
    - 最大 diff 行数
    """
    allowed_roots: List[Path] = field(default_factory=list)
    forbidden_roots: List[Path] = field(default_factory=list)
    high_risk_roots: List[Path] = field(default_factory=list)

    filename_high_risk_patterns: List[Pattern] = field(default_factory=list)
    max_diff_lines: int = 300  # 一次 patch 最多改多少行
    max_files_per_patch: int = 20

    def is_path_allowed(self, path: Path) -> bool:
        # 在 forbidden_roots 下面 → 直接否
        for root in self.forbidden_roots:
            try:
                if path.resolve().is_relative_to(root.resolve()):
                    return False
            except AttributeError:
                # Python<3.9 没有 is_relative_to，用 try/except 兼容也行
                try:
                    path.resolve().relative_to(root.resolve())
                    return False
                except ValueError:
                    pass

        # 如果配置了 allowed_roots，则必须在这些根路径之下
        if self.allowed_roots:
            for root in self.allowed_roots:
                try:
                    if path.resolve().is_relative_to(root.resolve()):
                        return True
                except AttributeError:
                    try:
                        path.resolve().relative_to(root.resolve())
                        return True
                    except ValueError:
                        continue
            return False

        # 没配 allowed_roots 就默认允许（不推荐生产这么用）
        return True

    def is_path_high_risk(self, path: Path) -> bool:
        # 在 high_risk_roots 之下 → 高风险
        for root in self.high_risk_roots:
            try:
                if path.resolve().is_relative_to(root.resolve()):
                    return True
            except AttributeError:
                try:
                    path.resolve().relative_to(root.resolve())
                    return True
                except ValueError:
                    continue

        # 文件名模式匹配 → 高风险
        name = path.name
        for p in self.filename_high_risk_patterns:
            if p.search(name):
                return True

        return False

    @classmethod
    def default(cls, repo_root: str | Path = ".") -> "SafetyPolicy":
        root = Path(repo_root).resolve()

        allowed = [
            root / "quentin" / "mutable",
            root / "meta_agent" / "tools",
        ]
        forbidden = [
            root / "quentin" / "kernel",
            root / "meta_agent" / "kernel",
            root / "meta_agent" / "runtime",
            root / "meta_agent" / "orchestrator",
            root / "meta_agent" / "safety",
            root / "meta_agent" / "self_programming",
        ]
        high_risk = [
            root / "meta_agent" / "security",
            root / "meta_agent" / "persistence",
        ]

        patterns = [
            re.compile(r".*secret.*", re.IGNORECASE),
            re.compile(r".*vault.*", re.IGNORECASE),
            re.compile(r".*credentials.*", re.IGNORECASE),
        ]

        return cls(
            allowed_roots=allowed,
            forbidden_roots=forbidden,
            high_risk_roots=high_risk,
            filename_high_risk_patterns=patterns,
            max_diff_lines=300,
            max_files_per_patch=20,
        )
