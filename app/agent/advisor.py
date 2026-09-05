class FailureAdvisor:
    """Mock Failure Advisor.

    A Real Deployment Would Ask An LLM: 'Given This Observation And The
    Mission History, Is This Failure Likely Transient Or Permanent?' —
    And Its Answer Would Only SELECT Among Pre-Approved Policies. This
    Mock Classifies With Keyword Rules So The Demo Stays Deterministic.

    Boundary (Unchanged): The Advisor Never Grants A New Capability And
    Never Overrides A Guardrail. The Retry Budget Still Caps Whatever It
    Recommends.
    """

    TRANSIENT_KEYWORDS = ("timeout", "temporar", "busy", "reconnect")

    @classmethod
    def classify(cls, message: str):
        """Return 'Transient' Or 'Permanent' For A Failure Message."""
        msg = (message or "").lower()

        if any(k in msg for k in cls.TRANSIENT_KEYWORDS):
            return "transient"

        return "permanent"
