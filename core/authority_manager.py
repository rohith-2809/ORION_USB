
import time

class AuthorityManager:
    """
    Manages ORION authority levels.
    Default: USER
    Elevated: GOD (temporary)
    """

    def __init__(self):
        self.level = "USER"
        self.expires_at = None

    def elevate(self, level: str, duration_seconds: int) -> bool:
        if level != "GOD":
            return False

        self.level = level
        self.expires_at = time.time() + duration_seconds
        return True

    def revoke(self):
        self.level = "USER"
        self.expires_at = None

    def current(self) -> str:
        if self.expires_at and time.time() > self.expires_at:
            self.revoke()
        return self.level

    def is_god(self) -> bool:
        return self.current() == "GOD"


class TrustManager:
    """
    Manages Dynamic Trust Scores for Autonomous Execution.
    Refuses to nag the user for actions they have repeatedly approved.
    """
    def __init__(self, db_path="trust_db.json"):
        import json
        self.db_path = db_path
        self.trust_db = {}
        self._load()

    def _load(self):
        import json
        import os
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    self.trust_db = json.load(f)
            except Exception:
                self.trust_db = {}

    def _save(self):
        import json
        with open(self.db_path, "w") as f:
            json.dump(self.trust_db, f, indent=2)

    def _hash_cmd(self, cmd: str) -> str:
        import hashlib
        return hashlib.sha256(cmd.strip().lower().encode()).hexdigest()

    def get_score(self, cmd: str) -> int:
        key = self._hash_cmd(cmd)
        return self.trust_db.get(key, {}).get("score", 0)

    def is_trusted(self, cmd: str) -> bool:
        """
        Returns True if command has sufficient trust score (>= 3).
        """
        return self.get_score(cmd) >= 3

    def update_trust(self, cmd: str, success: bool):
        """
        Success (User Approved) -> +1
        Failure (User Rejected/Failed) -> Reset to 0
        """
        key = self._hash_cmd(cmd)
        entry = self.trust_db.get(key, {"cmd": cmd, "score": 0})

        if success:
            entry["score"] += 1
            print(f"[TRUST] 🛡️ Validated: {cmd} (Score: {entry['score']})")
        else:
            entry["score"] = 0
            print(f"[TRUST] 🚫 Revoked: {cmd}")

        self.trust_db[key] = entry
        self._save()
