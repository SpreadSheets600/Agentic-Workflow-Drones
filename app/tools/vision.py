from app.models.observations import ToolObservation


class MockVision:
    """Simulated Camera + Anomaly Detector.

    Intended Scenario (Must Be Preserved For The Interview Demo):
    - 1st Capture FAILS (Camera Timeout), Later Captures Succeed.
    - 1st Detection Reports Weak Evidence (Confidence 0.46).
    - 2nd+ Detection Reports Strong Evidence (Confidence 0.93).
    """

    def __init__(self, camera_available=True):
        self.captureAttempts = 0
        self.detectionAttempts = 0
        self.camera_available = camera_available

    def check_camera(self):
        return ToolObservation(
            self.camera_available,
            "check_camera",
            f"Camera {'Available' if self.camera_available else 'Unavailable'}.",
            {"available": self.camera_available},
        )

    def captureImage(self, location: str):
        self.captureAttempts += 1

        if not self.camera_available:
            return ToolObservation(
                False,
                "capture_image",
                "Camera Initialization Failed.",
                {"location": location},
            )

        # Simulate A Camera Failure On The First Attempt
        if self.captureAttempts == 1:
            return ToolObservation(
                toolName="capture_image",
                success=False,
                message="Camera Timeout While Capturing Image",
                data={
                    "location": location,
                    "attempts": self.captureAttempts,
                },
            )

        image_id = f"IMG-{self.captureAttempts:03d}"
        return ToolObservation(
            toolName="capture_image",
            success=True,
            message="Image Captured Successfully",
            data={
                "location": location,
                "attempts": self.captureAttempts,
                "image_id": image_id,
            },
        )

    def detectAnomaly(self, image_id: str):
        self.detectionAttempts += 1

        # First Inspection Produces Weak Evidence
        if self.detectionAttempts == 1:
            confidence = 0.46
            message = "Possible Anomaly Detected (Weak Evidence)"
        # Second And Later Inspections Produce Strong Evidence
        else:
            confidence = 0.93
            message = "Anomaly Confirmed (Strong Evidence)"

        return ToolObservation(
            toolName="detect_anomaly",
            success=True,
            message=message,
            data={
                "image_id": image_id,
                "confidence": confidence,
                "attempts": self.detectionAttempts,
            },
        )
