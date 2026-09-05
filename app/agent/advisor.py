"""Mock failure advisor.

A real deployment would ask an LLM: 'given this observation and the
mission history, is this failure likely transient or permanent?' — and
its answer would only SELECT among pre-approved policies. This mock
classifies with keyword rules so the demo stays deterministic.

Boundary (unchanged): the advisor never grants a new capability and
never overrides a guardrail. The retry budget still caps whatever it
recommends.
"""


class FailureAdvisor:
    TRANSIENT_KEYWORDS = ("timeout", "temporar", "busy", "reconnect")

    @classmethod
    def classify(cls, message: str) -> str:
        """Return 'transient' or 'permanent' for a failure message."""
        msg = (message or "").lower()
        if any(k in msg for k in cls.TRANSIENT_KEYWORDS):
            return "transient"
        return "permanent"
