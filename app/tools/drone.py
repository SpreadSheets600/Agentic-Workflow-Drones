from app.models.observations import ToolObservation


# Simulates A Drone
class MockDrone:
    def __init__(self, gps_available=True, navigation_available=True, geofence_available=True):
        self.battery = 100.0
        self.location = "BASE"
        self.gps_available = gps_available
        self.navigation_available = navigation_available
        self.geofence_available = geofence_available

    def _capability(self, name, available):
        return ToolObservation(available, name, f"{name.replace('_', ' ').title()} {'Available' if available else 'Unavailable'}.", {"available": available})

    def check_gps(self):
        return self._capability("check_gps", self.gps_available)

    def check_battery(self):
        return ToolObservation(self.battery >= 30, "check_battery", f"Battery Level Is {self.battery:.0f}%.", {"battery": self.battery})

    def check_navigation_controller(self):
        return self._capability("check_navigation_controller", self.navigation_available)

    def check_geofence(self):
        return self._capability("check_geofence", self.geofence_available)

    def moveToTarget(self, target: str):
        if not self.navigation_available or not self.gps_available:
            return ToolObservation(False, "move_to_target", "Navigation Capability Unavailable.", {"location": self.location})
        if self.battery <= 20:
            return ToolObservation(
                toolName="move_to_target",
                success=False,
                message="Battery Too Low To Move To Target",
                data={
                    "battery": self.battery,
                    "location": self.location,
                    "target": target,
                },
            )

        self.location = target
        self.battery -= 10.0

        return ToolObservation(
            toolName="move_to_target",
            success=True,
            message=f"Moved To Target {target}",
            data={
                "battery": self.battery,
                "location": self.location,
            },
        )

    def returnToBase(self):
        if not self.navigation_available or not self.gps_available:
            return ToolObservation(False, "return_to_base", "Navigation Capability Unavailable.", {"location": self.location})
        self.location = "BASE"
        self.battery -= 10.0

        return ToolObservation(
            toolName="return_to_base",
            success=True,
            message="Returned To Base",
            data={
                "battery": self.battery,
                "location": self.location,
            },
        )
