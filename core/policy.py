# policy.py
class OrionPolicy:
    """
    ORION Policy – Phase 3.5

    Uses reflection output to issue warnings.
    Does NOT block actions. Advisory only.
    """

    def evaluate(self, intent: str, decision: dict, reflection: dict) -> list[str]:
        warnings = []

        risks = reflection.get("risks", [])

        # Warn before editing repeatedly failing targets
        if intent == "FILE_EDIT":
            path = decision.get("path", "")
            for r in risks:
                if path and path in r:
                    warnings.append(
                        f"Policy warning: Repeated failures detected on '{path}'. "
                        f"Consider reviewing manually before editing."
                    )

        return warnings
