import asyncio
import os
from quentin.infra.llm.ollama_client import OllamaClient

async def test_ollama_urls():
    print("--- Testing Ollama URL Sanitization ---")
    test_urls = ["http://localhost:11434", "http://localhost:11434/", "http://localhost:11434/api/generate"]
    for url in test_urls:
        client = OllamaClient(base_url=url, name="qwen2.5:latest")
        final_url = f"{client.base_url}/api/generate"
        print(f"Input: {url} -> Target: {final_url}")
        assert final_url == "http://localhost:11434/api/generate"

async def test_ollama_call():
    print("--- Testing Real Ollama Call ---")
    client = OllamaClient(base_url="http://localhost:11434", name="qwen2.5:latest")
    messages = [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]
    try:
        res = await client.generate(messages)
        print(f"Result OK: {res.text[:10]}...")
    except Exception as e:
        print(f"Call failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama_urls())
    asyncio.run(test_ollama_call())
