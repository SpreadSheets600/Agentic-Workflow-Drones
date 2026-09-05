from dataclasses import dataclass
import re


@dataclass
class MissionRequirements:
    target: str
    required_capabilities: list[str]


@dataclass
class MissionContext:
    mission_id: str
    requirements: MissionRequirements
    # Parsed free-text constraints (None = use policy defaults).
    battery_floor: float | None = None
    # How this mission was interpreted: "static" (fixed template)
    # or "nlp" (free-text extraction via the mock LLM seam).
    source: str = "static"
    raw_text: str = ""


class MissionParser:
    def parse(self, mission_id, target):
        requirements = MissionRequirements(
            target=target,
            required_capabilities=["gps", "battery", "camera", "navigation", "geofence"],
        )
        return MissionContext(mission_id=mission_id, requirements=requirements)


class NLPMissionParser:
    """Stand-in for an LLM-based mission parser.

    A real deployment would send the free-text mission to an LLM and ask
    for structured JSON (target, required capabilities, constraints,
    success criteria). Here the extraction is mocked with keyword rules
    so the demo stays deterministic, offline, and explainable.

    Boundary (unchanged): the parsed result is a PROPOSAL that fills in
    MissionState/requirements. It can only narrow what the agent does —
    the pre-flight gate still rejects missions whose capabilities are
    not actually available, and the guardrails still enforce every rule.
    """

    # Keyword -> capability. A real LLM would infer these semantically.
    CAPABILITY_KEYWORDS = {
        "camera": "camera",
        "photo": "camera",
        "image": "camera",
        "gps": "gps",
        "position": "gps",
        "navigate": "navigation",
        "navigation": "navigation",
        "fly": "navigation",
        "flight": "navigation",
        "geofence": "geofence",
        "battery": "battery",
    }

    BASE_CAPABILITIES = ["gps", "battery", "camera", "navigation", "geofence"]

    BATTERY_RE = re.compile(r"batter\w*\s*(?:hits|drops|below|at|under)\s*(\d{1,3})\s*%")

    def parse(self, mission_text: str, mission_id: str = "MISSION-NLP") -> MissionContext:
        text = (mission_text or "").lower()

        # Target: noun phrase after "inspect"/"check"/"survey", else a
        # known target keyword, else the default inspection area.
        target = "Solar Panel Area A"
        for marker in ("inspect ", "check ", "survey ", "scan "):
            if marker in text:
                after = text.split(marker, 1)[1].strip(" ,.;:")
                candidate = " ".join(after.split()[:4]).strip(" ,.;:")
                if candidate:
                    target = candidate.title()
                break

        # Capabilities: base set always required; keywords can only ADD
        # emphasis, never remove a safety-relevant capability.
        capabilities = list(self.BASE_CAPABILITIES)
        for keyword, cap in self.CAPABILITY_KEYWORDS.items():
            if keyword in text and cap not in capabilities:
                capabilities.append(cap)

        # Constraints: an operator-specified battery floor. The LLM only
        # PROPOSES it; the guardrail still validates every move against it.
        battery_floor = None
        match = self.BATTERY_RE.search(text)
        if match:
            value = float(match.group(1))
            if 0 < value <= 100:
                battery_floor = value

        return MissionContext(
            mission_id=mission_id,
            requirements=MissionRequirements(target=target, required_capabilities=capabilities),
            battery_floor=battery_floor,
            source="nlp",
            raw_text=mission_text or "",
        )

