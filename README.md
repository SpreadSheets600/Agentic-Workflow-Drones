# WeevilDrone — Evidence-Driven Drone Inspection Agent

<p align="center">
  <img src="docs/architecture.png" alt="WeevilDrone full system architecture — mission intake, pre-flight checks, agent decision loop, safety validator, tool layer, and terminal outcomes" width="100%">
</p>

An autonomous drone inspection agent for Solar Panel Area A that **collects evidence before it concludes**. It receives a mission, proposes a plan, calls tools, observes the results, updates its state, and **changes its plan when reality disagrees** — retrying a failed camera capture, consulting a semantic knowledge base when detection confidence is weak, re-planning, verifying the finding, returning safely, and writing an explainable report.

Every action passes through a deterministic safety validator before it can reach the (mocked) drone. The governing principle:

> **The agent proposes what to do; deterministic software decides whether it is allowed.**

No LLM, no agent framework, no flight hardware — just transparent control logic and deterministic tests.

## Quick Start

```bash
uv sync

# full demo: camera failure → bounded retry → weak evidence → RAG → re-plan → 0.93 → report
uv run python -m app.main

# deterministic safety aborts
uv run python -m app.main --scenario low-battery        # battery 15% < 30% floor → abort before any movement
uv run python -m app.main --scenario preflight_failure  # navigation controller unavailable → abort

# free-text mission via the mock-NLP seam
uv run python -m app.main --mission "Inspect the north solar field; return when battery hits 45%"

# tests
uv run pytest
```

The default demo is fully deterministic: the first capture times out, the retry succeeds, detection confidence is 0.46 (< 0.70 threshold → re-inspection), the second pass yields 0.93, and the drone returns to base and reports.

## How It Works

1. **Mission intake** — a structured scenario or free text (mock-NLP parser extracts target, extra capabilities, and constraints such as a battery floor; the parser only *proposes*).
2. **Pre-flight** — five critical checks (GPS, battery, camera, navigation controller, geofence) gate the mission before any movement.
3. **Decision loop** — `AgentController` decides the next action purely from current `MissionState` and policy thresholds, never from a fixed script.
4. **Safety wall** — `SafetyValidator` checks eight deterministic rules before every tool call; rejections are recorded and abort the mission.
5. **Watchdog tool calls** — a hung tool is turned into a normal failure `ToolObservation`, so guardrails still run on it.
6. **Failure handling** — a mock `FailureAdvisor` classifies failures transient/permanent and selects between pre-approved retry and abort policies; the retry budget still caps everything.
7. **Evidence gating** — confidence < 0.70 triggers advisory RAG retrieval and a re-plan; the plan list is rewritten, printed, and stored in `plan_history`.
8. **Report** — generated entirely from mission memory: plan vs. actual decision path, evidence, confidence history, failures, recovery, safety decisions.

## Documentation

Full documentation lives in **[`docs/`](docs/README.md)**:

| Document | Covers |
|---|---|
| [Architecture](docs/architecture.md) | Components, data flow, diagram, and why this shape was chosen |
| [Full System Diagram](docs/full-diagram.md) | One exhaustive mermaid diagram: every rule, threshold, planted behavior, and data contract |
| [Agentic Workflow](docs/agentic-workflow.md) | Mission → Plan → Observe → Decide → Act → Verify → Re-plan → Complete, mapped to code |
| [Design Decisions](docs/design-decisions.md) | Every important choice: what, why, alternatives considered, trade-offs |
| [Failure Handling & Safety](docs/failure-handling-and-safety.md) | Failure catalog, guardrails, deterministic limits, stop conditions |
| [Ownership: The Decision Core](docs/ownership.md) | Deep dive on the controller: internals, failure modes, debugging, scaling |
| [Demo Guide](docs/demo-guide.md) | How to run every scenario, expected console traces, talking points |
| [Module Reference](docs/module-reference.md) | File-by-file reference: classes, key functions, inputs and outputs |
| [Limitations & Roadmap](docs/limitations-and-roadmap.md) | What this system is *not*, and what a v2 would add |

## Project Structure

```
app/
├── main.py                 # CLI entry point and scenario selection
├── mission.py              # MissionParser + NLPMissionParser (mock-LLM seam #1)
├── system/preflight.py     # five critical pre-flight capability checks
├── agent/
│   ├── controller.py       # the decision loop — the owned core
│   ├── planner.py          # initial plan proposal
│   ├── policies.py         # centralized thresholds (battery floor, 0.70, retries)
│   └── advisor.py          # FailureAdvisor, transient/permanent triage (mock-LLM seam #2)
├── models/                 # decisions, observations (ToolObservation), MissionState
├── safety/guardrails.py    # deterministic execution boundary — the wall
├── tools/                  # MockDrone, MockVision, reporting (mock-LLM seam #3: narrative)
├── knowledge/              # semantic retriever + inspection/anomaly/history docs
└── tests/                  # decisions and state transitions tested directly
```

## Design Principles

- **Mock tools, real contracts** — `MockDrone`/`MockVision` return the same structured `ToolObservation` a real stack would; swapping in MAVSDK or a vision model changes nothing upstream.
- **State is memory, not vibes** — `MissionState` (status, battery, location, evidence, confidence history, failures, decisions, plan history, full event log) is the single source of truth; the report is derived entirely from it.
- **Knowledge ≠ state** — the RAG retriever answers *what policy recommends*; it is consulted only on low confidence, is advisory, and never executes actions.
- **Two protection layers** — pre-flight asks "can this platform start this mission?"; the safety validator asks "is this specific action allowed right now?" Neither can be reasoned with by the agent.
- **Bounded by construction** — 30-step budget, retry cap of 3, watchdog on every tool call. The loop provably terminates.
- **Deterministic and explainable** — every decision carries a reason and is auditable via the ordered event history; the demo is reproducible run to run.

## Future Work

Real telemetry and flight adapters, a real detection model, persistent mission memory, human-in-the-loop approval, richer planning, and LLM-assisted suggestions behind the existing mock-AI seams — all intentionally left out so the core workflow stays deterministic, explainable, and testable.
