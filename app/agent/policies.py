class MissionPolicy:
    # Minimum Battery To Continue A Mission
    MIN_BATTERY = 30

    # Minimum Confidence (0-1 Scale) Required To Confirm An Anomaly
    EVIDENCE_THRESHOLD = 0.70

    # Maximum Number Of Retries Allowed After Failure
    MAX_RETRIES = 3
    MAX_INSPECTION_ATTEMPTS = 2

    @classmethod
    def batteryIsSafe(cls, battery, floor=None):
        # Floor Lets A Parsed Mission Constraint Adjust The Default;
        # The Value Is Still Enforced Here (Guardrail), Not By The Agent.
        return battery >= (cls.MIN_BATTERY if floor is None else floor)

    @classmethod
    def evidenceIsSufficient(cls, confidence):
        return confidence >= cls.EVIDENCE_THRESHOLD

    @classmethod
    def retriesAllowed(cls, retries, limit=None):
        if limit is None:
            limit = cls.MAX_RETRIES
        return retries < limit
