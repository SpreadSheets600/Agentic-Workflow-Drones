from app.models.actions import ActionType, AgentAction


class MissionPlanner:
    def create_plan(self, mission: str):
        return [
            AgentAction(
                action_type=ActionType.CHECK_BATTERY,
                reason="Verify The Drone Has Enough Battery Before Starting.",
            ),
            AgentAction(
                action_type=ActionType.MOVE_TO_TARGET,
                reason=f"Navigate To The Inspection Target : {mission}.",
            ),
            AgentAction(
                action_type=ActionType.CAPTURE_IMAGE,
                reason="Capture Initial Visual Evidence Of The Target.",
            ),
            AgentAction(
                action_type=ActionType.DETECT_ANOMALY,
                reason="Analyze The Captured Evidence For Possible Anomalies.",
            ),
        ]
