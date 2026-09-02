# executor.py
import subprocess

class OrionExecutor:
    """
    ORION Executor – Phase 3.9
    Explicit, permissioned execution layer.
    NO reasoning. NO planning. NO autonomy.
    """

    def __init__(self, file_tools):
        self.file_tools = file_tools

        # Explicit allowlist of actions
        self.allowed_actions = {
            "FILE_READ": self._read_file,
            "FILE_LIST": self._list_files,
            "FILE_DELETE": self._delete_file,
            "FILE_EDIT_APPLY": self._apply_edit,
            "SHELL_EXECUTE": self._shell_execute,
        }

    def can_execute(self, action: str) -> bool:
        return action in self.allowed_actions

    def execute(self, action: str, payload: dict):
        if not self.can_execute(action):
            return {
                "status": "ERROR",
                "reason": f"Action '{action}' not permitted"
            }

        return self.allowed_actions[action](payload)

    # ---------- EXECUTORS (NO LOGIC, JUST CALLS) ----------

    def _read_file(self, payload):
        return self.file_tools.read_file(payload["path"])

    def _list_files(self, payload):
        return self.file_tools.list_files()

    def _delete_file(self, payload):
        return self.file_tools.delete_file(payload["path"])

    def _apply_edit(self, payload):
        path = payload["path"]
        content = payload["content"]

        backup = self.file_tools.delete_file(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "status": "SUCCESS",
            "backup": backup
        }

    def _shell_execute(self, payload):
        """
        Executes a shell command.
        CRITICAL: This method assumes authorization has effectively occurred upstream.
        """
        command = payload.get("command")
        if not command:
            return {"status": "ERROR", "reason": "No command provided"}

        print(f"[EXECUTOR] ⚠️  RUNNING SHELL COMMAND: {command}")

        try:
            # Run command and capture output
            result = subprocess.run(
                command,
                shell=True,
                text=True,
                capture_output=True,
                timeout=30 # Safety timeout
            )

            return {
                "status": "SUCCESS" if result.returncode == 0 else "FAILED",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": str(e)
            }

