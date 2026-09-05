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
    """Stand-In For An LLM-Based Mission Parser.

    A Real Deployment Would Send The Free-Text Mission To An LLM And Ask
    For Structured JSON (Target, Required Capabilities, Constraints,
    Success Criteria). Here The Extraction Is Mocked With Keyword Rules
    So The Demo Stays Deterministic, Offline, And Explainable.

    Boundary (Unchanged): The Parsed Result Is A PROPOSAL That Fills In
    MissionState/Requirements. It Can Only Narrow What The Agent Does —
    The Pre-Flight Gate Still Rejects Missions Whose Capabilities Are
    Not Actually Available, And The Guardrails Still Enforce Every Rule.
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

    def parse(self, mission_text: str, mission_id: str = "MISSION-NLP"):
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

