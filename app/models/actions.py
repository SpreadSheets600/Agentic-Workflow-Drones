from dataclasses import dataclass, field
from enum import Enum


class ActionType(Enum):
    """Executable capabilities exposed by the tool layer.

    Only these may be sent to SafetyValidator and the tools. Anything
    else (re-inspecting, verifying, aborting) is an agent-level
    *decision* (see DecisionType), never a physical drone command.
    """

    CHECK_BATTERY = "check_battery"
    CHECK_GPS = "check_gps"
    CHECK_CAMERA = "check_camera"
    CHECK_NAVIGATION = "check_navigation_controller"
    CHECK_GEOFENCE = "check_geofence"
    MOVE_TO_TARGET = "move_to_target"
    CAPTURE_IMAGE = "capture_image"
    DETECT_ANOMALY = "detect_anomaly"
    RETURN_TO_BASE = "return_to_base"
    GENERATE_REPORT = "generate_report"


@dataclass
class AgentAction:
    action_type: ActionType

    reason: str = ""


class DecisionType(Enum):
    """Mission-level decisions made by the agent.

    A decision explains *why*; it expands into zero or more executable
    AgentActions. For example RE_INSPECT expands into the execution
    sequence CAPTURE_IMAGE -> DETECT_ANOMALY, while VERIFY_FINDING needs
    no tool at all (it records the finding in mission memory).
    """

    PROCEED = "proceed"  # Execute the next step of the current plan.
    RETRY_CAPTURE = "retry_capture"  # Retry failed evidence collection.
    RE_INSPECT = "re_inspect"  # Collect and analyze more evidence.
    VERIFY_FINDING = "verify_finding"  # Record sufficient evidence.
    SAFE_RETURN = "safe_return"  # Return safely to base.
    ABORT = "abort"  # Stop the mission immediately.
    COMPLETE = "complete"  # Mark mission objectives achieved.


@dataclass
class AgentDecision:
    decision: DecisionType

    reason: str = ""

    # The single executable tool action to run next (None for purely
    # internal decisions such as VERIFY_FINDING, or terminal ones).
    next_action: AgentAction | None = None

    # Human-readable plan diff, set when the decision re-plans the mission.
    plan_update: str = ""
