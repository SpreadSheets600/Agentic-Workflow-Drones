from dataclasses import dataclass
from typing import Any


@dataclass
class ToolObservation:
    success: bool

    toolName: str

    message: str
    data: dict[str, Any]
