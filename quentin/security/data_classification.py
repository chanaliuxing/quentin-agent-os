from __future__ import annotations
from enum import Enum
from dataclasses import dataclass

class DataSensitivity(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"

@dataclass
class DataTag:
    sensitivity: DataSensitivity
    owner: str
    retention_days: int = 365
