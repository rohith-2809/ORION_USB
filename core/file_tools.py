# file_tools.py
import os
import shutil
import hashlib
from datetime import datetime

class FileTools:
    """
    ORION FileTools – Phase 3 (Safe FS Layer)

    Guarantees:
    - Root-scoped access only
    - Read, list, delete with backup
    - Hashing + audit metadata
    """

    orion_root = os.environ.get('ORION_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ROOT = orion_root
    BACKUP_DIR = os.path.join(ROOT, ".orion_backup")

    def __init__(self):
        try:
            os.makedirs(self.BACKUP_DIR, exist_ok=True)
        except Exception:
            pass # Ignore if USB is read-only at boot

    # -------------------------
    # Safety
    # -------------------------
    def _resolve_path(self, path: str) -> str:
        full = os.path.abspath(path)
        if not full.startswith(self.ROOT):
            raise PermissionError("Path outside ORION scope")
        return full

    def _hash(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # -------------------------
    # LIST FILES
    # -------------------------
    def list_files(self) -> list:
        result = []
        for name in os.listdir(self.ROOT):
            result.append({
                "name": name,
                "type": "dir" if os.path.isdir(name) else "file"
            })
        return result

    # -------------------------
    # READ FILE (SAFE)
    # -------------------------
    def read_file(self, path: str, limit: int = 2000) -> dict:
        full = self._resolve_path(path)

        if not os.path.exists(full):
            return {"status": "ERROR", "reason": "File not found"}

        stat = os.stat(full)
        sha = self._hash(full)

        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            preview = f.read(limit)

        return {
            "status": "OK",
            "path": full,
            "size": stat.st_size,
            "sha256": sha,
            "preview": preview
        }

    # -------------------------
    # DELETE WITH BACKUP
    # -------------------------
    def delete_file(self, path: str) -> dict:
        full = self._resolve_path(path)

        if not os.path.exists(full):
            return {"status": "ERROR", "reason": "File not found"}

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(
            self.BACKUP_DIR,
            f"{os.path.basename(full)}.{ts}.bak"
        )

        shutil.copy2(full, backup_path)
        sha = self._hash(full)
        os.remove(full)

        return {
            "status": "DELETED",
            "path": full,
            "backup": backup_path,
            "sha256": sha
        }

