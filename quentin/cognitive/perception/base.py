from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pathlib import Path

class PerceptionProvider(ABC):
    """
    Base class for perception providers that feed into the brain's situational awareness.
    """
    
    @abstractmethod
    def get_perception_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a dictionary of perception data to be included in the PerceptionSnapshot.
        """
        pass
