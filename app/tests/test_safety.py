"""Safety boundary tests: the agent proposes, SafetyValidator disposes."""

from app.agent.policies import MissionPolicy
from app.models.actions import ActionType, AgentAction
from app.models.state import MissionState, MissionStatus
from app.safety.guardrails import SafetyValidator


def make_state(**overrides):
    base = {
        "missionID": "TEST-001",
        "target": "Solar Panel Area A",
    }
    base.update(overrides)
    return MissionState(**base)


def test_low_battery_blocks_navigation():
    state = make_state(battery=10.0)
    allowed, reason = SafetyValidator.validate(
        AgentAction(ActionType.MOVE_TO_TARGET), state
    )
    assert not allowed
    assert "Battery" in reason


def test_sufficient_battery_allows_navigation():
    state = make_state(battery=MissionPolicy.MIN_BATTERY)
    allowed, _ = SafetyValidator.validate(
        AgentAction(ActionType.MOVE_TO_TARGET), state
    )
    assert allowed


def test_detect_without_evidence_blocked():
    state = make_state(currentLocation="Solar Panel Area A", evidence=[])
    allowed, reason = SafetyValidator.validate(
        AgentAction(ActionType.DETECT_ANOMALY), state
    )
    assert not allowed
    assert "Evidence" in reason


def test_detect_with_evidence_allowed():
    state = make_state(
        currentLocation="Solar Panel Area A", evidence=["IMG-002"]
    )
    allowed, _ = SafetyValidator.validate(
        AgentAction(ActionType.DETECT_ANOMALY), state
    )
    assert allowed


def test_capture_at_base_blocked():
    state = make_state(currentLocation="BASE")
    allowed, _ = SafetyValidator.validate(
        AgentAction(ActionType.CAPTURE_IMAGE), state
    )
    assert not allowed


def test_capture_at_target_allowed():
    state = make_state(currentLocation="Solar Panel Area A")
    allowed, _ = SafetyValidator.validate(
        AgentAction(ActionType.CAPTURE_IMAGE), state
    )
    assert allowed


def test_capture_blocked_when_retry_budget_spent():
    """Backstop against infinite evidence-collection loops at the safety
    layer (the decision layer checks the budget first)."""
    state = make_state(
        currentLocation="Solar Panel Area A",
        retries=MissionPolicy.MAX_RETRIES,
    )
    allowed, reason = SafetyValidator.validate(
        AgentAction(ActionType.CAPTURE_IMAGE), state
    )
    assert not allowed
    assert "Retries" in reason


def test_capture_allowed_with_retry_budget_left():
    state = make_state(currentLocation="Solar Panel Area A", retries=1)
    allowed, _ = SafetyValidator.validate(
        AgentAction(ActionType.CAPTURE_IMAGE), state
    )
    assert allowed


def test_report_blocked_without_evidence():
    state = make_state(status=MissionStatus.RETURNING, evidence=[])
    allowed, _ = SafetyValidator.validate(
        AgentAction(ActionType.GENERATE_REPORT), state
    )
    assert not allowed
