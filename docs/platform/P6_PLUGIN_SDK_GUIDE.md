# P6 Plugin SDK Guide

## Overview
Quentin supports external extensions through a standardized SDK. You can create three types of extensions:
- **Tools**: New capabilities for agents to interact with the world.
- **Skills**: New reasoning or domain-specific workflows.
- **Policies**: New governance or routing rules.

## Creating a Tool Plugin
1. Define your manifest.
2. Inherit from `ToolSDK`.
3. Register your handlers and schemas.

```python
from quentin.platform.sdk.tool_sdk import ToolSDK, ExtensionManifest

manifest = ExtensionManifest(name="my_tool", version="1.0.0", author="Me", description="...")
sdk = ToolSDK(manifest)
sdk.register_tool("my_action", my_handler, {"type": "object", ...})
```

## Registration
Register your provider with the `PlatformAPIGateway` to make it available in the system.
