"""
ORION MITIGATION ENGINE
======================
Authority-gated execution layer.
NO detection logic.
NO autonomous execution.
"""

import os
import signal
import subprocess
from datetime import datetime, timezone

class MitigationPlan:
    def __init__(self, incident_id, actions):
        self.incident_id = incident_id
        self.actions = actions
        self.created_at = datetime.now(timezone.utc)

class MitigationPlanner:
    def plan(self, incident_state, incident_reason, memory):
        actions = []

        # Ransomware containment
        if "ransomware" in incident_reason.lower():
            actions.extend([
                {
                    "type": "freeze_directory",
                    "target": "/home",
                    "reason": "Stop file encryption spread",
                    "reversible": True
                },
                {
                    "type": "propose_disable_outbound_network",
                    "reason": "Prevent key exfiltration / C2",
                    "reversible": True
                }
            ])

        # Writable-path execution
        if "writable path" in incident_reason.lower():
            suspicious = {
                e.payload.get("pid")
                for e in memory.events
                if e.category == "process"
                and isinstance(e.payload.get("exe"), str)
                and e.payload["exe"].startswith("/tmp")
            }
            for pid in suspicious:
                actions.append({
                    "type": "suspend_pid",
                    "target": pid,
                    "reason": "Suspend suspicious process",
                    "reversible": True
                })

        # Privilege escalation
        if "privilege" in incident_reason.lower():
            actions.append({
                "type": "alert_only",
                "reason": "Privilege escalation requires manual review",
                "reversible": True
            })

        return MitigationPlan(
            incident_id=memory.incident_started_at.isoformat(),
            actions=actions
        )


# --------------------------------------------
# MITIGATION EXECUTION ENGINE
# --------------------------------------------
class MitigationExecutionEngine:
    """
    Provides reversible containment primitives.
    All methods must be explicitly called by authority.
    """
    def execute(self, action):
        t = action["type"]

        if t == "freeze_directory":
            return self.freeze_directory(action["target"])

        if t == "propose_disable_outbound_network":
            return self.propose_disable_outbound_network()

        return f"[MITIGATION] Unknown action: {t}"
    # ────────────── PROCESS CONTROL ──────────────

    def suspend_pid(self, pid: int):
        try:
            os.kill(pid, signal.SIGSTOP)
            return f"[MITIGATION] PID {pid} suspended"
        except Exception as e:
            return f"[MITIGATION][ERROR] suspend_pid({pid}): {e}"

    def resume_pid(self, pid: int):
        try:
            os.kill(pid, signal.SIGCONT)
            return f"[MITIGATION] PID {pid} resumed"
        except Exception as e:
            return f"[MITIGATION][ERROR] resume_pid({pid}): {e}"

    def kill_pid(self, pid: int):
        try:
            os.kill(pid, signal.SIGKILL)
            return f"[MITIGATION] PID {pid} killed"
        except Exception as e:
            return f"[MITIGATION][ERROR] kill_pid({pid}): {e}"

    # ────────────── FILESYSTEM CONTAINMENT ──────────────

    def freeze_directory(self, path: str):
        try:
            if not os.path.isdir(path):
                return f"[MITIGATION][ERROR] Not a directory: {path}"

            subprocess.run(
                ["chmod", "-R", "a-w", path],
                check=True
            )
            return f"[MITIGATION] Directory frozen (write-disabled): {path}"
        except Exception as e:
            return f"[MITIGATION][ERROR] freeze_directory({path}): {e}"

    def unfreeze_directory(self, path: str):
        try:
            if not os.path.isdir(path):
                return f"[MITIGATION][ERROR] Not a directory: {path}"

            subprocess.run(
                ["chmod", "-R", "u+w", path],
                check=True
            )
            return f"[MITIGATION] Directory unfrozen (write-enabled): {path}"
        except Exception as e:
            return f"[MITIGATION][ERROR] unfreeze_directory({path}): {e}"

    # ────────────── NETWORK CONTAINMENT (PROPOSE-ONLY) ──────────────

    def propose_disable_outbound_network(self):
        return (
            "[MITIGATION][PROPOSE] Disable outbound network:\n"
            "sudo iptables -P OUTPUT DROP"
        )

    def propose_enable_outbound_network(self):
        return (
            "[MITIGATION][PROPOSE] Re-enable outbound network:\n"
            "sudo iptables -P OUTPUT ACCEPT"
        )
