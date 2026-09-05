# Demo Guide

## Setup

```bash
python -m pytest app/tests -q    # unit tests (state transitions, guardrails, reporting, retrieval)
```

All scenarios run on a laptop; the drone, camera, and detector are mocked. The first `mission` run downloads a small embedding model (~90 MB) for the optional RAG layer; if it is unavailable, the mission still completes retrieval failures are caught and printed.

## Scenario 0 Free-text mission (mock NLP parser)

```bash
python -m app.main --mission "Inspect the north solar field and take photos; return when battery hits 45%"
```

Demonstrates the mock-LLM mission-parsing seam: the header prints `Mission Source: Free text (mock NLP parser)`, then the parsed target (`The North Solar Field`) and the parsed battery constraint (`return when battery hits 45%`). The rest of the mission runs exactly like Scenario 1 the parser only *proposes* the target and constraint; the guardrails enforce them. Run without `--mission` and you get the structured mission (`Mission Source: Structured (static parser)`), which is a nice live contrast to show the seam works both ways.

## Scenario 1 Full mission (the one to present)

```bash
python -m app.main --scenario mission
```

What the audience sees, in order:

1. **Mission received** MISSION-001, target "Solar Panel Area A", requirements listed.
2. **Initial plan printed** check_battery → move_to_target → capture_image → detect_anomaly → verify_finding → return_to_base → generate_report.
3. **Pre-flight** five PASS lines; "Mission Readiness: Ready".
4. **Tool calls with the fixed trace vocabulary**, e.g.:
   ```
   Decision: Proceed
   Reason: Confirm battery before departure.
   Action: Check Battery
   Safety: Action Approved
   Observation: Battery Level Is 100%.
   ```
5. **Failure #1 (visible failure handling):** first `Capture Image` → "Camera Timeout While Capturing Image" → `Decision: Retry Capture` → second capture succeeds.
6. **Unexpected result #2:** `Detect Anomaly` → "Possible Anomaly Detected (Weak Evidence)".
7. **Knowledge consultation:** three "Relevant Knowledge" lines (inspection guidelines say confirm at ≥ 0.70; history says this area had a previous anomaly).
8. **Visible re-plan:**
   ```
   Decision: Re Inspect
   Reason: Confidence 0.46 is below the required threshold of 0.70.
   Plan Update
   Previous: check_battery -> ... -> generate_report
   Updated:  capture_image -> detect_anomaly -> verify_finding -> ...
   ```
9. **Re-inspection succeeds:** confidence 0.93 → `Decision: Verify Finding` → return to base → report generated.
10. **Final report** includes Initial Plan vs Actual Decision Path, finding, confidence history, failure counts, knowledge used, safety decisions, final battery/location, and an inspection summary. `Final Outcome: Mission Complete`.

**Talking points per challenge requirement:** ≥3 tool calls (battery, move, capture, detect, return, report) ✓; decision from a tool result (0.46 < 0.70 → re-inspect) ✓; visible state change (battery 100→80, location BASE→target→BASE, evidence list grows) ✓; failure + fallback (camera timeout retry) ✓; clear end condition (COMPLETE with report) ✓.

## Scenario 2 Deterministic safety abort

```bash
python -m app.main --scenario low-battery
```

Battery starts at 15%. Pre-flight battery check FAILs → "Decision: Abort Mission. Safety: No Movement Command Issued." → failure report still generated → `Final Outcome: Mission Aborted`. This is the slide-5 demo: the guardrail, not the agent, ends the mission, and it happens *before any movement*.

## Scenario 3 Platform failure

```bash
python -m app.main --scenario preflight_failure
```

Navigation controller unavailable → pre-flight fails on a different critical system → same safe-abort path. Shows the pre-flight gate is generic over capability checks, not hard-coded to battery.

## Predicting the system (interview prep)

Given any state, you can derive the next decision without running code:

- At `BASE` + `PRE_FLIGHT` → battery check.
- At `BASE` + `NAVIGATING` → move (if battery ≥ 30 and mission ready; else guardrail rejects).
- Away from base + no evidence → capture (if retries remain; else rejected → abort).
- Un-analyzed evidence → detect.
- Confidence < 0.70, first inspection → knowledge query + re-plan + re-inspect.
- Confidence ≥ 0.70 → verify (no tool) → return → report → COMPLETE.
- Any critical pre-flight failure → abort before movement.

## Live-change suggestions (small, defensible edits)

- Lower `MissionPolicy.EVIDENCE_THRESHOLD` to 0.40 → the weak evidence (0.46) is accepted on the first detection; no re-plan happens. Good for showing the policy is one line.
- Set `MockVision` first-detection confidence to 0.75 → no knowledge consultation; straight to verify.
- Set battery to 90 in `main.py` → report shows different battery accounting.
