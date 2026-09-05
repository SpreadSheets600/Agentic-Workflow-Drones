from dataclasses import dataclass, field
from enum import Enum


class MissionStatus(Enum):
    PLANNING = "planning"
    PRE_FLIGHT = "pre_flight"
    NAVIGATING = "navigating"
    INSPECTING = "inspecting"
    RE_INSPECTING = "re_inspecting"
    VERIFYING = "verifying"
    RETURNING = "returning"
    REPORTING = "reporting"
    COMPLETE = "complete"
    ABORTED = "aborted"


@dataclass
class MissionState:
    missionID: str
    target: str

    status: MissionStatus = MissionStatus.PLANNING
    battery: float = 100.0

    retries: int = 0
    maxRetries: int = 3

    currentLocation: str = "BASE"

    findings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    anomalyConfidence: float = 0.0

    requirements: list[str] = field(default_factory=list)
    initial_plan: list[str] = field(default_factory=list)
    plan_history: list[str] = field(default_factory=list)
    preflight_results: list[dict] = field(default_factory=list)
    mission_ready: bool = False
    readiness_reason: str = ""
    camera_retries: int = 0
    inspection_attempts: int = 0
    safety_decisions: list[str] = field(default_factory=list)

    # Structured mission memory (what happened during THIS mission).
    # This is distinct from RAG knowledge, which is static/external.
    failures: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    knowledge_sources: list[str] = field(default_factory=list)
    confidence_history: list[float] = field(default_factory=list)

    missionText: str = ""
    # Battery Floor For Movement Decisions. Default = MissionPolicy
    # Constant; Only A Parsed Mission Constraint May Change It, And The
    # Guardrail (Not The Agent) Still Enforces It.
    battery_floor: float = 30.0

    history: list[str] = field(default_factory=list)

    def transition(self, newStatus: MissionStatus):
        self.status = newStatus
        self.history.append(f"STATUS: {newStatus.value}")

    def record_event(self, event_type, details):
        self.history.append(f"{event_type}: {details}")
