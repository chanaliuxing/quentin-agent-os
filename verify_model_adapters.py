import asyncio
import logging
from typing import List, Dict
from quentin.infra.llm import ModelClient, adapter_registry, ModelClientFactory

logging.basicConfig(level=logging.INFO)

# 1. Simulate "AI writing a new adapter"
class DeepSeekAdapter(ModelClient):
    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        async def _run():
            # Mock implementation
            return f"[DEEPSEEK-MOCK] Response for {messages[-1]['content']}"
        
        # Use retry strategy
        return await self.retry_strategy.execute(_run, label=f"deepseek:{self.name}")

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        return [[0.1] * 5 for _ in texts]

# 2. Register the new adapter
adapter_registry.register("deepseek", DeepSeekAdapter)

async def main():
    print("Listing registered providers:", adapter_registry.list_providers())
    
    # 3. Use factory to create a client
    for model_id in ["deepseek-chat", "claude-3-5-sonnet-20240620", "gemini-1.5-pro"]:
        client = ModelClientFactory.create_client(model_id)
        print(f"\n--- Testing Model: {model_id} ---")
        print(f"Created client class: {client.__class__.__name__}")
        print(f"Provider: {client.provider}")
        
        # We skip actual generation if we don't have real keys, 
        # but the class instantiation and field resolution are verified.
        if client.provider == "deepseek":
             resp = await client.generate([{"role": "user", "content": "Hello!"}])
             print("Response (Mocked):", resp)

if __name__ == "__main__":
    asyncio.run(main())
