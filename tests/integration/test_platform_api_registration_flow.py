import pytest
from quentin.platform.sdk.base import ExtensionManifest
from quentin.platform.sdk.tool_sdk import ToolSDK
from quentin.platform.api_gateway import PlatformAPIGateway
from quentin.capabilities.catalog import CapabilityCatalog

def test_full_registration_flow():
    # 1. Setup
    catalog = CapabilityCatalog()
    gateway = PlatformAPIGateway(catalog)
    
    # 2. Create provider
    manifest = ExtensionManifest(name="cloud_tools", version="1.2.0", author="TeamX", description="Cloud utilities")
    sdk = ToolSDK(manifest)
    sdk.register_tool("s3_upload", lambda x: "uploaded", {"type": "object"})
    
    # 3. Register
    gateway.register_provider(sdk)
    
    # 4. Verify Catalog Integration
    caps = catalog.list_all()
    target = next((c for c in caps if c.name == "s3_upload"), None)
    assert target is not None
    assert target.metadata["provider"] == "cloud_tools"
    assert target.metadata["version"] == "1.2.0"
