from app.models.state import MissionState, MissionStatus
from app.system.preflight import PreFlightSystemCheck
from app.tools.drone import MockDrone
from app.tools.vision import MockVision


def run_check(drone=None, vision=None, battery=100.0):
    state = MissionState("PREFLIGHT-001", "Solar Panel Area A", battery=battery)
    results = PreFlightSystemCheck().run(state, drone or MockDrone(), vision or MockVision())
    return state, results


def test_successful_preflight_is_ready():
    state, results = run_check()
    assert state.mission_ready
    assert all(result.passed for result in results)


def test_gps_failure_is_critical():
    state, _ = run_check(MockDrone(gps_available=False))
    assert not state.mission_ready
    assert "GPS" in state.readiness_reason


def test_navigation_failure_is_critical():
    state, _ = run_check(MockDrone(navigation_available=False))
    assert not state.mission_ready
    assert "Navigation" in state.readiness_reason


def test_low_battery_is_not_ready():
    state, _ = run_check(battery=10.0)
    assert not state.mission_ready
    assert state.status == MissionStatus.PLANNING


def test_preflight_records_all_capabilities():
    state, results = run_check()
    assert [result.name for result in results] == [
        "GPS / Positioning", "Battery", "Camera", "Navigation Controller", "Geofence"
    ]
    assert len(state.preflight_results) == 5
