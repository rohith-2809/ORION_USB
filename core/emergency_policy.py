# emergency_policy.py
class EmergencyPolicy:
    """
    Defines when ORION may act without human approval.
    """
    CONFIDENCE_THRESHOLD = 0.9
    AUTHORITY_TIMEOUT = 45  # seconds
    ALLOWED_ACTIONS = {
        "freeze_directory",
        "suspend_pid",
        "propose_disable_outbound_network"
    }
    @classmethod
    def is_emergency(cls, incident, elapsed):
        return (
            incident.get("state") == "confirmed"
            and incident.get("confidence", 0) >= cls.CONFIDENCE_THRESHOLD
            and elapsed >= cls.AUTHORITY_TIMEOUT
        )

    @classmethod
    def is_action_allowed(cls, action):
        return (
            action.get("reversible") is True
            and action.get("type") in cls.ALLOWED_ACTIONS
        )
