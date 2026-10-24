# quentin/bootstrap/container.py
import os
import logging
from pathlib import Path
from typing import Optional, Any, Dict, List

from dotenv import load_dotenv
from quentin.infra.env_manager import env_manager

# Core & Infra
from quentin.config.settings import Settings
from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.kernel.safety import SafetyKernel
from quentin.kernel.policy import PolicyEngine
from quentin.kernel.budget import BudgetController

# Memory & Router
from quentin.memory.fabric import MemoryFabric
from quentin.models.router import ModelRouter, ModelInfo
from quentin.routing.backend_call import DefaultRouterBackend

# L1 Components
from quentin.cognitive.loop import CognitiveLoop
from quentin.planning.echo_planner import EchoPlanner
from quentin.critic.rule_based import RuleBasedCritic
from quentin.traces.execution_trace import ExecutionTraceStore as FileBackedTraceStore
from quentin.execution.executor import Executor
from quentin.execution.skill_executor import Executor as SkillExecutor
from quentin.tools.manager import ToolManager, ToolPolicy
from quentin.traces.core import JsonlTraceRecorder
from quentin.skills.library import SkillLibrary
from quentin.skills.miner import SkillMiner
from quentin.skills.manager import SkillManager
from quentin.loops.sleep_loop import SleepLoop
from quentin.loops.immune_loop import ImmuneLoop
from quentin.config.cognitive_policies import load_cognitive_policies
from quentin.cognitive.perception.layer import PerceptionContextConfig, PerceptionContextLayer
from quentin.cognitive.perception.situation_skill_router import MemoryBackedSituationSkillRouter

# Tools Implementation
from quentin.tools.filesystem import fs_write_file, fs_read_file, fs_search_replace
from quentin.tools.shell import shell_run_command
from quentin.tools.interactive_shell import interactive_shell_tool
from quentin.tools.plugin_loader import register_tool_plugins
from quentin.tools.providers.mcp import MCPToolProvider
from quentin.tools.usage.tool_knowledge_sink import ToolKnowledgeUsageSink
from quentin.tools.packs.builtin import build_builtin_tool_packs_registry
from quentin.tools.schemas import ToolSpec

# LLM & Multi-Agent
from quentin.llm.ollama_client import OllamaClient, OllamaClientConfig
from quentin.llm.types import LLMConfig
from quentin.llm.multi_council import MultiAICouncil
from quentin.agents.coordinator import MultiAgentCoordinator

# Governance & Blueprint
from quentin.blueprint.spec import load_default_spec_v3
from quentin.blueprint.gap_tracker import BlueprintGapTracker, CapabilitiesRegistry
from quentin.l3.research.schemas import ResearchBudgetConfig
try:
    from governance.council import Constitution, GovernanceCouncil
except ImportError:
    # Fallback or stub if governance is not installed as a package
    class Constitution: pass
    class GovernanceCouncil: pass

# Self-Programming V2
from meta_agent.self_programming.engine_v2 import (
    SelfProgrammingEngineV2, 
    SelfProgrammingConfig
)
from meta_agent.patches.safe_applier import SafePatchApplier
from meta_agent.patches.store import PatchStore

# Observability
from quentin.observability.service import ObservabilityService

logger = logging.getLogger(__name__)

