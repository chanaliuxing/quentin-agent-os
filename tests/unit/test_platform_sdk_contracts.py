import pytest
from quentin.platform.sdk.base import ExtensionManifest
from quentin.platform.sdk.tool_sdk import ToolSDK
from quentin.platform.api_gateway import PlatformAPIGateway
from quentin.capabilities.catalog import CapabilityCatalog

def test_tool_sdk_registration():
    manifest = ExtensionManifest(name="test_provider", version="1.0.0", author="Alice", description="Test")
    sdk = ToolSDK(manifest)
    sdk.register_tool("hello", lambda x: "hi", {"type": "object"})
    
    catalog = CapabilityCatalog()
    gateway = PlatformAPIGateway(catalog)
    gateway.register_provider(sdk)
    
    assert "test_provider" in gateway.list_providers()
    caps = catalog.list_all()
    assert len(caps) > 0
    assert caps[0].name == "hello"
    assert caps[0].metadata["provider"] == "test_provider"
