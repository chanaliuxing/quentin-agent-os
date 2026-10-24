from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BlueprintCapability:
    """
    单条蓝皮书能力项（对应蓝皮书里的一个“需求点”）。

    例子：
      - id: "memory.fabric.tiers"
      - section: "memory"
      - name: "Memory Fabric with STS/MTS/LTS tiers"
      - description: "Support 3-tier memory with promotion/decay and consolidation loop."
    """
    id: str
    section: str
    name: str
    description: str
    required: bool = True
    maturity_target: str = "phase-1"   # phase-0/1/2/... 对应蓝皮书路线图
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintSpec:
    """
    蓝皮书整体规格（机器可读版）：

    - version: "v3"
    - codename: "Project Quentin / Research-Integrated Edition"
    - capabilities: 所有能力项列表
    """
    version: str
    codename: str
    capabilities: List[BlueprintCapability]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "codename": self.codename,
            "capabilities": [c.to_dict() for c in self.capabilities],
        }

    def get_capability(self, cap_id: str) -> Optional[BlueprintCapability]:
        for c in self.capabilities:
            if c.id == cap_id:
                return c
        return None

    def list_by_section(self, section: str) -> List[BlueprintCapability]:
        return [c for c in self.capabilities if c.section == section]


# ============================================================
# 默认 v3 蓝皮书 spec（根据你给的 Meta-Agent v3 蓝皮书压缩）
# ============================================================

