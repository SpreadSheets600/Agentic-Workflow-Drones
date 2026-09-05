# Ownership: The Decision Core

The component I fully own and can defend line by line is **the agent decision logic and state management**: `AgentController._decide()` / `_apply_decision()` plus the `MissionState` state machine (`app/agent/controller.py`, `app/models/state.py`).

## How it works internally

`_decide()` is a pure function of state. It branches on `state.status` and, within each status, on state facts:

- `PRE_FLIGHT` → confirm battery (one last check before departure).
- `NAVIGATING` → if still at `BASE`, move; otherwise start capturing. (The location check, not the plan index, chooses the action.)
- `INSPECTING / RE_INSPECTING` → the richest branch, four ordered checks:
  1. New un-analyzed evidence? → `DETECT_ANOMALY`.
  2. No evidence at all? → `CAPTURE_IMAGE`.
  3. Confidence ≥ 0.70? → `VERIFY_FINDING` (no tool a memory operation).
  4. Otherwise → consult knowledge, rewrite plan, `RE_INSPECT`.
- `VERIFYING` → `RETURN_TO_BASE`; `RETURNING` → `GENERATE_REPORT`.

The key invariant: **the plan list is never consulted to choose the next action.** The plan exists for the human (it is printed and diffed on re-plan); the state is what actually drives behavior. That is what separates this from a script a script follows an index into a list, which is exactly how the camera failure would have derailed it.

Decisions and actions are deliberately different types (`DecisionType` vs `ActionType`). A *decision* is a why (`RE_INSPECT`); it expands into zero or more executable *actions* (`CAPTURE_IMAGE` → `DETECT_ANOMALY`). This keeps agent-level intent out of the guardrails the validator refuses anything that isn't a concrete executable `ActionType` (it raises `TypeError` on a decision), so there is no path from "I should re-inspect" to the drone without first becoming a validated, physical command.

## Inputs and outputs

- **Inputs:** `MissionState` (mutable, the single source of truth), `MissionPolicy` constants (thresholds), and through `_apply_decision()`, `ToolObservation`s.
- **Outputs:** an `AgentDecision` (decision type + human-readable reason + optional next action + optional plan diff), state transitions, and eventually the final `MissionState` (the report is generated from it).
- The controller returns the final `state` from `run()`, which is what tests assert on.

## What can fail, and how it's detected

| Failure mode | Detection | Response |
|---|---|---|
| Tool returns failure observation | `observation.success == False` | Retry (camera) or abort (everything else), with the reason recorded |
| Guardrail rejects the action | `validate()` returns `(False, reason)` | Abort, or targeted handling (e.g. a rejected `RETURN_TO_BASE` away from base is treated as "cannot return safely" → abort with that reason) |
| Decision loop never converges | Step counter vs `max_steps` | Abort with "Step budget exhausted" |
| Knowledge retrieval unavailable | `try/except` around `retrieve()` | Print notice, continue mission without knowledge |
| Tool returns malformed data | `update_state()` uses `.get()` with fallbacks for legacy/new keys | Missing fields are simply not recorded; no crash |
| Invalid decision reaching the validator | `TypeError` in `SafetyValidator` | Programming bug, fails fast by design |

## Why designed this way the two-line version

Because in a real drone system the two things that must never be uncertain are **why** the agent did something (auditability) and **whether** it was allowed to (safety). Everything else mocked tools, console output, simple thresholds is in service of making those two things visible.

## Alternatives considered

- **Switch dispatch table** (`status → handler function`): cleaner for 10+ states; overkill for 8 where the branches share state reads. The if/elif is ~60 readable lines.
- **Plan-index-driven execution** (`plan[i]` with pointers): simpler code, but it's a script it cannot express "the situation changed" without hacky index rewinding, which is precisely the agentic behavior being demonstrated.
- **Event-driven / behavior-tree design**: better composability for many behaviors; more indirection than one mission needs.

## How I debug it

1. **Reproduce deterministically:** every scenario is a CLI flag (`--scenario mission|low-battery|preflight_failure`); the same input produces the same trace, so a failure is always replayable.
2. **Read the audit trail:** `MissionState.history` records every status change, event, failure, and decision with reasons. The final report prints this narrative often the bug is visible in the printed trace without a debugger.
3. **Isolate:** `MissionState` is a plain dataclass, and `_decide()` is state-in/decision-out I can construct a suspicious state by hand in a REPL or test and inspect the decision it produces. The unit tests (`app/tests/`) do exactly this.
4. **Shrink the loop:** `max_steps` is injectable; setting it to 1 shows exactly one iteration's decision path.

## How I would improve / scale it

- Extract `Planner.revise(plan, state) → plan` so re-planning policy is testable independently of the controller.
- Give `_decide()` a formal precondition table (state facts → allowed decisions) that the guardrails can cross-check, shrinking the trusted code further.
- Replace the string event log with structured events (JSON lines) for tooling; keep the printed trace for humans.
- Multi-mission: `MissionState` is already per-mission; a scheduler would hold N states and share the guardrail layer, which is stateless by design.
