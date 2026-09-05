from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from app.agent.advisor import FailureAdvisor
from app.agent.planner import MissionPlanner
from app.agent.policies import MissionPolicy
from app.mission import MissionParser, NLPMissionParser
from app.models.actions import ActionType, AgentAction, AgentDecision, DecisionType
from app.models.observations import ToolObservation
from app.models.state import MissionState, MissionStatus
from app.safety.guardrails import SafetyValidator
from app.system.preflight import PreFlightSystemCheck
from app.tools.drone import MockDrone
from app.tools.reporting import generate_report
from app.tools.vision import MockVision

SEPARATOR = "=" * 60


class AgentController:
    """Owns Observation-Dependent Mission Decisions And Mission Memory."""

    def __init__(
        self,
        state,
        drone=None,
        vision=None,
        planner=None,
        retriever=None,
        max_steps=30,
        tool_timeout=10.0,
    ):
        self.state = state
        self.drone = drone or MockDrone()
        self.vision = vision or MockVision()
        self.planner = planner or MissionPlanner()
        self._retriever = retriever
        self.max_steps = max_steps
        self.tool_timeout = tool_timeout
        self._detections_done = 0
        self._steps_used = 0
        self._battery_checked = False
        self._knowledge_consulted = False
        self.plan = []
        self.rag_queries = []
        self.report = ""
        self.drone.battery = float(state.battery)

    def run(self):
        self._print_header()
        # Free-Text Missions Go Through The Mock NLP Parser; Structured
        # Missions Use The Static Parser. Either Way The Result Is A
        # Proposal The Guardrails Still Enforce It.
        if self.state.missionText:
            context = NLPMissionParser().parse(self.state.missionText)
            self.state.missionID = context.mission_id
            self.state.target = context.requirements.target
            if context.battery_floor is not None:
                self.state.battery_floor = context.battery_floor
        else:
            context = MissionParser().parse(self.state.missionID, self.state.target)
        self.state.requirements = list(context.requirements.required_capabilities)
        print(
            f"Mission Source: {'Free text (mock NLP parser)' if context.source == 'nlp' else 'Structured (static parser)'}"
        )
        if context.source == "nlp":
            print(f"Parsed Target: {self.state.target}")
            if context.battery_floor is not None:
                print(
                    f"Parsed Constraint: return when battery hits {context.battery_floor:.0f}%"
                )
        self.state.record_event(
            "MISSION_PARSED", f"target={self.state.target}; source={context.source}"
        )
        initial = self.planner.create_plan(self.state.target)
        self.plan = [action.action_type.value for action in initial] + [
            "verify_finding",
            "return_to_base",
            "generate_report",
        ]
        self.state.initial_plan = list(self.plan)
        self.state.plan_history.append("Initial proposal: " + " -> ".join(self.plan))
        self._print_plan("Initial Plan (Proposal)", self.plan)

        self.state.transition(MissionStatus.PRE_FLIGHT)
        self._run_preflight()
        print(
            f"Mission Feasibility: {'Feasible' if self.state.mission_ready else 'Not Feasible'}"
        )
        if not self.state.mission_ready:
            self._abort("Pre-flight failed: " + self.state.readiness_reason)
            self._generate_failure_report()
            return self.state

        print("Mission Readiness: Ready")
        for _ in range(self.max_steps):
            if self.state.status in (MissionStatus.COMPLETE, MissionStatus.ABORTED):
                break
            decision = self._decide()
            if self._apply_decision(decision):
                break
        if self.state.status not in (MissionStatus.COMPLETE, MissionStatus.ABORTED):
            self._abort("Step budget exhausted without reaching a terminal state.")
        print(SEPARATOR)
        print(f"Final Outcome: Mission {self.state.status.value.title()}")
        print(SEPARATOR)
        return self.state

    def _print_header(self):
        print(SEPARATOR)
        print("Mission Initialization")
        print(SEPARATOR)
        print(f"Mission: {self.state.missionID}")
        print(f"Target: {self.state.target}")
        print(
            "Requirements: Safe platform, visual evidence, verified finding, safe return"
        )

    def _print_plan(self, title, plan):
        print("\n" + title + ":")
        for number, step in enumerate(plan, 1):
            print(f"{number}. {step.replace('_', ' ').title()}")

    def _run_preflight(self):
        print("\n" + SEPARATOR)
        print("Pre-Flight System Check")
        print(SEPARATOR)
        results = PreFlightSystemCheck().run(self.state, self.drone, self.vision)
        for result in results:
            print(f"[{'PASS' if result.passed else 'FAIL'}] {result.name}")
        if not self.state.mission_ready:
            print("Mission Readiness: Not Ready")
            print(f"Reason: {self.state.readiness_reason}")
            print("Decision: Abort Mission.")
            print("Safety: No Movement Command Issued.")

    def _decide(self):
        s = self.state
        if s.status == MissionStatus.PRE_FLIGHT:
            return self._tool(
                DecisionType.PROCEED,
                ActionType.CHECK_BATTERY,
                "Confirm battery before departure.",
            )
        if s.status == MissionStatus.NAVIGATING:
            return (
                self._tool(
                    DecisionType.PROCEED,
                    ActionType.MOVE_TO_TARGET,
                    f"Navigate to {s.target}.",
                )
                if s.currentLocation == "BASE"
                else self._tool(
                    DecisionType.PROCEED,
                    ActionType.CAPTURE_IMAGE,
                    "Collect initial visual evidence.",
                )
            )
        if s.status in (MissionStatus.INSPECTING, MissionStatus.RE_INSPECTING):
            if len(s.evidence) > self._detections_done:
                return self._tool(
                    DecisionType.PROCEED,
                    ActionType.DETECT_ANOMALY,
                    "Analyze the newest image.",
                )
            if not s.evidence:
                return self._tool(
                    DecisionType.PROCEED,
                    ActionType.CAPTURE_IMAGE,
                    "Evidence is required before analysis.",
                )
            if MissionPolicy.evidenceIsSufficient(s.anomalyConfidence):
                return AgentDecision(
                    DecisionType.VERIFY_FINDING,
                    f"Confidence {s.anomalyConfidence:.2f} meets the threshold of {MissionPolicy.EVIDENCE_THRESHOLD:.2f}.",
                )
            if s.status == MissionStatus.RE_INSPECTING:
                return self._tool(
                    DecisionType.PROCEED,
                    ActionType.CAPTURE_IMAGE,
                    "Collect additional evidence under the re-inspection plan.",
                )
            knowledge = self._retrieve_for_low_confidence()
            previous = " -> ".join(self.plan)
            self.plan = [
                "capture_image",
                "detect_anomaly",
                "verify_finding",
                "return_to_base",
                "generate_report",
            ]
            update = f"Previous: {previous}\nUpdated: {' -> '.join(self.plan)}\nKnowledge: {knowledge}"
            return AgentDecision(
                DecisionType.RE_INSPECT,
                f"Confidence {s.anomalyConfidence:.2f} is below the required threshold of {MissionPolicy.EVIDENCE_THRESHOLD:.2f}.",
                plan_update=update,
            )
        if s.status == MissionStatus.VERIFYING:
            return self._tool(
                DecisionType.SAFE_RETURN,
                ActionType.RETURN_TO_BASE,
                "Finding is recorded; return safely to base.",
            )
        if s.status == MissionStatus.RETURNING:
            return self._tool(
                DecisionType.PROCEED,
                ActionType.GENERATE_REPORT,
                "At base; generate the inspection report.",
            )
        return AgentDecision(
            DecisionType.COMPLETE, "No further mission work is required."
        )

    @staticmethod
    def _tool(decision, action_type, reason):
        return AgentDecision(decision, reason, AgentAction(action_type, reason))

    def _apply_decision(self, decision):
        s = self.state
        s.decisions.append(f"{decision.decision.value}: {decision.reason}")
        s.record_event(
            "AGENT_DECISION", f"{decision.decision.value}: {decision.reason}"
        )
        print(f"\nDecision: {decision.decision.value.replace('_', ' ').title()}")
        print(f"Reason: {decision.reason}")
        if decision.plan_update:
            print("\nPlan Update")
            print(decision.plan_update)
            s.plan_history.append(decision.plan_update)
            s.record_event("PLAN_UPDATE", decision.reason)
            s.history.append("PLAN UPDATE: " + decision.reason)
        if decision.decision == DecisionType.ABORT:
            return self._abort(decision.reason)
        if decision.decision == DecisionType.RE_INSPECT:
            s.inspection_attempts += 1
            s.transition(MissionStatus.RE_INSPECTING)
            s.record_event("RE_INSPECTION", "Additional evidence requested.")
            return False
        if decision.decision == DecisionType.VERIFY_FINDING:
            s.findings.append(
                f"Possible surface anomaly confirmed (confidence {s.anomalyConfidence:.2f})"
            )
            s.record_event(
                "VERIFICATION", "Finding confirmed after sufficient evidence."
            )
            s.transition(MissionStatus.VERIFYING)
            return False
        return self._execute(decision.next_action)

    def _execute(self, action):
        self._steps_used += 1
        allowed, reason = SafetyValidator.validate(action, self.state)
        self.state.safety_decisions.append(
            f"{action.action_type.value}: {'Approved' if allowed else 'Rejected'} - {reason}"
        )
        print(f"\nAction: {action.action_type.value.replace('_', ' ').title()}")
        print(f"Safety: {reason}")
        if not allowed:
            self.state.record_event(
                "SAFETY_REJECTION", f"{action.action_type.value}: {reason}"
            )
            return self._handle_rejection(action, reason)
        observation = self.call_tool(action)
        print(f"Observation: {observation.message}")
        self.update_state(observation)
        if not observation.success:
            handled = self._handle_failure(action, observation)
        else:
            handled = self._handle_success(action)
        self._trace(action, observation, handled)
        return handled

    def _trace(self, action, observation, handled):
        """One-Line Decision Trace In The Challenge's Suggested Format.

        Printed AFTER State Update + Decision Handling So The Shown
        State Already Reflects The Decision That Was Made.
        """
        data = observation.data or {}
        result_parts = [f"success={str(observation.success).lower()}"]
        if "battery" in data:
            result_parts.append(f"battery={data['battery']:.0f}")
        if "confidence" in data:
            result_parts.append(f"confidence={data['confidence']:.2f}")
        if "image_id" in data:
            result_parts.append(f"evidence={data['image_id']}")
        if not observation.success:
            result_parts.append(f"error='{observation.message}'")
        decision = (
            "abort"
            if self.state.status.value == "aborted"
            else f"continue ({self.state.status.value})"
        )
        print(
            f"trace: state={self.state.status.value} | "
            f"tool={action.action_type.value} | "
            f"result: {', '.join(result_parts)} | "
            f"decision: {decision} | "
            f"steps_left={self.max_steps - self._steps_used}"
        )

    def call_tool(self, action):
        tools = {
            ActionType.CHECK_BATTERY: self.drone.check_battery,
            ActionType.MOVE_TO_TARGET: lambda: self.drone.moveToTarget(
                self.state.target
            ),
            ActionType.CAPTURE_IMAGE: lambda: self.vision.captureImage(
                self.state.currentLocation
            ),
            ActionType.DETECT_ANOMALY: lambda: self.vision.detectAnomaly(
                self.state.evidence[-1]
            ),
            ActionType.RETURN_TO_BASE: self.drone.returnToBase,
            ActionType.GENERATE_REPORT: lambda: ToolObservation(
                True, "generate_report", "Inspection report generated.", {}
            ),
        }
        # Watchdog: Run The Tool On A Worker Thread So A Hang Becomes A
        # Failure ToolObservation Instead Of Freezing The Mission.
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            return executor.submit(tools[action.action_type]).result(
                timeout=self.tool_timeout
            )
        except FutureTimeoutError:
            message = f"Tool Timed Out After {self.tool_timeout:g}s"
            return ToolObservation(False, action.action_type.value, message, {})
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def update_state(self, observation):
        data = observation.data or {}
        if "battery" in data:
            self.state.battery = float(data["battery"])
        if "location" in data:
            self.state.currentLocation = data["location"]
        image_id = data.get("image_id")
        if image_id and observation.toolName == "capture_image":
            self.state.evidence.append(image_id)
        confidence = data.get("confidence")
        if confidence is not None and observation.toolName == "detect_anomaly":
            self.state.anomalyConfidence = float(confidence)
            self.state.confidence_history.append(float(confidence))
        self.state.record_event(observation.toolName.upper(), observation.message)
        self.state.history.append(f"{observation.toolName}: {observation.message}")

    def _handle_success(self, action):
        s = self.state
        if action.action_type == ActionType.CHECK_BATTERY:
            self._battery_checked = True
            s.transition(MissionStatus.NAVIGATING)
        elif action.action_type == ActionType.MOVE_TO_TARGET:
            s.transition(MissionStatus.INSPECTING)
        elif action.action_type == ActionType.CAPTURE_IMAGE:
            s.transition(
                MissionStatus.INSPECTING
                if s.status != MissionStatus.RE_INSPECTING
                else MissionStatus.RE_INSPECTING
            )
        elif action.action_type == ActionType.DETECT_ANOMALY:
            self._detections_done += 1
        elif action.action_type == ActionType.RETURN_TO_BASE:
            s.transition(MissionStatus.RETURNING)
        elif action.action_type == ActionType.GENERATE_REPORT:
            s.transition(MissionStatus.REPORTING)
            s.transition(MissionStatus.COMPLETE)
            self.report = generate_report(s)
            print("\n" + self.report)
            return True
        return False

    def _handle_failure(self, action, observation):
        s = self.state
        s.failures.append(f"{observation.toolName}: {observation.message}")
        s.record_event("FAILURE", s.failures[-1])
        # The Advisor Only Selects Among Pre-Approved Policies (Retry Vs
        # Abort); The Retry Budget Still Caps It.
        classification = FailureAdvisor.classify(observation.message)
        s.record_event(
            "ADVISOR", f"{observation.toolName} failure classified {classification}."
        )
        print(f"Advisor: failure classified as {classification}")
        if (
            action.action_type == ActionType.CAPTURE_IMAGE
            and classification == "transient"
        ):
            s.retries += 1
            s.camera_retries += 1
            if s.camera_retries <= s.maxRetries:
                s.record_event(
                    "RETRY", f"Camera capture retry {s.camera_retries}/{s.maxRetries}."
                )
                s.decisions.append(
                    "retry_capture: Advisor says failure is transient and retry budget remains."
                )
                s.history.append(
                    "DECISION: retry_capture (Advisor says failure is transient and retry budget remains.)"
                )
                print("Decision: Retry Capture")
                return False
            return self._abort("Camera retry limit reached.")
        return self._abort(f"Tool failure: {observation.message}")

    def _handle_rejection(self, action, reason):
        if (
            action.action_type == ActionType.RETURN_TO_BASE
            and self.state.currentLocation != "BASE"
        ):
            return self._abort("Unable to return safely: " + reason)
        return self._abort("Action rejected: " + reason)

    def _retrieve_for_low_confidence(self):
        query = f"Anomaly detected with confidence {self.state.anomalyConfidence:.2f}. What should the inspection agent do next?"
        results = self._retrieve(query, 3)
        if not self._knowledge_consulted:
            results += self._retrieve(
                "What confidence is required before confirming an anomaly?", 1
            )
            results += self._retrieve(
                "Has this inspection area had previous anomalies?", 1
            )
            self._knowledge_consulted = True
        return "; ".join(f"{item['source']}: {item['text']}" for item in results)

    def _retrieve(self, query, top_k):
        self.rag_queries.append(query)
        if self._retriever is None:
            import io
            from contextlib import redirect_stderr, redirect_stdout

            from app.knowledge.retriever import KnowledgeRetriever

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self._retriever = KnowledgeRetriever()
        try:
            results = self._retriever.retrieve(query, top_k=top_k)
        except Exception as exc:
            print(f"Knowledge retrieval unavailable: {exc}")
            return []
        for item in results:
            if item["source"] not in self.state.knowledge_sources:
                self.state.knowledge_sources.append(item["source"])
        self.state.record_event("RAG_QUERY", query)
        self.state.history.append(
            f"RAG: {query} -> {[item['source'] for item in results]}"
        )
        print("\nRelevant Knowledge:")
        for item in results:
            print(f"- {item['source']}: {item['text']}")
        return results

    def _abort(self, reason):
        self.state.record_event("ABORT", reason)
        self.state.transition(MissionStatus.ABORTED)
        print(f"Decision: Abort Mission. Reason: {reason}")
        return True

    def _generate_failure_report(self):
        self.report = generate_report(self.state)
        print("\n" + self.report)
