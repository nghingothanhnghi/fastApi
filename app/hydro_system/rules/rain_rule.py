from .base_rule import ActuatorRule

class RainRule(ActuatorRule):
    """
    When rain is detected, close the sliding door (or skip valve/pump activation)
    to prevent overwatering / water ingress.
    """
    actuator_type = "sliding_door"

    def should_activate(self, sensor_data: dict, thresholds: dict, actuator=None) -> bool:
        # "activate" here means "close" — invert if your door's ON state = open
        return sensor_data.get("rain_detected", False)