from app.models.state import MissionState


def generate_report(state: MissionState):
    """Build The Final Inspection Report From Mission Memory.

    Mission Memory (Events, Failures, Decisions, Confidence History)
    Explains This Flight; The Knowledge Used Section Credits The
    Static Rag Sources That Influenced Decisions Along The Way.
    """
    lines = [
        "Mission Report",
        "==============",
        "",
        "Mission:",
        state.missionID,
        "",
        "Target:",
        state.target,
        "",
        "Final Status:",
        state.status.value.replace("_", " ").title(),
        "",
        "System Readiness:",
        "Ready" if state.mission_ready else "Not Ready",
        state.readiness_reason,
        "",
        "Initial Plan:",
        *[f"{i}. {step.replace('_', ' ').title()}" for i, step in enumerate(state.initial_plan, 1)],
        "",
        "Actual Decision Path:",
        *(state.decisions if state.decisions else ["(None)"]),
        "",
        "Finding:",
        (state.findings[-1] if state.findings else "No Confirmed Anomaly"),
        "",
        "Anomaly Narrative (Mock LLM):",
        _narrative(state),
        "",
        "Confidence:",
        f"{state.anomalyConfidence:.2f}",
        "",
        "Evidence:",
        *(state.evidence if state.evidence else ["(None)"]),
        "",
        "Mission Events:",
        *[
            f"{i}. {event}"
            for i, event in enumerate(_mission_events(state), 1)
        ],
        "",
        "Failure Handling:",
        f"Camera Failures: {len(state.failures)}",
        f"Retries: {state.retries}",
        f"Maximum Retries: {state.maxRetries}",
        "",
        "Knowledge Used:",
        *(state.knowledge_sources if state.knowledge_sources else ["(None)"]),
        "",
        "Final Battery:",
        f"{state.battery:.0f}%",
        "",
        "Final Location:",
        state.currentLocation,
        "",
        "Safety Decisions:",
        *(state.safety_decisions if state.safety_decisions else ["(None)"]),
        "",
        "Outcome:",
        _outcome_text(state),
        "",
        "Inspection Summary:",
        _summary(state),
    ]
    return "\n".join(lines)


def _narrative(state: MissionState):
    """Mock LLM narrative writer.

    A real deployment would hand the structured facts (finding,
    confidence, evidence, failure/retry history) to an LLM and ask for a
    short human-readable narrative. Here the prose is templated from the
    same facts so the demo stays deterministic. Boundary (unchanged):
    the narrative only REWORDS facts already in mission memory — it can
    never change the finding, the confidence, or the outcome.
    """
    if state.status.value == "aborted":
        return (
            "The flight was stopped safely before completing inspection. "
            "No anomaly finding is reported from this mission."
        )
    if not state.findings:
        return (
            f"The drone surveyed {state.target} and captured "
            f"{len(state.evidence)} image(s), but no anomaly was confirmed "
            "above the evidence threshold."
        )
    attempts = len(state.confidence_history)
    failures = len(state.failures)
    recovery = (
        f" The agent recovered from {failures} tool failure(s) en route."
        if failures
        else ""
    )
    replan = (
        " Confidence was initially below threshold, so the agent re-planned "
        "and collected additional evidence before confirming."
        if attempts > 1
        else ""
    )
    return (
        f"A surface anomaly on the inspected panel at {state.target} was "
        f"confirmed at confidence {state.anomalyConfidence:.2f} across "
        f"{attempts} analysis pass(es){replan}{recovery} "
        "Maintenance follow-up is recommended."
    )


def _mission_events(state: MissionState):
    """Deterministic Narrative Of What Actually Happened, Oldest First."""
    events: list[str] = []
    history = " ".join(state.history)

    for result in state.preflight_results:
        events.append(f"Pre-Flight {result['name']}: {'Passed' if result['passed'] else 'Failed'}.")

    if "check_battery" in history:
        events.append(f"Battery Verified At {_verified_battery(state)}.")
    if "move_to_target" in history and "Moved To Target" in history:
        events.append("Drone Navigated To Target.")
    for failure in state.failures:
        if "capture_image" in failure or "Timeout" in failure:
            events.append("Initial Image Capture Failed (Camera Timeout).")
        else:
            events.append(f"Tool Failure: {failure}.")
    if any("retry_capture" in d for d in state.decisions):
        events.append("Agent Retried Evidence Collection.")
    if any(h.startswith("capture_image: ") for h in state.history):
        plural = "s" if len(state.evidence) != 1 else ""
        events.append(
            f"Image Captured Successfully ({len(state.evidence)} Image{plural} Total)."
        )
    for i, confidence in enumerate(state.confidence_history, 1):
        events.append(f"Anomaly Detection #{i}: Confidence {confidence:.2f}.")
    if any("RE_INSPECT" in h or "re_inspect" in h for h in state.history):
        if state.knowledge_sources:
            events.append("Semantic Knowledge Indicated That Evidence Was Insufficient.")
        events.append("Agent Re-Planned Inspection (Additional Evidence).")
    if state.findings:
        events.append(f"Finding Verified At Confidence {state.anomalyConfidence:.2f}.")
    if state.currentLocation == "BASE" and "return_to_base" in history:
        events.append("Drone Returned To Base.")
    if not events:
        events.extend(state.history or ["No Mission Events Recorded."])
    return events


def _verified_battery(state: MissionState):
    for entry in state.history:
        if entry.startswith("check_battery: Battery Level Is"):
            try:
                return f"{float(entry.rsplit(' ', 1)[-1]):.0f}%"
            except ValueError:
                pass
    return f"{state.battery:.0f}%"


def _outcome_text(state: MissionState):
    if state.status.value == "complete" and state.findings:
        return (
            "Anomaly Confirmed After Additional Inspection "
            "And Drone Safely Returned To Base."
        )
    if state.status.value == "complete":
        return "Inspection Complete; No Anomaly Confirmed. Drone Safely Returned To Base."
    if state.status.value == "aborted":
        return "Mission Aborted Safely After Exhausting Retries Or Failing A Safety Check."
    return f"Mission Ended With Status: {state.status.value}."


def _summary(state):
    if state.status.value == "aborted":
        return "The mission was stopped safely before completion."
    if state.findings:
        return (f"Collected {len(state.evidence)} image(s), recovered from "
                f"{len(state.failures)} failure(s), and confirmed the finding "
                f"after {len(state.confidence_history)} analysis attempt(s).")
    return f"Collected {len(state.evidence)} image(s); no finding was confirmed."
