# Design Decisions

Each decision: what, why, what I considered instead, and the trade-off I accepted. (The short version lives in `DECISIONS.md` at the repo root; this is the full reasoning.)

## 1. Rule-based decision core, not an LLM in the loop

**Decision.** `_decide()` is a pure function of `MissionState` + `MissionPolicy` constants. No LLM call decides anything.

**Why.** The challenge evaluates *understanding and logic* (30%) and *explainability*. With rules, every decision has a printed reason traceable to a line of code and a threshold. With an LLM I could not predict, on demand, why the agent chose an action the exact thing the interview tests. I also avoided a failure mode that matters in real robotics: an LLM could propose `MOVE_TO_TARGET` at 10% battery with confident prose. Deterministic code never does.

**Alternatives.** LLM planner + rule executor (rejected: the interesting logic would live in the LLM, not in code I own); a hybrid (LLM proposes, rules veto sensible for production, unnecessary complexity for one mocked mission).

**Trade-off.** The agent is brittle to situations my rules didn't anticipate. Mitigation: the RAG knowledge layer supplies *advisory* context without giving up decision determinism, and `_decide()` is small enough to extend live in an interview.

## 2. Initial plan is a proposal; the controller re-plans

**Decision.** `MissionPlanner` produces the opening plan, but `_decide()` can rewrite it mid-mission (the low-confidence branch literally replaces the plan list and prints the diff).

**Why.** Agentic behavior *is* responding to observations. If the planner were authoritative, the camera failure and the 0.46-confidence detection would have nowhere to change the outcome.

**Alternatives.** Fully reactive (no plan at all rejected: the challenge asks for planning and visible re-planning); plan with contingencies pre-declared (better for real systems, but pre-scripted branches are less demonstrably agentic).

**Trade-off.** Re-planning logic in the controller is less reusable than a first-class planner object. Acceptable at this scale; a v2 would extract a `Planner.revise(plan, state)` interface (see [Roadmap](limitations-and-roadmap.md)).

## 3. Structured observations (`ToolObservation`), not prose

**Decision.** Every tool returns `ToolObservation(success, toolName, message, data)`.

**Why.** Decisions depend on *data* (`data["confidence"]`, `data["battery"]`), while *messages* are for humans. Separating them means the agent never parses strings (a classic fragile pattern), and the report/events pipeline has one uniform shape to consume. It also means the mock tools have exactly the contract a real drone SDK adapter would expose.

**Alternatives.** Raw return values + exceptions (rejected: exceptions conflate "expected failure" with "bug", and raw values force isinstance checks at every call site).

**Trade-off.** The legacy camelCase keys (`imageID`, `anomalyConfidence`) still exist alongside the canonical snake_case ones in tool data the controller tolerates both, which is slightly redundant but backward compatible.

## 4. One controller, one state dataclass, no framework

**Decision.** Plain Python. `AgentController` owns the loop; `MissionState` owns the memory.

**Why.** A few hundred explainable lines beat thousands of framework lines I can't defend. Also practical: the whole system runs on a laptop, and unit tests construct `MissionState` directly no mocking of framework internals.

**Alternatives.** LangChain/LlamaIndex agents (rejected: hides the state machine the one thing I must own); a state-machine library like `transitions` (rejected: my transitions are ~10 lines of if/elif; a library adds dependency weight without adding logic).

**Trade-off.** I hand-rolled things a framework gives for free (the tool registry is a dict literal). Fine the registry is 6 entries.


## 5. Guardrails as a separate, non-negotiable layer

**Decision.** `SafetyValidator` sits *between* decision and tool call, with its own tests, and no code path bypasses it.

**Why.** The agent proposes; the validator disposes. This is the answer to "where would you not rely on the agent": battery floor (30%), retry caps, "no capture at base", "no detection without evidence", pre-flight gating. Because it's a pure function `(action, state) → (bool, reason)`, it is trivially unit-testable and it is tested.

**Alternatives.** Checks inside the agent (rejected: the agent checking itself is not a safety boundary); checks inside the tools (partially done as defense-in-depth `MockDrone.moveToTarget` refuses ≤ 20% battery but tool-side checks can't cover preconditions the tool doesn't know about).

