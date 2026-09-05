# Module Reference

## `app/main.py` — entry point
Parses `--scenario` (`mission` default, `low-battery`, `preflight_failure`) and an optional `--mission "free text"` (routed to `NLPMissionParser`), builds `MissionState` (low-battery seeds `battery=15.0`), constructs `MockDrone` (preflight_failure seeds `navigation_available=False`), runs `AgentController(state, drone)`.

## `app/mission.py` — mission parsing
- `MissionParser.parse(mission_id, target)` → `MissionContext` with a fixed capabilities list (`gps, battery, camera, navigation, geofence`). Used for structured missions.
- `NLPMissionParser.parse(mission_text)` — **mock LLM seam**: keyword-rule extraction of target (noun phrase after "inspect/check/survey"), required capabilities, and an operator battery constraint (regex like *"return when battery hits 45%"* → `context.battery_floor`). Docstring states exactly what a real LLM would do behind the identical contract. The parsed result is a proposal: pre-flight still gates the capabilities, and the guardrail (not the parser) enforces any battery floor.
- `MissionContext` carries `mission_id`, `requirements`, optional `battery_floor`, `source` (`"static"` / `"nlp"`), and `raw_text`.

## `app/models/` — the data contracts

| Class | Purpose |
|---|---|
| `state.MissionStatus` | Enum: `PLANNING → PRE_FLIGHT → NAVIGATING → INSPECTING ⇄ RE_INSPECTING → VERIFYING → RETURNING → REPORTING → COMPLETE / ABORTED` |
| `state.MissionState` | All mission memory. Key methods: `transition(status)` (records to history), `record_event(type, details)` |
| `actions.ActionType` | Executable tool capabilities — the *only* things `SafetyValidator` accepts |
| `actions.DecisionType` | Agent-level decisions (`PROCEED, RETRY_CAPTURE, RE_INSPECT, VERIFY_FINDING, SAFE_RETURN, ABORT, COMPLETE`) — intent, never sent to tools directly |
| `actions.AgentAction` | `(action_type, reason)` — one executable step |
| `actions.AgentDecision` | `(decision, reason, next_action, plan_update)` — the why, plus optional what and plan diff |
| `observations.ToolObservation` | `(success, toolName, message, data)` — uniform tool envelope; `data` is machine-readable, `message` is human-readable |

## `app/agent/controller.py` — AgentController (core, see [Ownership](ownership.md))
- `run()` — parse mission (free text → `NLPMissionParser`, else static parser; a parsed battery constraint sets `state.battery_floor`) → initial plan → pre-flight → decision loop (max 30 steps) → final outcome banner. Returns final `MissionState`.
- `_decide()` — state → `AgentDecision` (pure, no side effects).
- `_apply_decision()` — validate → call tool → update state → dispatch success/failure.
- `call_tool()` — dict registry mapping `ActionType` → tool callables, each run under a watchdog: a call exceeding `tool_timeout` (default 10s) becomes a failure `ToolObservation` and flows through the normal failure pipeline.
- `update_state(observation)` — folds tool data into state (battery, location, evidence ID, confidence + history) and logs the event.
- `_handle_failure()` — consults `FailureAdvisor` (mock) to classify the failure, then retries camera failures classified transient (up to budget) or aborts; records failures/decisions.
- `_retrieve_for_low_confidence()` / `_retrieve()` — RAG consultation with lazy initialization and failure tolerance.

## `app/agent/planner.py` — MissionPlanner
`create_plan(mission)` → 4 `AgentAction`s (battery, navigate, capture, detect). A proposal generator only; it never executes anything and is not consulted during the loop.

## `app/agent/advisor.py` — FailureAdvisor (mock LLM seam)
`classify(message)` → `"transient"` or `"permanent"` via keyword rules (timeout/temporary/busy → transient). Docstring states what a real LLM advisor would do; its answer only selects between the pre-approved retry and abort policies, and the retry budget still caps it.

## `app/agent/policies.py` — MissionPolicy
The numbers, in one place: `MIN_BATTERY=30`, `EVIDENCE_THRESHOLD=0.70` (aligned with retrieved inspection guidelines), `MAX_RETRIES=3`, `MAX_INSPECTION_ATTEMPTS=2`, plus predicate helpers (`batteryIsSafe` accepts an optional `floor` so a parsed mission constraint can override the default — still enforced by the guardrail, `evidenceIsSufficient`, `retriesAllowed`). Changing behavior = changing one constant.

## `app/safety/guardrails.py` — SafetyValidator
`validate(action, state, preflight=False)` → `(allowed: bool, reason: str)`. Rules: no move below battery floor; no departure unless mission-ready and at `BASE`; no capture at `BASE` or with exhausted retry budget; no detection without evidence; no report without evidence (unless aborted). Raises `TypeError` if handed a non-executable decision. Stateless, side-effect-free, unit-tested.

## `app/system/preflight.py` — PreFlightSystemCheck
Five critical checks (GPS, battery, camera, navigation controller, geofence) via tool calls; each result recorded in `state.preflight_results`; `mission_ready = all critical checks passed`; `readiness_reason` explains the first failure.

## `app/tools/` — mocked environment
- `drone.MockDrone` — `check_gps/battery/navigation_controller/geofence`, `moveToTarget` (fails ≤ 20% battery or without nav/gps; costs 10% battery; updates location), `returnToBase` (costs 10%, location → BASE).
- `vision.MockVision` — `check_camera`, `captureImage` (attempt 1 fails with timeout, later attempts return `IMG-00N`), `detectAnomaly` (attempt 1 → 0.46 weak, later → 0.93 strong). The planted sequence is documented in the class docstring so demo expectations are explicit.
- `reporting.generate_report(state)` — pure function of mission memory: status, readiness, initial plan vs actual decision path, finding, **mock-LLM anomaly narrative** (templated prose from the structured facts — it can reword but never change the finding/confidence/outcome), confidence, evidence, event narrative, failure counts, knowledge sources, final battery/location, safety decisions, outcome, summary. Rendered at mission end (both for COMPLETE and ABORTED).

## `app/knowledge/` — RAG layer (bonus)
- `retriever.KnowledgeRetriever` — loads `documents/*.txt` (anomaly, inspection, history), chunks paragraphs and list items, embeds with `all-MiniLM-L6-v2`, retrieves by cosine similarity → `[{source, text, score}]`. Path resolution is tolerant of the caller's working directory.
- Consumed only by the controller's low-confidence branch; results are advisory (printed + credited in the report), and retrieval errors never stop the mission.

## `app/tests/`
- `test_agent.py` — controller decisions across scenarios (retry, re-inspect, abort paths).
- `test_safety.py` — each guardrail rule in isolation.
- `test_preflight.py` — readiness gating.
- `test_reporting.py` — report content derived from state.
- `test_retriever.py` — chunking and retrieval behavior.
- `test_nlp.py` — mock-AI seams: NLP mission parsing (target/capabilities/constraints), advisor classification, tool watchdog hang → failure observation, and the mock-LLM report narrative.

## Repo root
- `DECISIONS.md` — three-paragraph summary of the key design decisions (full versions in [Design Decisions](design-decisions.md)).
- `docs/` — this documentation set.
