from __future__ import annotations
import logging
from typing import Dict, Any, List
from quentin.platform.sdk.base import BaseSDK
from quentin.capabilities.catalog import CapabilityCatalog, Capability, CapabilityType

logger = logging.getLogger(__name__)

class PlatformAPIGateway:
    """
    P6-A: Platform API Gateway
    Central registry for platform extensions.
    """
    def __init__(self, catalog: CapabilityCatalog) -> None:
        self.catalog = catalog
        self.providers: Dict[str, BaseSDK] = {}

    def register_provider(self, provider: BaseSDK) -> None:
        self.providers[provider.manifest.name] = provider
        # Automatically register capabilities in the catalog
        for cap_info in provider.get_capabilities():
            cap = Capability(
                name=cap_info["name"],
                type=CapabilityType(cap_info["type"]),
                description=provider.manifest.description,
                metadata={
                    "provider": provider.manifest.name,
                    "version": provider.manifest.version,
                    **cap_info.get("schema", {})
                }
            )
            self.catalog.register(cap)
        logger.info("Platform Provider '%s' registered.", provider.manifest.name)

    def list_providers(self) -> List[str]:
        return list(self.providers.keys())
