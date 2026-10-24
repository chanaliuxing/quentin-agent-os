"""
Minimal AgentRuntime stub to satisfy container and tests.
"""

class AgentRuntime:
    def __init__(self, *args, **kwargs):
        self.initialized = True
        self.tracer = kwargs.get("tracer")
        self.kv_store = kwargs.get("kv_store")
        self.safety_kernel = kwargs.get("safety_kernel")
        self.memory = kwargs.get("memory")
        self.model_router = kwargs.get("model_router")
        self.cognitive_loop = kwargs.get("cognitive_loop")
        self.immune_loop = kwargs.get("immune_loop")
        self.planner = kwargs.get("planner")
        self.executor = kwargs.get("executor")
        self.critic = kwargs.get("critic")
        self.tool_manager = kwargs.get("tool_manager")
        self.skill_library = kwargs.get("skill_library")
        self.skill_miner = kwargs.get("skill_miner")
        self.sleep_loop = kwargs.get("sleep_loop")
        self.multi_agent = kwargs.get("multi_agent")
        self.multi_llm_council = kwargs.get("multi_llm_council")
        self.observability = kwargs.get("observability")
        self.self_programming = kwargs.get("self_programming")

    @classmethod
    def create_from_settings(cls, settings, container=None):
        tracer = getattr(container, "tracer", None) if container else None
        kv = getattr(container, "kv_store", None) if container else None
        safety_kernel = getattr(container, "safety_kernel", None) if container else None
        memory = getattr(container, "memory_fabric", None) if container else None
        model_router = getattr(container, "model_router", None) if container else None
        cognitive_loop = getattr(container, "cognitive_loop", None) if container else None
        immune_loop = getattr(container, "immune_loop", None) if container else None
        planner = getattr(container, "planner", None) if container else None
        executor = getattr(container, "executor", None) if container else None
        critic = getattr(container, "critic", None) if container else None
        tool_manager = getattr(container, "tool_manager", None) if container else None
        skill_library = getattr(container, "skill_library", None) if container else None
        skill_miner = getattr(container, "skill_miner", None) if container else None
        sleep_loop = getattr(container, "sleep_loop", None) if container else None
        multi_agent = getattr(container, "multi_agent_coordinator", None) if container else None
        multi_llm_council = getattr(container, "multi_llm_council", None) if container else None
        observability = getattr(container, "observability_service", None) if container else None
        self_programming = getattr(container, "self_programming_engine", None) if container else None
        runtime = cls(
            tracer=tracer,
            kv_store=kv,
            safety_kernel=safety_kernel,
            memory=memory,
            model_router=model_router,
            cognitive_loop=cognitive_loop,
            immune_loop=immune_loop,
            planner=planner,
            executor=executor,
            critic=critic,
            tool_manager=tool_manager,
            skill_library=skill_library,
            skill_miner=skill_miner,
            sleep_loop=sleep_loop,
            multi_agent=multi_agent,
            multi_llm_council=multi_llm_council,
            observability=observability,
            self_programming=self_programming,
        )
        try:
            if observability and getattr(observability, "runtime", None) is None:
                observability.runtime = runtime
        except Exception:
            pass
        return runtime

    def run(self, *args, **kwargs):
        return {"status": "ok"}
