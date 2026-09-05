# Limitations & Roadmap

## What this system is not

- **Not flight software.** Everything physical is mocked; the "drone" is a dict with a battery float and a location string. The value is in the decision/safety architecture, which is the part that would survive swapping in real tools.
- **Not general.** `_decide()` encodes one inspection mission. A new mission type means new decision branches by design, for explainability, at the cost of generality.
- **Not multi-mission or multi-agent.** One mission, one controller, one state object. The guardrail layer is stateless and would be reusable, but nothing here schedules or coordinates.
- **Not robust to unmodeled tool failures.** The failure classifier is one `if` (camera → retry, else → abort). Real systems need per-failure-type policies.
- **Not adversarially safe.** Guardrails assume honest inputs; a real deployment needs authenticated commands, command-rate limits, and an external emergency stop outside the agent process entirely.

## Known code-level debts (honesty list)

1. **Legacy dual keys** in tool data (`imageID`/`image_id`, `anomalyConfidence`/`confidence`) tolerated by `update_state()` for backward compatibility; should be collapsed to one canonical schema.
2. **Print-based observability** fine for the demo, but the event log and the printed trace are two renderings of the same facts; structured logging (JSON lines) would remove the duplication.
3. **Re-planning inline in the controller** the new plan is hard-coded in the low-confidence branch rather than derived; a `Planner.revise()` method would make the policy testable in isolation.
4. **`MissionPolicy.MAX_INSPECTION_ATTEMPTS` is declared but enforcement leans on the capture retry cap** the backstop works, but the two limits should be reconciled explicitly.
5. **First RAG query pays model load latency** (~seconds) lazily initialized, and failure-tolerant, but a smaller model or precomputed embeddings would smooth the demo.

## v2 roadmap (in priority order)

1. **Structured event stream** replace/augment `history` strings with typed events; the report and console become views over one stream.
2. **Per-tool failure taxonomy** `Transient / Recoverable / Fatal` classification driving retry policy per tool, instead of the camera special case.
3. **Planner.revise(plan, state)** extracted re-planning policy, unit-testable on its own.
4. **Reserved-return-energy check** before departure, compute whether battery covers outbound + return + margin, replacing the flat 30% floor.
5. **Human-in-the-loop approval** the challenge lists it as bonus; natural insertion point is `RE_INSPECT` (operator approves the extra flight) behind a `REQUIRES_APPROVAL` flag on decisions.
6. **Real tool adapters** `MavSdkDrone` and `OnnxDetector` implementing the same `ToolObservation` contract; the controller and guardrails should need zero changes, which is the architecture's main claim.
7. ~~Tool-call timeout watchdog~~ **done in v1.1**: `call_tool()` wraps every call in a timeout that synthesizes a failure observation; a real stack would add process-level isolation.
8. **Real LLM behind the mock seams** swap the keyword rules in `NLPMissionParser` / `FailureAdvisor` / the report narrative for actual model calls; the contracts and the guardrail boundary stay exactly as they are (see [Design Decisions #9](design-decisions.md)).

## The one-paragraph defense

The system demonstrates every required agentic behavior with the minimum machinery that makes those behaviors *visible and provable*: state-driven decisions (not plan indices), structured observations, bounded retries, mid-mission re-planning backed by advisory knowledge, deterministic guardrails the agent cannot talk its way past, and a report generated from what actually happened rather than what was intended. Every part of it can be explained without a framework, changed live, and traced from printed decision back to a line of code.
