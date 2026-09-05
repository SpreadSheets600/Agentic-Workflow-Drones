"""Tests for the mock-AI seams: NLP mission parser, failure advisor,
tool watchdog, and the mock-LLM report narrative."""

from app.agent.advisor import FailureAdvisor
from app.agent.controller import AgentController
from app.mission import NLPMissionParser
from app.models.actions import AgentAction, ActionType
from app.models.state import MissionState
from app.tools.reporting import generate_report
from app.tools.vision import MockVision

import time


def test_nlp_parser_extracts_target_capabilities_and_constraint():
    parser = NLPMissionParser()
    context = parser.parse(
        "Inspect the north solar field and take photos; return when battery hits 45%"
    )
    assert context.source == "nlp"
    assert "North Solar Field" in context.requirements.target
    assert "camera" in context.requirements.required_capabilities
    assert context.battery_floor == 45.0


def test_nlp_parser_defaults_without_constraints():
    context = NLPMissionParser().parse("Check the wind turbines for damage")
    assert context.battery_floor is None  # falls back to policy default 30
    assert context.requirements.target


def test_advisor_classifies_transient_and_permanent():
    assert FailureAdvisor.classify("Camera Timeout After 2.0s") == "transient"
    assert FailureAdvisor.classify("Navigation Capability Unavailable") == "permanent"


from app.tools.drone import MockDrone


def test_tool_watchdog_converts_hang_to_failure_observation():
    class HangingDrone(MockDrone):
        def check_battery(self):
            time.sleep(1.5)  # longer than the controller watchdog
            return super().check_battery()

    state = MissionState(missionID="M-T", target="X")
    controller = AgentController(state, drone=HangingDrone(), tool_timeout=0.2)
    observation = controller.call_tool(AgentAction(ActionType.CHECK_BATTERY))
    assert observation.success is False
    assert "Timed Out" in observation.message
    # The failure went through the normal pipeline into mission history.
    controller.update_state(observation)
    assert any("timed out" in h.lower() for h in state.history)


def test_report_contains_mock_llm_narrative():
    state = MissionState(missionID="M-N", target="Solar Panel Area A")
    state.evidence = ["IMG-001", "IMG-002"]
    state.findings = ["Scratched Panel"]
    state.confidence_history = [0.46, 0.93]
    state.anomalyConfidence = 0.93
    state.failures = ["capture_image: Camera Timeout After 2.0s"]
    state.mission_ready = True
    report = generate_report(state)
    assert "Anomaly Narrative (Mock LLM)" in report
    assert "0.93" in report
    assert "re-planned" in report