**Trade-off.** The agent has less freedom. Accepted unsafe proposals reaching the drone is the failure mode that actually matters.

## 6. Retry policy: recoverable vs fatal, with a hard budget

**Decision.** Camera failure → retry up to 3 times; any other tool failure → immediate abort; step budget 30 → abort.

**Why.** A camera timeout is plausibly transient; a navigation failure mid-mission is not something retrying fixes safely. Differentiated failure response (not a blanket retry-everything) is the reasoning the challenge asks to see, and the budget makes "retry" finite.

**Trade-off.** Aborting on a transient GPS glitch mid-flight would be premature in a real system. A v2 would classify failures per tool (see [roadmap](limitations-and-roadmap.md)).

## 7. RAG as advisory knowledge, not decision-maker (bonus feature)

**Decision.** When confidence < threshold, the agent queries a local semantic retriever (`all-MiniLM-L6-v2` over three small domain documents) and *prints* the retrieved guidance before re-planning.

**Why.** It demonstrates "useful memory / knowledge" at the bonus tier without surrendering decision authority: the retrieved text appears in the trace and report as justification, but the threshold comparison itself stays deterministic. Retrieval failures are caught and downgraded to a printed notice the mission continues.

**Alternatives.** Letting RAG choose the next action (rejected: non-determinism in the decision path); skipping RAG entirely (fine, but the 0.70 threshold now visibly agrees with the retrieved inspection guidelines, which strengthens the demo story).

**Trade-off.** First retrieval pays a model-load cost (~seconds) and adds two dependencies. It is lazily initialized only when low confidence actually occurs.

## 8. Console trace as the observability layer

**Decision.** Print statements in a fixed vocabulary (`Decision:`, `Action:`, `Safety:`, `Observation:`) plus a full event log inside `MissionState.history` that the final report renders.

**Why.** The challenge explicitly says a console trace is enough. The dual channel matters, though: prints are for the *live demo*, `state.history` is the *source of truth* the report is generated from so the report cannot drift from what actually happened.

## 9. Mock-AI seams: LLM-like components at the edges, never in the core

**Decision.** Three LLM-shaped capabilities are simulated with deterministic keyword rules, each at a boundary of the system: `NLPMissionParser` (free-text mission → target, capabilities, battery constraint), `FailureAdvisor` (failure message → transient/permanent), and a narrative writer in the report (structured facts → human-readable prose). No LLM call happens anywhere.

**Why.** "Where would an LLM actually help?" has a real answer mission understanding, failure triage, report prose but putting one in the decision core would break the explainability the whole design is built on. The seams demonstrate the integration *boundary* instead: every mocked component's output is a **proposal** that deterministic code still validates. The NLP parser can only fill in requirements (pre-flight still gates them, and the parsed battery floor is enforced by the guardrail, not the parser); the advisor only selects between two pre-approved policies and the retry budget still caps it; the narrative only rewords facts already in mission memory.

**Alternatives.** A real LLM call behind a feature flag (rejected for this submission: adds network dependency, cost, and non-determinism to a demo that must be reproducible on a laptop); no mock at all (rejected: "we'd add an LLM somewhere" without a seam is hand-waving the seam is the engineering).

**Trade-off.** The keyword extraction is crude (regex, not semantics) and the advisor is a one-if classifier. Accepted the point is the boundary, and each docstring states exactly what a real implementation would do behind the identical contract.

## 10. Tool watchdog: a hang becomes a failure observation

**Decision.** `call_tool()` runs every tool call under a timeout (`tool_timeout`, default 10s, via a worker thread). On timeout it synthesizes `ToolObservation(success=False, message="Tool Timed Out...")` and the normal failure pipeline (advisor → guardrails → state) proceeds.

**Why.** Previously the one unclosed hole: guardrails run on *observations*, so a tool that never returned would bypass them entirely the mission would freeze rather than fail safely. Converting a hang into the standard failure envelope means every existing safeguard applies unchanged.

**Alternatives.** Heartbeat protocol between agent and tools (over-engineered for in-process mocks); per-tool timeouts configured individually (one global budget is enough at this scale).

**Trade-off.** A timed-out worker thread keeps running in the background (Python threads can't be killed). Harmless for mocked tools; a real deployment would use process-level isolation or an async runtime with cancellation.
