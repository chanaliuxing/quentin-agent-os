from typing import Callable, Awaitable, Dict, Any, List


# 统一约定：variant 函数签名
VariantFunc = Callable[[Dict[str, Any]], Awaitable[Any]]


class VariantRegistry:
    """
    管理各模块的多个 variant：
    - module_name -> variant_name -> async func(input) -> output

    这里不假设具体模块（planner/critic/...），只约定“输入/输出都是 Dict 或其他 JSON-able 对象”，
    方便在 EvalHarness 里统一调用。
    """

    def __init__(self):
        self._registry: Dict[str, Dict[str, VariantFunc]] = {}

    def register(self, module_name: str, variant_name: str, func: VariantFunc):
        if module_name not in self._registry:
            self._registry[module_name] = {}
        self._registry[module_name][variant_name] = func

    def list_variants(self, module_name: str) -> List[str]:
        return list(self._registry.get(module_name, {}).keys())

    def get(self, module_name: str, variant_name: str) -> VariantFunc:
        module_variants = self._registry.get(module_name, {})
        if variant_name not in module_variants:
            raise KeyError(f"Variant not found: {module_name}.{variant_name}")
        return module_variants[variant_name]
