# Failure Handling & Safety

## The expected response pattern

For every failure the system follows: **detect → interpret → choose fallback → update state → continue or stop safely.** All four demo scenarios exercise this pattern differently.

## Failure catalog

### 1. Camera timeout on first capture (in `mission` scenario)
- **Detect:** `ToolObservation(success=False, message="Camera Timeout While Capturing Image")`.
- **Interpret:** the mock `FailureAdvisor` classifies the message as transient; its answer only selects between the pre-approved retry and abort policies (a real LLM advisor would slot in behind the same contract).
- **Fallback:** increment `camera_retries`, record `RETRY` event + decision reason, re-attempt next loop.
- **Bound:** at 3 retries the guardrail rejects `CAPTURE_IMAGE` outright and the mission aborts with "Camera retry limit reached." Retry is a *budget*, not a hope.
- **Second attempt succeeds** → evidence `IMG-002` recorded, mission continues.

### 2. Low detection confidence (0.46 < 0.70) — the "unexpected result"
- **Detect:** `detect_anomaly` data shows `confidence: 0.46`.
- **Interpret:** evidence insufficient to confirm; aborting would throw away a plausible finding.
- **Fallback:** consult knowledge base (retrieval says: "if anomaly confidence is below 0.70, collect additional evidence"), rewrite plan, `RE_INSPECT`. Second detection: 0.93 → verified.
- **Bound:** `MAX_INSPECTION_ATTEMPTS` and the capture retry cap prevent endless re-inspection; the 30-step budget is the final backstop.

### 3. Low battery at pre-flight (`low-battery` scenario)
- **Detect:** pre-flight battery check fails (15% < 30%).
- **Interpret:** mission not feasible; this is a *pre-condition* failure, not a runtime recovery.
- **Fallback:** `mission_ready = False` → abort **before any movement command**, and still generate a failure report (so the ground team has a record).
- **Defense in depth:** even if the agent ignored this, three more layers would stop it: `SafetyValidator` rejects `MOVE_TO_TARGET` when battery < 30; `MockDrone.moveToTarget` refuses ≤ 20%; pre-flight gates all non-preflight actions.

### 4. Navigation unavailable (`preflight_failure` scenario)
- **Detect:** pre-flight "Navigation Controller" check fails.
- **Fallback:** safe abort with reason; no movement issued.

### 5. Step-budget exhaustion (latent, tested via logic)
If the decision layer ever failed to converge, the loop hits `max_steps = 30` and aborts with "Step budget exhausted without reaching a terminal state." No unbounded loops are possible.

### 6. Hung tool call (closed by the watchdog, unit-tested)
Previously a latent hole: guardrails run on *observations*, so a tool that never returned would bypass them entirely. `call_tool()` now runs every call under `tool_timeout` (default 10s); a hang becomes `ToolObservation(success=False, message="Tool Timed Out...")` and flows through the exact same pipeline (advisor → state → abort/retry) as any other failure. Covered by `test_nlp.py::test_tool_watchdog_converts_hang_to_failure_observation`.

## Where I deliberately do NOT rely on the agent

The challenge asks for at least one such place; here are all of them, in the order a real command passes through:

| Guardrail | Rule | Why deterministic |
|---|---|---|
| Pre-flight gate | All 5 critical checks must pass before `NAVIGATING` | A "probably fine" from a probabilistic planner must never launch a drone with a dead camera. |
| Battery floor | No `MOVE_TO_TARGET` below 30% | A margin for safe return must be preserved unconditionally. |
| Location rule | Departure only from `BASE`; no capture at `BASE` | Prevents physically meaningless commands. |
| Retry cap | Max 3 capture retries | Prevents a panicked agent from burning the battery on a broken camera. |
| Evidence precondition | No detection without evidence; no report without evidence (unless aborted) | Prevents fabricated findings. |
| Step budget | 30 steps → abort | The global loop-termination guarantee. |

Additionally `MockDrone` itself refuses moves ≤ 20% battery — tool-side validation as a last line of defense, mirroring how a real flight controller enforces limits regardless of what the autonomy stack sends.

**Design principle:** the agent decides *what it wants*; the validator decides *what it may*. The validator is a pure function — `(action, state) → (allowed, reason)` — with no access to tools, no state of its own, and unit tests covering each rule (`app/tests/test_safety.py`). Rejections are recorded as `SAFETY_REJECTION` events and appear in the report's Safety Decisions section.

## Clear end conditions (all demonstrated)

- **Complete:** report generated from mission memory, status `COMPLETE`, drone at `BASE`.
- **Safe abort:** reason printed + failure report generated, status `ABORTED`, no partial-finding ambiguity (report marks the mission "stopped safely before completion").
- **Handover:** the generated report itself is the handover artifact — it contains the event narrative, confidence history, failure counts, and knowledge sources used, enough for a human operator to decide next steps.

## What I'd improve for real hardware

- Battery model with consumption per distance rather than flat −10% per move.
- ~~Watchdog/heartbeat around `call_tool`~~ **done** — a hung tool now becomes a failure `ToolObservation` (see failure #6 above); a real deployment would additionally use process-level isolation so the timed-out worker can actually be killed.
- Return-to-home reserved-power check before departure (compute "can I still get home?" rather than a flat floor).

## Where AI would (and would not) go

The LLM-shaped capabilities in this system are **mock seams** (`NLPMissionParser`, `FailureAdvisor`, the report narrative), each kept out of the decision core on purpose: their output is a proposal that deterministic code still validates. See [Design Decisions #9](design-decisions.md) and [Architecture §7](architecture.md).
