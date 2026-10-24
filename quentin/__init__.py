"""
Project Quentin v3

四层结构：
- L0: kernel, infra
- L1: base (执行 / 记忆 / 工具)
- L2: meta (评估 / 自改调度)
- L3: research (演化策略 / 实验平台)

三环境：
- sandbox
- staging
- prod
"""

__all__ = ["kernel", "infra", "meta", "l3", "mutable", "domain", "runtime"]
