from dataclasses import dataclass, field
from enum import Enum


class ActionType(Enum):
    """Executable Capabilities Exposed By The Tool Layer.

    Only These May Be Sent To SafetyValidator And The Tools. Anything
    Else (Re-Inspecting, Verifying, Aborting) Is An Agent-Level
    *Decision* (See DecisionType), Never A Physical Drone Command.
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
    """Mission-Level Decisions Made By The Agent.

    A Decision Explains *Why*; It Expands Into Zero Or More Executable
    AgentActions. For Example RE_INSPECT Expands Into The Execution
    Sequence CAPTURE_IMAGE -> DETECT_ANOMALY, While VERIFY_FINDING Needs
    No Tool At All (It Records The Finding In Mission Memory).
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