def load_default_spec_v3() -> BlueprintSpec:
    """
    v3 蓝皮书（Research-Integrated Edition）的最小机器可读版本。
    如果以后蓝皮书升级，可以在这里扩展能力列表。

    注意：
      - 这里列出的是能力“点位”，不是实现状态。
      - 实现状态由 BlueprintGapTracker + CapabilitiesRegistry 决定。
    """
    caps: List[BlueprintCapability] = []

    # 1. 架构层（四层 + 三环境 + 安全内核）
    caps.append(BlueprintCapability(
        id="arch.layers.four-layer-logic",
        section="architecture",
        name="Four Logic Layers (L0-L3)",
        description="L0 Infra&Kernel, L1 Base, L2 Meta, L3 Research & Evolution as distinct modules.",
        maturity_target="phase-0",
    ))
    caps.append(BlueprintCapability(
        id="arch.envs.three-environments",
        section="architecture",
        name="Three Environments (sandbox/staging/prod)",
        description="Support sandbox, staging, production environments, all self-evolution must start from sandbox.",
        maturity_target="phase-1",
    ))
    caps.append(BlueprintCapability(
        id="arch.kernel.safety-kernel",
        section="architecture",
        name="Safety Kernel",
        description="Permission, rollback, audit and risk controls that cannot be modified by self-programming.",
        maturity_target="phase-1",
    ))

    # 2. Memory Fabric（STS/MTS/LTS + promotion/decay）
    caps.append(BlueprintCapability(
        id="memory.fabric.tiers",
        section="memory",
        name="Memory Fabric tiers",
        description="STS, MTS, LTS three-tier memory with explicit metadata: tier, kind, importance, usage.",
        maturity_target="phase-1",
    ))
    caps.append(BlueprintCapability(
        id="memory.fabric.consolidation",
        section="memory",
        name="Memory consolidation from traces",
        description="Sleep loop that turns execution traces into episodic memories in STS/MTS.",
        maturity_target="phase-1",
    ))
    caps.append(BlueprintCapability(
        id="memory.fabric.promotion-decay",
        section="memory",
        name="Memory promotion & decay rules",
        description="Periodic maintenance cycle to promote STS->MTS->LTS and decay stale memories.",
        maturity_target="phase-2",
    ))
    caps.append(BlueprintCapability(
        id="memory.fabric.cross-domain",
        section="memory",
        name="Cross-domain memory flag",
        description="Domain field with 'cross' type for reusable knowledge across domains.",
        maturity_target="phase-2",
    ))

    # 3. Loops：认知 / 免疫 / 睡眠 / 技能进化
    caps.append(BlueprintCapability(
        id="loops.cognitive.trace-required",
        section="loops",
        name="Cognitive loop with mandatory trace",
        description="Every task execution must produce structured traces with status, steps, metrics, summary.",
        maturity_target="phase-0",
    ))
    caps.append(BlueprintCapability(
        id="loops.immune.anomaly-detector",
        section="loops",
        name="Immune loop anomaly detector",
        description="Monitor error rate/latency/cost/reward; detect anomalies and downgrade features or rollback.",
        maturity_target="phase-2",
    ))
    caps.append(BlueprintCapability(
        id="loops.sleep.consolidation",
        section="loops",
        name="Sleep loop consolidation",
        description="Periodic sleep loop that consolidates traces into memory and prepares training pairs.",
        maturity_target="phase-1",
    ))
    caps.append(BlueprintCapability(
        id="loops.skill-evolution.from-traces",
        section="loops",
        name="Skill & code evolution from successful traces",
        description="Mine patterns from high-success traces, synthesize skills, test them and decide replace/coexist.",
        maturity_target="phase-3",
    ))

    # 4. 自编程引擎
    caps.append(BlueprintCapability(
        id="selfprog.patch-generation",
        section="self-programming",
        name="Patch generation for mutable modules",
        description="Generate code patches for modules under /mutable/ marked as auto_updatable.",
        maturity_target="phase-4",
    ))
    caps.append(BlueprintCapability(
        id="selfprog.test-harness",
        section="self-programming",
        name="Patch test harness",
        description="Run unit tests, static analysis and simple regression before accepting patch candidates.",
        maturity_target="phase-4",
    ))
    caps.append(BlueprintCapability(
        id="selfprog.deployment-policy",
        section="self-programming",
        name="Patch deployment policy",
        description="Policy for when patches are allowed to move from sandbox to staging/shadow/prod.",
        maturity_target="phase-5",
    ))

    # 5. 多智能体 & 模型路由
    caps.append(BlueprintCapability(
        id="multiagent.council.roles",
        section="multi-agent",
        name="Fixed roles in multi-agent council",
        description="Speed-Agent, Safety-Agent, Cost-Agent, Domain-Expert-Agent as fixed basic roles.",
        maturity_target="phase-1",
    ))
    caps.append(BlueprintCapability(
        id="multiagent.council.experimental-roles",
        section="multi-agent",
        name="Experimental agent roles",
        description="Allow new experimental roles to be introduced under ResearchLayer for small-traffic tests.",
        maturity_target="phase-3",
    ))
    caps.append(BlueprintCapability(
        id="routing.model-router.data-driven",
        section="multi-agent",
        name="Data-driven ModelRouter",
        description="Route tasks to models based on logged performance metrics and costs (bandit/RL/SL).",
        maturity_target="phase-3",
    ))

    # 6. 多领域接入 & 跨域复用
    caps.append(BlueprintCapability(
        id="domain.generic-adapter-interface",
        section="domains",
        name="Generic domain adapter interface",
        description="Domain adapters for Desktop/Legal/Trading etc share a common interface (actions/tools + schema).",
        maturity_target="phase-2",
    ))
    caps.append(BlueprintCapability(
        id="domain.cross-skill-reuse",
        section="domains",
        name="Cross-domain skill reuse",
        description="Skill definitions can be reused across domains where applicable, with domain whitelist/blacklist.",
        maturity_target="phase-3",
    ))

    # 7. 可观测性 & 研究接口
    caps.append(BlueprintCapability(
        id="obs.traces-metrics-logs",
        section="observability",
        name="Traces + metrics + logs",
        description="Unified observability: structured traces, metrics and logs across all loops and layers.",
        maturity_target="phase-0",
    ))
    caps.append(BlueprintCapability(
        id="obs.eval-harness",
        section="observability",
        name="Eval Harness",
        description="Unified evaluation harness for offline/online metrics and A/B testing.",
        maturity_target="phase-2",
    ))
    caps.append(BlueprintCapability(
        id="obs.dashboard-minimum",
        section="observability",
        name="Minimal dashboard or export for visualization",
        description="Export metrics and experiment results in a format easy to plug into dashboards.",
        maturity_target="phase-3",
    ))

    # 8. 研究层 & 实验编排
    caps.append(BlueprintCapability(
        id="research.experiment-orchestrator",
        section="research",
        name="Experiment Orchestrator",
        description="Create experiments, run them across variants, compare variants and export results.",
        maturity_target="phase-2",
    ))
    caps.append(BlueprintCapability(
        id="research.auto-experiment-selection",
        section="research",
        name="Automatic experiment selection",
        description="Select which experiments to run per research cycle using an evolution strategy manager.",
        maturity_target="phase-3",
    ))
    caps.append(BlueprintCapability(
        id="research.budget-controller",
        section="research",
        name="Budget & cost controller",
        description="Limit experiments and runs per cycle according to research budget constraints.",
        maturity_target="phase-3",
    ))

    # 9. 蓝皮书自迭代相关
    caps.append(BlueprintCapability(
        id="blueprint.spec.machine-readable",
        section="blueprint",
        name="Machine-readable blueprint spec",
        description="Represent the blueprint (this file) in a structured, versioned format.",
        maturity_target="phase-0",
    ))
    caps.append(BlueprintCapability(
        id="blueprint.gap-tracking",
        section="blueprint",
        name="Blueprint gap tracker",
        description="Compare blueprint capabilities against actual system capabilities to locate gaps.",
        maturity_target="phase-1",
    ))
    caps.append(BlueprintCapability(
        id="blueprint.auto-improvement-plans",
        section="blueprint",
        name="Automatic improvement plans",
        description="Generate improvement plans and experiments to close blueprint gaps via LLM(s).",
        maturity_target="phase-3",
    ))

    return BlueprintSpec(
        version="v3",
        codename="Project Quentin / Research-Integrated Edition",
        capabilities=caps,
    )

