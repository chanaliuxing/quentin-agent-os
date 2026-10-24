import sys
import asyncio
from typing import Dict, Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.infra.channels.provider import ChannelProvider

class MockChannel(ChannelProvider):
    @property
    def provider_id(self) -> str: return "mock"
    async def start(self): pass
    async def stop(self): pass
    async def send_text(self, target_id: str, text: str, **kwargs) -> None:
        print(f"Mock sent to {target_id}: {text}")
    def set_on_message(self, callback): self.cb = callback

def test_contract():
    c = MockChannel()
    assert c.provider_id == "mock"
    
    # Simulate inbound
    c.set_on_message(lambda x: print(f"Received: {x}"))
    if hasattr(c, "cb"):
        c.cb({"text": "hello"})
    
    print("ChannelContract: OK")

if __name__ == "__main__":
    test_contract()
