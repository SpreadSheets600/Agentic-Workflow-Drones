from app.agent.policies import MissionPolicy
from app.models.actions import ActionType, AgentAction
from app.models.state import MissionState


class SafetyValidator:
    """Deterministic safety layer for *executable* tool actions only.

    The agent decides what it wants to do (AgentDecision); this validator
    decides whether the proposed tool action is allowed to execute. It
    never performs semantic reasoning -- only deterministic checks.
    """

    @staticmethod
    def validate(action: AgentAction, state: MissionState, preflight=False):
        if not isinstance(action.action_type, ActionType):
            raise TypeError(
                "SafetyValidator only validates executable AgentActions, "
                f"got {type(action.action_type).__name__}. Agent decisions "
                "(RE_INSPECT, VERIFY_FINDING, ...) must first expand into "
                "tool actions before validation."
            )

        if action.action_type == ActionType.MOVE_TO_TARGET and not MissionPolicy.batteryIsSafe(state.battery, floor=state.battery_floor):
            return False, "Battery Too Low For Navigation"

        if action.action_type == ActionType.MOVE_TO_TARGET and state.preflight_results and not state.mission_ready and not preflight:
            return False, "Mission Is Not Pre-Flight Ready"

        if action.action_type == ActionType.MOVE_TO_TARGET and state.currentLocation != "BASE":
            return False, "Drone Is Not At Base For Departure"

        if action.action_type == ActionType.CAPTURE_IMAGE:
            if state.currentLocation == "BASE":
                return False, "Cannot Capture Image At Base"
            # Backstop Against Infinite Evidence-Collection Loops. If The
            # Decision Layer Misbehaves, No More Captures Are Allowed.
            retry_count = max(state.camera_retries, state.retries)
            if not MissionPolicy.retriesAllowed(retry_count, limit=state.maxRetries):
                return False, "No Retries Left For Evidence Collection"

        if action.action_type == ActionType.DETECT_ANOMALY and not state.evidence:
            return False, "No Evidence To Detect Anomaly"

        if action.action_type == ActionType.GENERATE_REPORT and not state.evidence and state.status.value != "aborted":
            return False, "No Evidence To Report"

        return True, "Action Approved"
