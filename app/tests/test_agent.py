"""Agent loop tests.

A FakeRetriever stands in for the semantic model so these tests stay fast;
the real retriever is covered in test_retriever.py.
"""

import pytest

from app.agent.controller import AgentController
from app.agent.policies import MissionPolicy
from app.models.actions import ActionType, AgentAction, DecisionType
from app.models.observations import ToolObservation
from app.models.state import MissionState, MissionStatus
from app.safety.guardrails import SafetyValidator


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def retrieve(self, query, top_k=3):
        self.queries.append(query)
        if "previous anomalies" in query.lower():
            chunks = [
                {
                    "source": "history.txt",
                    "text": "Previous inspection: Possible surface anomaly detected.",
                    "score": 0.9,
                }
            ]
        else:
            chunks = [
                {
                    "source": "anomaly.txt",
                    "text": "A finding should only be confirmed when confidence is at least 0.70.",
                    "score": 0.9,
                },
                {
                    "source": "inspection.txt",
                    "text": "5. If anomaly confidence is below 0.70, collect additional evidence.",
                    "score": 0.8,
                },
            ]
        return chunks[:top_k]


class AlwaysFailVision:
    def captureImage(self, location):
        return ToolObservation(
            toolName="capture_image",
            success=False,
            message="Camera Timeout While Capturing Image",
            data={"location": location},
        )

    def detectAnomaly(self, imageID):
        raise AssertionError("must never detect without evidence")


def make_state(**overrides):
    base = {"missionID": "TEST-001", "target": "Solar Panel Area A"}
    base.update(overrides)
    return MissionState(**base)


def test_full_mission_completes(capsys):
    state = make_state()
    agent = AgentController(state, retriever=FakeRetriever())
    agent.run()

    assert state.status == MissionStatus.COMPLETE
    # Failure happened (first capture) and was recovered.
    assert state.retries == 1
    assert any("FAILURE" in h for h in state.history)
    # Evidence gating: weak evidence re-inspected, strong evidence verified.
    assert len(state.evidence) == 2
    assert state.anomalyConfidence == pytest.approx(0.93)
    assert state.findings
    # Drone returned safely and a report was generated.
    assert state.currentLocation == "BASE"
    assert "Anomaly Confirmed" in agent.report
    # RAG was actually consulted and recorded in mission memory.
    assert agent.rag_queries
    assert any("RAG:" in h for h in state.history)
    assert state.knowledge_sources
    # Re-planning happened: the initial plan was not the final plan.
    assert any("PLAN UPDATE" in h for h in state.history)
    # At least 3 distinct tools were used.
    tools = {h.split(":")[0] for h in state.history if ":" in h}
    assert {"check_battery", "move_to_target", "capture_image"} <= tools


def test_camera_failure_retries_capture():
    state = make_state()
    agent = AgentController(state, retriever=FakeRetriever())
    agent.run()
    decisions = [h for h in state.history if "retry_capture" in h]
    assert decisions, "agent must explicitly retry after the camera timeout"
    assert state.retries >= 1


def test_max_retries_abort_has_no_infinite_loop():
    state = make_state(maxRetries=2)
    agent = AgentController(
        state, vision=AlwaysFailVision(), retriever=FakeRetriever(), max_steps=10
    )
    agent.run()
    assert state.status == MissionStatus.ABORTED
    assert state.retries <= state.maxRetries


def test_low_confidence_triggers_reinspect_with_plan_update():
    state = make_state(
        status=MissionStatus.INSPECTING,
        currentLocation="Solar Panel Area A",
        evidence=["IMG-002"],
        anomalyConfidence=0.46,
    )
    agent = AgentController(state, retriever=FakeRetriever())
    agent._battery_checked = True
    agent._detections_done = 1  # the single evidence item has been analyzed
    decision = agent._decide()
    assert decision.decision == DecisionType.RE_INSPECT
    assert "0.46" in decision.reason
    # RE_INSPECT is a reasoning decision, not a drone tool: no tool action.
    assert decision.next_action is None
    assert decision.plan_update
    assert agent.rag_queries, "low confidence must trigger knowledge retrieval"


def test_high_confidence_allows_verification():
    state = make_state(
        status=MissionStatus.INSPECTING,
        currentLocation="Solar Panel Area A",
        evidence=["IMG-002", "IMG-003"],
        anomalyConfidence=0.93,
    )
    agent = AgentController(state, retriever=FakeRetriever())
    agent._battery_checked = True
    agent._detections_done = 2
    decision = agent._decide()
    assert decision.decision == DecisionType.VERIFY_FINDING
    assert decision.next_action is None  # internal: records finding, no tool


def test_reinspect_decision_expands_into_executable_actions():
    """Decisions reason; only tool actions execute. RE_INSPECT is internal,
    the follow-up step is a real CAPTURE_IMAGE the validator can check."""
    state = make_state(
        status=MissionStatus.INSPECTING,
        currentLocation="Solar Panel Area A",
        evidence=["IMG-002"],
        anomalyConfidence=0.46,
    )
    agent = AgentController(state, retriever=FakeRetriever())
    agent._battery_checked = True
    agent._detections_done = 1

    reinspect = agent._decide()
    assert reinspect.decision == DecisionType.RE_INSPECT
    assert reinspect.next_action is None

    # Apply the re-plan, then the next decision must be executable.
    state.transition(MissionStatus.RE_INSPECTING)
    follow_up = agent._decide()
    assert follow_up.next_action is not None
    assert isinstance(follow_up.next_action.action_type, ActionType)
    assert follow_up.next_action.action_type == ActionType.CAPTURE_IMAGE
    allowed, _ = SafetyValidator.validate(follow_up.next_action, state)
    assert allowed


def test_validator_rejects_non_executable_decisions():
    with pytest.raises(TypeError):
        SafetyValidator.validate(
            AgentAction(action_type=DecisionType.RE_INSPECT), make_state()
        )


def test_every_decision_carries_a_reason():
    state = make_state(
        status=MissionStatus.INSPECTING,
        currentLocation="Solar Panel Area A",
        evidence=["IMG-002"],
        anomalyConfidence=0.46,
    )
    agent = AgentController(state, retriever=FakeRetriever())
    agent._battery_checked = True
    agent._detections_done = 1
    for _ in range(6):
        decision = agent._decide()
        assert decision.decision is not None and decision.reason.strip()
        if decision.next_action is not None:
            assert decision.next_action.reason.strip()
        # Advance a minimal simulation so decisions evolve.
        if decision.decision == DecisionType.RE_INSPECT:
            state.transition(MissionStatus.RE_INSPECTING)
        elif decision.decision == DecisionType.VERIFY_FINDING:
            break
        elif decision.next_action is not None:
            if decision.next_action.action_type == ActionType.CAPTURE_IMAGE:
                state.evidence.append(f"IMG-{len(state.evidence) + 10:03d}")
            elif decision.next_action.action_type == ActionType.DETECT_ANOMALY:
                agent._detections_done += 1
                state.anomalyConfidence = 0.93
        else:
            break


def test_low_battery_mission_aborts_without_moving():
    state = make_state(battery=10.0)
    agent = AgentController(state, retriever=FakeRetriever())
    agent.run()
    # Safety sits between agent and tools: navigation never executes.
    assert state.currentLocation == "BASE"
    assert state.status == MissionStatus.ABORTED


def test_evidence_threshold_is_general():
    assert not MissionPolicy.evidenceIsSufficient(
        MissionPolicy.EVIDENCE_THRESHOLD - 0.01
    )
    assert MissionPolicy.evidenceIsSufficient(MissionPolicy.EVIDENCE_THRESHOLD)
