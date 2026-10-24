from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from quentin.capabilities.catalog import CapabilityCatalog, Capability, LifecycleStatus

logger = logging.getLogger(__name__)

class LifecycleManager:
    """
    P4-D: Lifecycle Manager
    Manages the lifecycle transitions of capabilities.
    """
    def __init__(self, catalog: CapabilityCatalog) -> None:
        self.catalog = catalog

    def promote(self, capability_id: str) -> bool:
        """
        Promote a capability to the next level of trust.
        """
        cap = self.catalog.get(capability_id)
        if not cap:
            return False
        
        if cap.status == LifecycleStatus.EXPERIMENTAL:
            cap.status = LifecycleStatus.TRUSTED
            logger.info("Capability %s promoted to TRUSTED.", capability_id)
            return True
        elif cap.status == LifecycleStatus.DEPRECATED:
            cap.status = LifecycleStatus.TRUSTED
            logger.info("Capability %s restored to TRUSTED.", capability_id)
            return True
        return False

    def deprecate(self, capability_id: str) -> bool:
        """
        Mark a capability as deprecated.
        """
        cap = self.catalog.get(capability_id)
        if not cap:
            return False
        
        cap.status = LifecycleStatus.DEPRECATED
        logger.info("Capability %s DEPRECATED.", capability_id)
        return True

    def retire(self, capability_id: str) -> bool:
        """
        Mark a capability as retired.
        """
        cap = self.catalog.get(capability_id)
        if not cap:
            return False
        
        # Check dependencies before retirement
        if self._has_active_dependencies(capability_id):
             logger.warning("Capability %s has active dependencies. Cannot retire.", capability_id)
             return False
             
        cap.status = LifecycleStatus.RETIRED
        logger.info("Capability %s RETIRED.", capability_id)
        return True

    def _has_active_dependencies(self, capability_id: str) -> bool:
        """
        Heuristic dependency check.
        """
        # In a real system, this would scan skills and tools that depend on this capability.
        return False
