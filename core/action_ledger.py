# action_ledger.py

import json
import os
from datetime import datetime


class ActionLedger:
    """
    ORION Action Ledger – Phase 3.3.1 (PATH-SAFE)

    - Append-only
    - Orchestrator-only write
    - Read-only + filter support
    - Uses absolute path (no CWD bugs)
    """

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    FILE = os.path.join(BASE_DIR, "action_ledger.json")

    def __init__(self):
        if not os.path.exists(self.FILE):
            with open(self.FILE, "w", encoding="utf-8") as f:
                json.dump([], f)

    def log(self, action: str, target: str, result: str, approved: bool):
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "target": target,
            "approved": approved,
            "result": result
        }

        with open(self.FILE, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data.append(record)
            f.seek(0)
            json.dump(data, f, indent=2)

    def read(
        self,
        limit: int = 20,
        action: str | None = None,
        target: str | None = None,
        result: str | None = None
    ):
        with open(self.FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if action:
            data = [d for d in data if d["action"] == action]

        if target:
            data = [d for d in data if target in d["target"]]

        if result:
            data = [d for d in data if d["result"] == result]

        return data[-limit:]
