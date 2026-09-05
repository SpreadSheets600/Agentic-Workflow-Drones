"""Reporting tests: the final report must explain the decision path."""

from app.models.state import MissionState, MissionStatus
from app.tools.reporting import generate_report


def make_completed_state():
    state = MissionState(missionID="MISSION-001", target="Solar Panel Area A")
    state.status = MissionStatus.COMPLETE
    state.battery = 80.0
    state.currentLocation = "BASE"
    state.retries = 1
    state.evidence = ["IMG-002", "IMG-003"]
    state.anomalyConfidence = 0.93
    state.confidence_history = [0.46, 0.93]
    state.findings = ["Possible surface anomaly confirmed (confidence 0.93)"]
    state.failures = ["capture_image: Camera Timeout While Capturing Image"]
    state.decisions = [
        "retry_capture: Evidence is required before anomaly analysis.",
        "re_inspect: Current confidence 0.46 is below the threshold.",
        "verify_finding: Evidence confidence 0.93 meets the threshold.",
    ]
    state.knowledge_sources = ["anomaly.txt", "inspection.txt", "history.txt"]
    state.history = [
        "check_battery: Battery Level Is 100.0",
        "move_to_target: Moved To Target Solar Panel Area A",
        "FAILURE: capture_image: Camera Timeout While Capturing Image",
        "DECISION: retry_capture (evidence required)",
        "capture_image: Image Captured Successfully",
        "RAG: anomaly confidence query -> ['anomaly.txt']",
        "DECISION: RE_INSPECT (confidence 0.46 below threshold)",
        "PLAN UPDATE: Previous plan -> Updated plan",
        "return_to_base: Returned To Base",
    ]
    return state


def test_report_covers_decision_path():
    report = generate_report(make_completed_state())
    for section in (
        "Mission Report",
        "Finding:",
        "Confidence:\n0.93",
        "Mission Events:",
        "Failure Handling:",
        "Knowledge Used:",
        "Final Battery:",
        "Outcome:",
    ):
        assert section in report


def test_report_events_tell_the_story_in_order():
    report = generate_report(make_completed_state())
    events = report.split("Mission Events:")[1].split("Failure Handling:")[0]
    for fragment in (
        "Battery Verified",
        "Navigated To Target",
        "Capture Failed",
        "Retried Evidence Collection",
        "Confidence 0.46",
        "Knowledge Indicated",
        "Re-Planned",
        "Confidence 0.93",
        "Verified",
        "Returned To Base",
    ):
        assert fragment in events, f"missing event: {fragment}"
    numbered = [
        line for line in events.splitlines() if line.strip() and line.strip()[0].isdigit()
    ]
    assert len(numbered) >= 8


def test_report_lists_knowledge_and_failures():
    report = generate_report(make_completed_state())
    assert "anomaly.txt" in report
    assert "Camera Failures: 1" in report
    assert "Retries: 1" in report
    assert "Maximum Retries: 3" in report
    assert "Anomaly Confirmed After Additional Inspection" in report