class Container:
    def __init__(self, settings: Optional[Settings] = None, repo_root: Optional[str | Path] = None):
        load_dotenv(override=True)
        # Normalize legacy env vars (opt-in; safe and conservative).
        try:
            env_manager.normalize()
        except Exception:
            pass
        if repo_root:
            self.repo_root = Path(repo_root).resolve()
        else:
            self.repo_root = Path(__file__).parent.parent.parent.resolve()
            
        self.settings = settings or Settings()
        self._instances: Dict[str, Any] = {}

    def _get(self, key: str, factory):
        if key not in self._instances:
            self._instances[key] = factory()
        return self._instances[key]

    @property
    def tracer(self) -> Tracer:
        return self._get("tracer", Tracer)

    @property
    def kv_store(self) -> KVStore:
        return self._get("kv_store", KVStore)

    @property
    def budget_controller(self) -> BudgetController:
        return self._get("budget_controller", lambda: BudgetController(
            repo_root=self.repo_root
        ))

    @property
    def policy_engine(self) -> PolicyEngine:
        return self._get("policy_engine", lambda: PolicyEngine(
            repo_root=self.repo_root
        ))

    @property
    def safety_kernel(self) -> SafetyKernel:
        def _build_kernel():
            # Initialize default balance for local/test use
            from quentin.infra.billing.balance_manager import balance_manager
            balance_manager.set_balance("default_user", 9000000.0)
            
            return SafetyKernel(
                policy_engine=self.policy_engine,
                budget_controller=self.budget_controller,
                approval_gate=self.approval_gate
            )
        return self._get("safety_kernel", _build_kernel)

    @property
    def approval_gate(self) -> Any:
        from quentin.infra.security.approval import approval_gate
        return self._get("approval_gate", lambda: approval_gate)

    @property
    def council_manager(self) -> Any:
        from quentin.council.manager import CouncilManager
        return self._get("council_manager", lambda: CouncilManager(
            repo_root=self.repo_root,
            model_router=self.model_router
        ))

    @property
    def tool_manager(self) -> ToolManager:
        def factory():
            from quentin.tools.middleware.path_fixer import get_path_correction_hook
            tm = ToolManager()
            tm.set_repo_root(str(self.repo_root))

            use_packs = (os.getenv("QUENTIN_TOOL_PACKS_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            if use_packs:
                # Pluggable pack bootstrap (P1-B): builtin tools are registered via packs.
                registry = build_builtin_tool_packs_registry(container=self)
                _ = registry.run(tool_manager=tm, repo_root=self.repo_root, container=self)
                return tm

            # Legacy hardcoded wiring (default).
            # v3.1: tool knowledge writeback (best-effort, pluggable).
            try:
                tm.add_usage_sink(ToolKnowledgeUsageSink(memory_fabric=self.memory_fabric))
            except Exception:
                pass
            # Tier 0 ToolPack Architecture (P5 Normalized)
            from quentin.tools.packs.filesystem_pack import FileSystemToolPack
            from quentin.tools.packs.shell_pack import ShellToolPack
            from quentin.tools.packs.memory_pack import MemoryPack
            from quentin.tools.packs.coder_pack import CoderToolPack
            from quentin.tools.packs.autoloop_pack import AutoloopToolPack
            from quentin.tools.learning.graph_search import GraphSearchTool

            tm.register_pack(FileSystemToolPack())
            tm.register_pack(ShellToolPack())
            tm.register_pack(MemoryPack(memory_fabric=self.memory_fabric))
            tm.register_pack(CoderToolPack())
            tm.register_pack(AutoloopToolPack())
            
            # Register GraphSearchTool (Phase 4)
            tm.register_tool(ToolSpec(**GraphSearchTool.get_schema()), GraphSearchTool(service=self.graph_service).call)
            
            # P5: Evolution Phase 1 - Smart Middleware
            from quentin.tools.middleware.filesystem import SmartFilesystemMiddleware
            from quentin.tools.middleware.shell_safety import ShellSafetyMiddleware
            from quentin.tools.middleware.syntax_guard import SyntaxGuardMiddleware
            from quentin.tools.middleware.quality_gate import QualityGateMiddleware
            
            tm.add_middleware(SmartFilesystemMiddleware(repo_root=str(self.repo_root)))
            tm.add_middleware(ShellSafetyMiddleware())
            tm.add_middleware(SyntaxGuardMiddleware())
            tm.add_middleware(QualityGateMiddleware(repo_root=str(self.repo_root)))
            
            # Common Core Aliases (Explicit Mapping)
            sh_h = tm._handlers.get("shell.run_command")
            if sh_h:
                for alias in ["pwd", "find"]: tm.register(alias, sh_h)
            fr_h = tm._handlers.get("fs.read_file")
            # cat is now in ShellToolPack pointing to shell_cat

            # [6.1.2] Register path correction middleware
            if (os.getenv("QUENTIN_TOOL_MIDDLEWARE_PIPELINE", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
                try:
                    from quentin.tools.middleware.path_fixer import PathFixerMiddleware
                    from quentin.tools.middleware.error_hints import ErrorHintsMiddleware

                    tm.add_middleware(PathFixerMiddleware(repo_root=self.repo_root))
                    tm.add_middleware(ErrorHintsMiddleware())
                except Exception:
                    tm.add_before_hook(get_path_correction_hook(repo_root=self.repo_root))
            else:
                tm.add_before_hook(get_path_correction_hook(repo_root=self.repo_root))

            tm.set_safety_kernel(self.safety_kernel)
            
            # P5: Evolution Phase 4 - Marketplace Engine (PluginLoader)
            try:
                from quentin.tools.loader import PluginLoader
                loader = PluginLoader(repo_root=str(self.repo_root), tool_manager=tm)
                loader.scan_and_load()
                # Also register v1 tool plugins under extensions/tools (canonical plugin layout).
                # This keeps the Container default wiring aligned with ToolManager's lazy plugin loader.
                try:
                    register_tool_plugins(tool_manager=tm, repo_root=self.repo_root)
                except Exception:
                    pass

                # Optional: Live Evolution watcher is OFF by default to avoid background
                # threads in unit tests and local one-shot runs.
                if (os.getenv("QUENTIN_LIVE_EVOLUTION_WATCHER", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
                    from quentin.infra.config.watcher import config_watcher

                    # Watch key runtime configs for hot-reload (OpenClaw parity).
                    config_watcher.watch_files.append(self.repo_root / ".env")
                    config_watcher.watch_files.append(self.repo_root / "config" / "budgets.json")
                    config_watcher.watch_files.append(self.repo_root / "config" / "model_router_rules.json")
                    config_watcher.register_callback(lambda: loader.scan_and_load())
                    config_watcher.register_callback(lambda: self.model_router.reload_rules())
                    config_watcher.start()
            except Exception: pass

            # Default tool policy layering:
            # global -> role -> environment -> tool
            # sandbox: shell allowed (guarded by SafetyKernel + hooks)
            # staging/prod: shell denied by environment policy
            tm.set_global_policy(ToolPolicy(deny=["system.*", "exec.*"]))
            tm.set_environment_policy("staging", ToolPolicy(deny=["shell.*"]))
            tm.set_environment_policy("prod", ToolPolicy(deny=["shell.*"]))

            # Legacy plugins now handled by Phase 4 PluginLoader above.

            # MCP tools: pluggable provider (disabled by default via config/mcp_security.yaml).
            try:
                from quentin.config.mcp_security import load_mcp_security
                from quentin.governance.tool_council import ToolGovernanceGate
                from quentin.council.manager import CouncilManager

                mcp_cfg = load_mcp_security(self.repo_root)
                gate = None
                if mcp_cfg.enabled and mcp_cfg.enable_tool_governance:
                    # Pluggable gate: can be swapped/replaced without changing MCPToolProvider API.
                    gate = ToolGovernanceGate(
                        council_manager=CouncilManager(repo_root=self.repo_root, model_router=self.model_router)
                    )
                MCPToolProvider(tool_governance_gate=gate).register(tool_manager=tm, repo_root=str(self.repo_root))
            except Exception:
                pass
            
            # P5: Surgery One Hundred and One - Active Skill Loading (OpenClaw Parity)
            # Ensure newly mined/verified skills are physically registered as tools
            try:
                from quentin.skills.manager import SkillManager
                sm = SkillManager(repo_root=self.repo_root)
                loaded_count = sm.load_all_skills(tm)
                if loaded_count > 0:
                    logger.info(f"Container: Activated {loaded_count} learned skills from library.")
            except Exception as e:
                logger.error(f"Container: Failed to load learned skills: {e}")

            return tm
        return self._get("tool_manager", factory)

    @property
    def llm(self) -> OllamaClient:
        model = os.getenv("LLM_MODEL")
        if not model:
            raise ValueError("Environment variable LLM_MODEL is not set.")
        return self._get("llm", lambda: OllamaClient(
            config=OllamaClientConfig(name=model)
        ))

    @property
    def executor(self) -> Executor:
        return self._get("executor", lambda: Executor(
            tool_manager=self.tool_manager,
            llm=self.llm,
            trace_recorder=self.trace_recorder,
            repo_root=str(self.repo_root),
        ))

    @property
    def skill_manager(self) -> SkillManager:
        return self._get("skill_manager", lambda: SkillManager(repo_root=self.repo_root))

    @property
    def skill_executor(self) -> SkillExecutor:
        return self._get(
            "skill_executor",
            lambda: SkillExecutor(
                repo_root=self.repo_root,
                model_router=self.model_router,
                skill_manager=self.skill_manager,
                tool_manager=self.tool_manager,
            ),
        )

    @property
    def perception_layer(self) -> PerceptionContextLayer:
        def factory() -> PerceptionContextLayer:
            policies = load_cognitive_policies(repo_root=self.repo_root)
            cfg = PerceptionContextConfig(
                enable_situation_classifier=policies.enable_situation_classifier,
                enable_attention_filter=policies.enable_attention_filter,
                enable_expectation_engine=policies.enable_expectation_engine,
                enable_situation_to_skill=policies.enable_situation_to_skill,
                attention_target_ratio=float(policies.attention_target_ratio),
                debug_use_full_context=policies.debug_use_full_context,
            )
            router = None
            if cfg.enable_situation_to_skill:
                router = MemoryBackedSituationSkillRouter(memory_fabric=self.memory_fabric)
            return PerceptionContextLayer(config=cfg, situation_skill_router=router)

        return self._get("perception_layer", factory)

    @property
    def model_router(self) -> ModelRouter:
        def factory():
            router = ModelRouter(
                backend_call=DefaultRouterBackend(safety_kernel=self.safety_kernel),
                repo_root=self.repo_root
            )
            model_name = os.getenv("LLM_MODEL")
            if not model_name:
                raise ValueError("Environment variable LLM_MODEL is not set.")
            # Provider(kind) must not be hardcoded. Benchmarks and offline runs rely on
            # routing to the correct adapter (e.g. provider="stub").
            provider = (os.getenv("LLM_PROVIDER") or os.getenv("QUENTIN_LLM_PROVIDER") or "").strip().lower()
            if not provider:
                # Keep behavior stable when env vars are missing.
                mid = str(model_name or "").lower()
                if ":" in mid:
                    provider = "ollama"
                elif "gpt" in mid or "openai" in mid:
                    provider = "openai"
                elif "claude" in mid or "anthropic" in mid:
                    provider = "anthropic"
                elif "gemini" in mid or "google" in mid:
                    provider = "gemini"
                elif "deepseek" in mid:
                    provider = "deepseek"
                else:
                    provider = "unknown"
            router.register_model(ModelInfo(name=model_name, kind=provider))
            return router
        return self._get("model_router", factory)

    @property
    def graph_service(self) -> Any:
        from quentin.knowledge_graph.service import GraphService
        return self._get("graph_service", lambda: GraphService())

    @property
    def memory_fabric(self) -> MemoryFabric:
        def factory():
            store = self._build_memory_store()
            return MemoryFabric(repo_root=self.repo_root, store=store)
        return self._get("memory_fabric", factory)

    def _build_memory_store(self) -> Any:
        """
        L0 Factory: decide which storage implementation to use based on config.
        This isolates implemention details from high-level layers.
        """
        from quentin.memory.store_sqlite import SqliteMemoryStore
        
        db_path = self.repo_root / "data" / "memory.db"
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        store_kind = (os.getenv("QUENTIN_MEMORY_STORE") or "").strip().lower()

        # 0. Champion stack (Qdrant + Postgres)
        if store_kind == "champion":
            try:
                from quentin.memory.store_champion import ChampionMemoryStore
                dsn = os.getenv("PG_DSN")
                return ChampionMemoryStore(pg_dsn=dsn)
            except Exception as e:
                logger.warning(f"Container: Failed to load ChampionMemoryStore: {e}. Falling back to SQLite.")
        
        # 1. Postgres Support (L0 implementation)
        if store_kind == "postgres":
            try:
                from quentin.memory.store_postgres import PostgresMemoryStore
                dsn = os.getenv("PG_DSN") or "postgresql://postgres@localhost:5432/postgres"
                return PostgresMemoryStore(dsn=dsn)
            except Exception as e:
                logger.warning(f"Container: Failed to load PostgresMemoryStore: {e}. Falling back to SQLite.")

        # 2. SQLite-Vec Support
        if store_kind == "sqlite_vec":
            try:
                from quentin.memory.store_sqlite_vec import SqliteVecMemoryStore
                store = SqliteVecMemoryStore(db_path)
                store.init()
                return store
            except Exception:
                logger.warning("Container: SqliteVecMemoryStore unavailable. Falling back to base SQLite.")

        # 3. Default L0: Base SQLite
        store = SqliteMemoryStore(db_path)
        try:
            store.init()
        except Exception:
            pass
        return store

    @property
    def trace_store(self) -> FileBackedTraceStore:
        return self._get("trace_store", lambda: FileBackedTraceStore(repo_root=self.repo_root))

    @property
    def trace_recorder(self) -> JsonlTraceRecorder:
        return self._get("trace_recorder", lambda: JsonlTraceRecorder(repo_root=str(self.repo_root)))

    @property
    def cognitive_loop(self) -> CognitiveLoop:
        return self._get("cognitive_loop", lambda: CognitiveLoop(
            executor=self.skill_executor,
            perception_layer=self.perception_layer,
            traces_store=self.trace_store,
            memory_fabric=self.memory_fabric,
            model_router=self.model_router,
            cognitive_policies=load_cognitive_policies(repo_root=self.repo_root),
            repo_root=self.repo_root,
            council_manager=self.council_manager,
            skill_manager=self.skill_manager,
            self_programming_engine=self.self_programming_engine,
        ))

    @property
    def immune_loop(self) -> ImmuneLoop:
        return self._get("immune_loop", lambda: ImmuneLoop(repo_root=self.repo_root))

    @property
    def sleep_loop(self) -> SleepLoop:
        return self._get("sleep_loop", lambda: SleepLoop(memory_fabric=self.memory_fabric, repo_root=self.repo_root))

    @property
    def self_programming_engine(self) -> Any:
        def _build() -> Any:
            from quentin.self_programming.engine import SelfProgrammingEngine
            return SelfProgrammingEngine(repo_root=self.repo_root)

        return self._get("self_programming_engine", _build)

    @property
    def knowledge_graph(self) -> Any:
        """
        Pluggable knowledge graph backend.

        Bridges the SimpleKnowledgeGraph API to the industrial GraphService.
        """
        from quentin.knowledge_graph.service import GraphService
        from quentin.knowledge_graph.schema import NodeType, EdgeType

        try:
            svc = self._get("graph_service", lambda: GraphService())
            
            class KGBridge:
                """Bridge the SimpleKnowledgeGraph API to GraphService."""
                def __init__(self, service: GraphService):
                    self.service = service

                def add_triple(self, subj: str, pred: str, obj: str, source: str = "system"):
                    # Map predicate to EdgeType if possible
                    try:
                        rel = EdgeType(pred.lower())
                    except ValueError:
                        rel = EdgeType.RELATED_TO
                        
                    self.service.create_link(
                        src_ref=(NodeType.CONCEPT, subj),
                        dst_ref=(NodeType.CONCEPT, obj),
                        rel=rel
                    )

                def query(self, entity: str) -> List[Any]:
                    # Simple query fallback
                    raw = self.service.get_neighbors(entity, depth=1, direction="both")
                    # Convert to Triple-like objects for compatibility
                    from quentin.memory.knowledge_graph import Triple
                    results = []
                    for e in raw.get("edges", []):
                        results.append(Triple(
                            subject=e.get("src_node_id"),
                            predicate=e.get("edge_type"),
                            object=e.get("dst_node_id")
                        ))
                    return results

                def get_context_text(self, entities: List[str]) -> str:
                    facts = []
                    for ent in entities:
                        raw = self.service.get_neighbors(ent, depth=1, direction="both")
                        for e in raw.get("edges", []):
                            facts.append(f"- {e.get('src_node_id')} {e.get('edge_type')} {e.get('dst_node_id')}")
                    if not facts: return ""
                    return "\nRELEVANT KNOWLEDGE:\n" + "\n".join(list(set(facts))[:20]) + "\n"

            return KGBridge(svc)
        except Exception as e:
            logger.warning(f"Container: Failed to initialize GraphService bridge: {e}. Falling back to SimpleKnowledgeGraph.")
            from quentin.memory.knowledge_graph import SimpleKnowledgeGraph
            return self._get("knowledge_graph", lambda: SimpleKnowledgeGraph(repo_root=str(self.repo_root)))

    @property
    def auto_fixer(self) -> Any:
        # AutoFixer is gated by QUENTIN_AUTO_FIXER_ENABLED at call sites.
        # Here we provide a dedicated engine instance with safe defaults (proposal-only)
        # unless QUENTIN_AUTO_FIXER_AUTO_APPLY=1 is explicitly set.
        from quentin.self_programming.auto_fixer import AutoFixerLoop

        def _build_engine() -> SelfProgrammingEngineV2:
            import os
            from quentin.runtime.system_events import SystemEventQueue
            from meta_agent.self_programming.backends.registry import build_bundle_by_id

            auto_apply = (os.getenv("QUENTIN_AUTO_FIXER_AUTO_APPLY", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            backend_id = (os.getenv("QUENTIN_AUTO_FIXER_SELFPROG_BACKEND") or os.getenv("QUENTIN_SELFPROG_BACKEND") or "default").strip().lower()

            cfg = SelfProgrammingConfig(default_coder_backend="llm_client")
            try:
                cfg.proposal_only = not auto_apply
            except Exception:
                pass
            try:
                cfg.allow_auto_apply = bool(auto_apply)
            except Exception:
                pass

            bundle = build_bundle_by_id(
                backend_id=backend_id,
                repo_root=self.repo_root,
                safety_kernel=self.safety_kernel,
            )

            return SelfProgrammingEngineV2(
                config=cfg,
                applier=SafePatchApplier(repo_root=self.repo_root, safety_kernel=self.safety_kernel),
                system_event_queue=SystemEventQueue(repo_root=str(self.repo_root)),
                backend_bundle=bundle,
                tool_manager=self.tool_manager,
            )

        def _build() -> Any:
            engine = self._get("auto_fixer_engine", _build_engine)
            return AutoFixerLoop(repo_root=str(self.repo_root), engine=engine)

        return self._get("auto_fixer", _build)

    @property
    def metrics(self) -> Any:
        from quentin.infra.observability.metrics import MetricsCollector
        return self._get("metrics", lambda: MetricsCollector(repo_root=str(self.repo_root)))

    @property
    def observability_service(self) -> ObservabilityService:
        return self._get("observability_service", lambda: ObservabilityService(repo_root=self.repo_root))
