import asyncio
from quentin.infra.llm.ollama_client import OllamaClient

async def run():
    print("Test Starting...")
    c = OllamaClient(base_url="http://localhost:11434", name="qwen3-vl:latest")
    m = [{"role": "user", "content": "hi"}]
    try:
        # This will trigger the new print in _call_api
        r = await asyncio.wait_for(c.generate(m), timeout=30)
        print("Test OK")
    except Exception as e:
        print("Test Info: " + str(e))

if __name__ == "__main__":
    asyncio.run(run())
