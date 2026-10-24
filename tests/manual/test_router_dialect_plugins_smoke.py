import os
import asyncio
from pathlib import Path
from quentin.routing.model_router import ModelRouter, ModelInfo
from quentin.llm.client import call_llm

def test_router_plugins():
    print("Testing Routing Policy Plugins...")
    os.environ["QUENTIN_ROUTING_POLICY_PLUGINS"] = "1"
    
    router = ModelRouter()
    router.register_model(ModelInfo(name="super-model", kind="openai"))
    
    # 1. Custom Policy
    from quentin.models.routing_policies.base import RoutingPolicy, get_routing_policy_registry
    class ForceSuperPolicy(RoutingPolicy):
        @property
        def id(self): return "force_super"
        @property
        def priority(self): return 1000
        def route(self, mode, task_type, metadata):
            if task_type == "special":
                return ModelInfo(name="super-model", kind="openai")
            return None
            
    get_routing_policy_registry().register(ForceSuperPolicy())
    
    res = router.route(mode="chat", task_type="special")
    print(f"Routing result for 'special': {res.name}")
    assert res.name == "super-model"
    print("Routing Policy Plugin check PASSED.")

def test_dialect_plugins():
    print("\nTesting Prompt Dialect Plugins...")
    os.environ["QUENTIN_PROMPT_DIALECT_PLUGINS"] = "1"
    
    from quentin.llm.dialects.base import PromptDialect, get_dialect_registry
    class ShoutDialect(PromptDialect):
        @property
        def id(self): return "shout"
        @property
        def priority(self): return 1000
        def supports(self, provider, model_name): return True
        def transform(self, provider, model_name, system_prompt, user_prompt, metadata):
            return system_prompt.upper(), user_prompt.upper(), {"shouted": True}
            
    get_dialect_registry().register(ShoutDialect())
    
    # We can't easily call_llm without real network, but we can check if it gets to audit/guard
    # or just use a stub. Let's look at dialects result via a direct call if possible.
    reg = get_dialect_registry()
    sp, up, meta = reg.apply("test", "test", "hello system", "hello user")
    print(f"Dialect result: sp={sp}, up={up}, meta={meta}")
    assert sp == "HELLO SYSTEM"
    assert up == "HELLO USER"
    assert meta.get("shouted") == True
    print("Prompt Dialect Plugin check PASSED.")

if __name__ == "__main__":
    try:
        test_router_plugins()
        test_dialect_plugins()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
