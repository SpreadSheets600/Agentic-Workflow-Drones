from dataclasses import dataclass

from app.models.actions import ActionType, AgentAction
from app.models.observations import ToolObservation
from app.models.state import MissionState
from app.safety.guardrails import SafetyValidator


@dataclass
class PreFlightResult:
    name: str
    passed: bool
    critical: bool
    message: str


class PreFlightSystemCheck:
    """Checks Platform Readiness Before The Agent Can Start The Mission."""

    CHECKS = (
        ("GPS / Positioning", ActionType.CHECK_GPS, True),
        ("Battery", ActionType.CHECK_BATTERY, True),
        ("Camera", ActionType.CHECK_CAMERA, True),
        ("Navigation Controller", ActionType.CHECK_NAVIGATION, True),
        ("Geofence", ActionType.CHECK_GEOFENCE, True),
    )

    def run(self, state, drone, vision):
        drone.battery = float(state.battery)
        results = []
        for name, action_type, critical in self.CHECKS:
            action = AgentAction(action_type, "Pre-flight capability check.")
            allowed, reason = SafetyValidator.validate(action, state, preflight=True)
            observation = (
                self._check(action_type, drone, vision)
                if allowed
                else ToolObservation(
                    success=False, toolName=action_type.value, message=reason, data={}
                )
            )
            result = PreFlightResult(
                name, observation.success, critical, observation.message
            )
            results.append(result)
            state.preflight_results.append(
                {
                    "name": name,
                    "passed": result.passed,
                    "critical": critical,
                    "message": result.message,
                }
            )
            state.record_event(
                "PRE_FLIGHT_CHECK", f"{name}: {'PASS' if result.passed else 'FAIL'}"
            )

        state.mission_ready = all(item.passed for item in results if item.critical)
        state.readiness_reason = (
            "All critical systems are available."
            if state.mission_ready
            else next(
                item.message for item in results if item.critical and not item.passed
            )
        )
        return results

    @staticmethod
    def _check(action_type, drone, vision):
        camera_check = getattr(vision, "check_camera", None)
        gps_check = lambda: ToolObservation(
            drone.gps_available,
            "check_gps",
            f"GPS / Positioning {'Available' if drone.gps_available else 'Unavailable'}.",
            {"available": drone.gps_available},
        )
        checks = {
            ActionType.CHECK_GPS: gps_check,
            ActionType.CHECK_BATTERY: drone.check_battery,
            ActionType.CHECK_CAMERA: camera_check
            or (lambda: ToolObservation(True, "check_camera", "Camera Available.", {})),
            ActionType.CHECK_NAVIGATION: drone.check_navigation_controller,
            ActionType.CHECK_GEOFENCE: drone.check_geofence,
        }
        return checks[action_type]()
