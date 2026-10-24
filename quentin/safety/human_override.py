from __future__ import annotations
import os

class HumanOverride:
    """
    P8-D: Human Override Channel
    Allows operators to freeze evolution or force rollbacks.
    """
    def __init__(self) -> None:
        self.evolution_frozen: bool = False

    def freeze_evolution(self) -> None:
        self.evolution_frozen = True
        os.environ["FF_ROADMAP_EVOLUTION_V1"] = "0"

    def unfreeze_evolution(self) -> None:
        self.evolution_frozen = False
        # Do not auto-enable, let operator decide
