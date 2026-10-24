from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class InteractionStep:
    input_text: str
    expected_prompt_hash: str
    step_index: int

class ReplayBuffer:
    """
    P5: Ported from OpenClaw's interactive replay logic.
    Stores terminal inputs and their corresponding environment anchors.
    """
    def __init__(self):
        self.steps: List[InteractionStep] = []

    def record_step(self, input_text: str, current_stdout_tail: str):
        """
        Snapshots the environment before sending input.
        """
        # Create a stable hash of the prompt
        prompt_hash = hashlib.md5(current_stdout_tail.strip().encode("utf-8")).hexdigest()
        
        step = InteractionStep(
            input_text=input_text,
            expected_prompt_hash=prompt_hash,
            step_index=len(self.steps)
        )
        self.steps.append(step)
        logger.debug(f"ReplayBuffer: Recorded step {step.step_index} with prompt hash {prompt_hash[:8]}")

    def clear(self):
        self.steps = []

    def get_steps(self) -> List[InteractionStep]:
        return self.steps
