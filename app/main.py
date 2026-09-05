import argparse
import os

from app.agent.controller import AgentController
from app.models.state import MissionState
from app.tools.drone import MockDrone

# Settings Default Values For Logs
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# Simulation For Low Battery State From The Start
def build_state(scenario: str):
    if scenario == "low-battery":
        return MissionState(
            missionID="MISSION-002",
            target="Solar Panel Area A",
            battery=15.0,
        )
    return MissionState(missionID="MISSION-001", target="Solar Panel Area A")

# Main Function With Inspection Arguments
def main(argv=None):
    parser = argparse.ArgumentParser(description="WeevilDrone Inspection Mission")
    parser.add_argument(
        "--scenario",
        choices=["default", "mission", "low-battery", "preflight_failure"],
        default="mission",
        help="Mission: Full Inspection Demo\n Low-Battery: Safety Abort Demo",
    )
    parser.add_argument(
        "--mission",
        type=str,
        default="",
        help=(
            'Free-text mission, e.g. --mission "Inspect the wind turbines; '
            'return when battery hits 45%%". Parsed by the mock NLP parser.'
        ),
    )
    args = parser.parse_args(argv)

    state = build_state(args.scenario)
    state.missionText = args.mission
    drone = MockDrone(navigation_available=args.scenario != "preflight_failure")
    agent = AgentController(state, drone=drone)
    agent.run()


if __name__ == "__main__":
    main()