def parse_markdown_blueprint(file_path: str) -> BlueprintSpec:
    """
    Parses a markdown blueprint file into a BlueprintSpec object.
    
    This is a heuristic parser that maps markdown headers to sections
    and list items to capabilities. It's not perfect but provides a
    bridge between the human-readable doc and the machine-readable spec.
    """
    import re
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    caps: List[BlueprintCapability] = []
    current_section = "general"
    current_cap_name = ""
    current_cap_desc = []
    
    # Regex patterns
    section_pattern = re.compile(r'^(\d+)\.\s+(.*)') # e.g., "1. 总体架构..."
    subsection_pattern = re.compile(r'^(\d+\.\d+)\s+(.*)') # e.g., "1.1 四层智能结构..."
    # Matches list items that look like capabilities, e.g., "* Memory Fabric..." or "1. ..."
    cap_pattern = re.compile(r'^[\*\-]\s+(.*)') 
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for section headers
        sec_match = section_pattern.match(line)
        if sec_match:
            current_section = sec_match.group(2).strip()
            continue
            
        sub_match = subsection_pattern.match(line)
        if sub_match:
            # Treat subsections as part of the current section key for uniqueness or just ignore
            # For now, let's just append it to the section name or treat it as a context switch
            # current_section = f"{current_section} - {sub_match.group(2).strip()}"
            continue

        # Check for capability items
        cap_match = cap_pattern.match(line)
        if cap_match:
            # If we were building a capability, save it
            if current_cap_name:
                caps.append(BlueprintCapability(
                    id=f"md.{current_section}.{len(caps)}", # Generate a temp ID
                    section=current_section,
                    name=current_cap_name,
                    description=" ".join(current_cap_desc),
                    maturity_target="phase-unknown"
                ))
            
            # Start new capability
            current_cap_name = cap_match.group(1).strip()
            current_cap_desc = []
        else:
            # If it's text following a capability, treat it as description
            if current_cap_name:
                current_cap_desc.append(line)

    # Add the last one
    if current_cap_name:
        caps.append(BlueprintCapability(
            id=f"md.{current_section}.{len(caps)}",
            section=current_section,
            name=current_cap_name,
            description=" ".join(current_cap_desc),
            maturity_target="phase-unknown"
        ))

    return BlueprintSpec(
        version="v3-parsed",
        codename="Parsed from blueprint.md",
        capabilities=caps
    )

class BlueprintSpecLoader:
    """
    Loads a v3 blueprint spec from a single source-of-truth.

    Decision (Blueprint v3 checklist P2.3):
    - Canonical machine-readable spec is `quentin/blueprint/spec.py:load_default_spec_v3()`.
    - `blueprint.md` is treated as a narrative doc and can be parsed as a fallback.
    - `blueprints/meta_agent_v3.yaml` can be generated from the canonical spec for tooling.
    """

    def __init__(self, path: str | None = None):
        self.path = path or "blueprint.md"

    def load(self) -> BlueprintSpec:
        p = Path(self.path)
        if not p.exists():
            return load_default_spec_v3()

        suffix = p.suffix.lower()
        if suffix in (".md",):
            try:
                return parse_blueprint_md_to_spec_v3(str(p))
            except Exception:
                return load_default_spec_v3()
        if suffix in (".yaml", ".yml"):
            try:
                import yaml

                raw = yaml.safe_load(p.read_text(encoding="utf-8") or "{}") or {}
                caps = []
                for c in raw.get("capabilities", []) or []:
                    if not isinstance(c, dict):
                        continue
                    caps.append(
                        BlueprintCapability(
                            id=str(c.get("id") or ""),
                            section=str(c.get("section") or ""),
                            name=str(c.get("name") or ""),
                            description=str(c.get("description") or ""),
                            required=bool(c.get("required", True)),
                            maturity_target=str(c.get("maturity_target") or "phase-unknown"),
                            notes=c.get("notes"),
                        )
                    )
                if caps:
                    return BlueprintSpec(
                        version=str(raw.get("version") or "v3"),
                        codename=str(raw.get("codename") or "meta-agent-v3"),
                        capabilities=caps,
                    )
            except Exception:
                pass
            return load_default_spec_v3()
        if suffix in (".json",):
            try:
                raw = json.loads(p.read_text(encoding="utf-8") or "{}") or {}
                caps = []
                for c in raw.get("capabilities", []) or []:
                    if not isinstance(c, dict):
                        continue
                    caps.append(BlueprintCapability(**c))
                if caps:
                    return BlueprintSpec(
                        version=str(raw.get("version") or "v3"),
                        codename=str(raw.get("codename") or "meta-agent-v3"),
                        capabilities=caps,
                    )
            except Exception:
                pass
            return load_default_spec_v3()

        return load_default_spec_v3()
