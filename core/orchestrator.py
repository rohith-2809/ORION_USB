# orchestrator.py
# ------------------------------------------------
# import statements
# ------------------------------------------------
from datetime import datetime
from fileinput import filename
import os
import sys
import uuid
import time
import difflib
import threading
from datetime import datetime, timezone
from document_engine import DocumentEngine
from memory import OrionMemory
from brain import OrionBrain
from intent_classifier import IntentClassifier
from file_tools import FileTools
from action_ledger import ActionLedger
from reflection import OrionReflection
from policy import OrionPolicy
# from voice_input import OrionVoiceInput
from rag_memory import OrionRAGMemory
from planner import OrionPlanner
from executor import OrionExecutor
from tts import OrionTTS
from conversation_policy import ConversationPolicy
from emergency_policy import EmergencyPolicy
import psutil
from orion_defense_kernel import OrionDefenseKernel
from authority_manager import AuthorityManager, TrustManager
from document_writer import DocumentWriter

class OrionOrchestrator:
    # ------------------------------------------------
    # ORION Orchestrator
    # ------------------------------------------------

    def __init__(self, socketio=None):
        self.socketio = socketio # [NEW] Real-time events
        self.memory = OrionMemory()
        self.brain = OrionBrain()
        self.intent = IntentClassifier()
        self.files = FileTools()
        self.ledger = ActionLedger()
        self.policy = OrionPolicy()
        self.pending_action = None
        # self.voice = OrionVoiceInput()
        self.rag = OrionRAGMemory()

        # [COGNITIVE ARCHITECTURE]
        self.planner = OrionPlanner(self.brain, self.memory)
        self.executor = OrionExecutor(self.files)
        # self.reflection initialized after memory to resolve recursive dependency if needed,
        # but here we just pass them.
        self.reflection = OrionReflection(self.brain, self.memory)

        self.active_plan = None
        self.plan_cursor = 0
        self.step_approved = False
        self.is_busy = False

        # [NEW] Unified Voice System
        print("[ORION] Initializing Voice Subsystem (Loading NeMo/Vosk)...")
        from orion_voice_system import OrionVoiceSystem
        self.voice = OrionVoiceSystem(socketio=self.socketio) # Pass socketio down
        self.tts = self.voice # Compatibility alias for existing TTS calls

        self.pending_voice_intent = None
        self.awaiting_authority_since = None
        self.last_security_event = None
        self.authority = AuthorityManager()
        self.authority.trust = TrustManager() # [NEW] Trust System
        self.doc_engine = DocumentEngine(self.brain)

        # ─────────────────────────────────────
        # ORION DEFENSE KERNEL (BACKGROUND)
        # ─────────────────────────────────────

        self.kernel = OrionDefenseKernel(
            watch_path="/",
            event_sink=self.receive_security_event
        )
        self.kernel.set_event_callback(self.receive_security_event)


    # ---------- CODE SANITY GUARD ----------
    def _is_valid_code(self, text: str) -> bool:
        banned = ["```", "here is", "i propose", "explanation"]
        lower = text.lower()
        if any(b in lower for b in banned):
            return False
        return any(k in text for k in ["def ", "class ", "import ", "from "])

    # ================= COGNITIVE LOOP (PHASE 7) =================
    def _execute_cognitive_loop(self, goal: str):
        """
        1. PLAN: Uses Planner to generate steps.
        2. ASK: Presents plan to user.
        """
        print(f"[ORION] 🧠 Planning goal: {goal}")
        self.tts.speak("I am planning that task. One moment.")

        # 1. Generate Plan
        plan = self.planner.plan(goal)

        if not plan.get("executable"):
            self.tts.speak("I could not generate a valid plan for that request.")
            return {"type": "ERROR", "msg": "Planning failed"}

        # 2. Store Plan
        self.active_plan = plan
        self.plan_cursor = 0

        # 3. Summarize to User
        steps_count = len(plan['steps'])
        steps_desc = ", ".join([s.get('description', 'step') for s in plan['steps'][:3]])
        msg = f"I have a plan with {steps_count} steps. I will {steps_desc}. Shall I proceed?"

        self.tts.speak(msg)
        self.pending_voice_intent = "EXECUTE_PLAN"

        return {
            "type": "PLAN_PROPOSED",
            "plan": plan
        }

    def _run_active_plan(self):
        """
        Executes the next steps in the active plan until completion
        or a GATED action (SHELL_EXECUTE) is encountered.
        """
        if not self.active_plan:
            self.tts.speak("I have no active plan.")
            return

        steps = self.active_plan['steps']

        while self.plan_cursor < len(steps):
            step = steps[self.plan_cursor]
            action = step['action']
            payload = step['payload']
            desc = step.get('description', 'Unknown Step')

            print(f"[ORION] ⏳ Executing Step {self.plan_cursor + 1}: {desc}")

            # GATED ACTION CHECK
            if action == "SHELL_EXECUTE":
                cmd = payload.get('command')

                # [TRUST SYSTEM] Auto-approve if trusted
                if self.authority.trust.is_trusted(cmd):
                    print(f"[ORION] 🛡️ Trust Check Passed: {cmd}")
                    self.tts.speak("Auto-executing trusted command.")

                # Check if we just got approval
                elif getattr(self, "step_approved", False):
                    # Proceed with execution and reset flag
                    self.step_approved = False
                else:
                    # STOP AND ASK
                    msg = f"Step {self.plan_cursor + 1} requires running command: {cmd}. Approve?"
                    self.tts.speak(msg)
                    self.pending_voice_intent = "CONTINUE_PLAN" # Waiting for NEXT "Yes"
                    return # Exit loop, wait for user

            # EXECUTE SAFE ACTION (OR APPROVED SHELL)
            result = self.executor.execute(action, payload)

            # [TRUST UPDATE]
            if action == "SHELL_EXECUTE":
                is_success = result.get("status") == "SUCCESS"
                cmd = payload.get('command')
                self.authority.trust.update_trust(cmd, is_success)

            # Log
            self.ledger.log(action, "COGNITIVE_LOOP", str(payload), True) # Assume approved by plan

            if result.get("status") == "ERROR":
                # [SELF-HEALING]
                error_msg = result.get('reason', 'Unknown Error')
                print(f"[ORION] 🩹 Step Failed: {error_msg}")

                # 1. Check for infinite loop (limit 1 heal per step)
                if step.get("healing_attempt"):
                     self.tts.speak(f"Self-healing failed. Error persists: {error_msg}. Aborting plan.")
                     self.active_plan = None
                     return

                # 2. Ask Brain for Fix
                self.tts.speak("Step failed. Attempting to auto-correct.")

                fix_prompt = (
                    f"The step '{desc}' failed with error: '{error_msg}'. "
                    "Provide a single corrective step to fix this (e.g., install missing module, create missing directory). "
                    "Return ONLY JSON: {\"action\": ..., \"payload\": ..., \"description\": ...}"
                )

                try:
                    # Clean imports inside method to avoid dependency hell risk
                    import json
                    fix_resp = self.brain.think(fix_prompt)
                    fix_json = self.planner._clean_json(fix_resp)
                    fix_step = json.loads(fix_json)

                    # Mark as a fix to prevent infinite recursion
                    fix_step["healing_attempt"] = True
                    fix_step["description"] = f"[FIX] {fix_step.get('description', 'Corrective Action')}"

                    # 3. Inject Fix
                    # Insert at current cursor. Execution will run this next, then increment to original step.
                    self.active_plan['steps'].insert(self.plan_cursor, fix_step)
                    print(f"[ORION] 💉 Injected Fix: {fix_step['description']}")

                    # Do NOT increment cursor here. Next loop iteration (or recursion) runs the fix at current cursor.
                    continue

                except Exception as e:
                    print(f"[ORION] Healing Logic Failed: {e}")
                    self.tts.speak(f"Critical failure: {error_msg}. Halting.")
                    self.active_plan = None
                    return

            self.plan_cursor += 1

        # PLAN COMPLETE
        self.tts.speak("Task complete.")

        # [MEMORY] Store Successful Plan
        if self.active_plan and self.active_plan.get("source") == "BRAIN":
            # Only store new plans generated by the Brain
            goal = self.active_plan.get("goal")
            steps = self.active_plan.get("steps")
            if goal and steps:
                self.memory.store_successful_plan(goal, steps)

        # REFLECTION
        self.reflection.post_mortem(self.ledger)
        self.active_plan = None
        self.pending_voice_intent = None

    # ================= ROUTER =================
    def route(self, user_input: str, god_mode: bool = False) -> dict:
        if getattr(self, "is_busy", False):
            return {"type": "ERROR", "content": "I am currently processing a task. Please wait."}

        self.is_busy = True
        try:
            return self._route_impl(user_input, god_mode)
        except Exception as e:
            print(f"[ORCHESTRATOR] Routing Error: {e}")
            return {"type": "ERROR", "content": f"Internal Error: {e}"}
        finally:
            self.is_busy = False

    def _route_impl(self, user_input: str, god_mode: bool = False) -> dict:
        decision = self.intent.classify(user_input)
        intent = decision.get("intent")

        # [COGNITIVE LOOP]
        if intent == "COMPLEX_TASK":
            return self._execute_cognitive_loop(decision["goal"])

        # ---------- AUTHORITY ENABLE (GOD MODE) ----------
        if intent == "AUTHORITY_ENABLE":
            duration = decision.get("duration", 120)

            self.authority.elevate("GOD", duration)

            self.ledger.log(
                "AUTHORITY_ENABLE",
                "GOD",
                f"{duration}s",
                True
            )

            return {
                "type": "AUTHORITY",
                "content": f"GOD MODE enabled for {duration} seconds"
            }

            # ---------- AUTHORITY DISABLE ----------
        if intent == "AUTHORITY_DISABLE":
            self.authority.revoke()

            self.ledger.log(
                "AUTHORITY_DISABLE",
                "GOD",
                "REVOKED",
                True
            )

            return {
                "type": "AUTHORITY",
                "content": "GOD MODE disabled"
            }

        # ---------- AUTHORITY CHECK ----------
        if intent in ("DOCUMENT_CREATE", "FILE_UPDATE", "FILE_SEND"):
            if not (god_mode or self.authority.is_god()):
                return {
                    "type": "ERROR",
                    "content": "This action requires GOD MODE"
                }
        # ---------- MEMORY STORE ----------
        if intent == "MEMORY_STORE":
            self.memory.add(decision["key"], decision["value"])
            self.ledger.log("MEMORY_STORE", decision["key"], "SUCCESS", True)
            return {"type": "MEMORY_STORE", "content": "Saved"}

        # ---------- MEMORY QUERY ----------
        if intent == "MEMORY_QUERY":
            mem = self.memory.get_by_key(decision["key"])
            return {
                "type": "MEMORY_RESULT",
                "content": mem["value"] if mem else "UNKNOWN"
            }

        # ---------- FILE LIST ----------
        if intent == "FILE_LIST":
            return {
                "type": "FILE_RESULT",
                "content": self.files.list_files()
            }

        # ---------- FILE READ ----------
        if intent == "FILE_READ":
            return {
                "type": "FILE_RESULT",
                "content": self.files.read_file(decision["path"])
            }
        # ---------- DOCUMENT CREATE (GOD MODE) ----------
        if intent == "DOCUMENT_CREATE":
            filename = decision.get("filename", "ORION_DOCUMENT")
            fmt = decision.get("format", "txt")
            topic = decision.get("topic")

            if not topic:
                return {
                    "type": "ERROR",
                    "content": "Document topic is required"
                }

            # ================= FILE CONTEXT AWARENESS =================
            context_data = None

            # 1. Check if topic is a direct file path
            if os.path.exists(topic) and os.path.isfile(topic):
                try:
                    with open(topic, "r", encoding="utf-8") as f:
                        context_data = f.read()
                    print(f"[ORCHESTRATOR] Attached local file context: {topic}")
                except Exception as e:
                    print(f"[ORCHESTRATOR] Failed to read context file: {e}")

            # 2. Check if topic is a filename in CWD (if not absolute)
            elif not os.path.isabs(topic):
                 parts = topic.split() # Handle "main.py" inside "Create doc for main.py"? No, classifier extracts "main.py"
                 # The classifier might return "main.py"
                 if os.path.exists(topic) and os.path.isfile(topic):
                      with open(topic, "r", encoding="utf-8") as f:
                          context_data = f.read()

            # ================= NEW JOB FLOW =================
            self.pending_action = {
                "type": "DOCUMENT_JOB_START",
                "topic": topic,
                "filename": filename,
                "format": fmt,
                "mode": decision.get("mode", "standard"),
                "context": context_data
            }

            if god_mode:
                return self.route("confirm", god_mode=True)

            msg = f"Confirm START of document job: {topic} (Format: {fmt})"
            if context_data:
                msg += f" [With Context: {len(context_data)} chars]"

            return {
                "type": "CONFIRM_REQUIRED",
                "content": msg
            }

        # ---------- DOCUMENT RESUME ----------
        if intent == "DOCUMENT_RESUME":
            job_id = decision.get("job_id")

            # Auto-detect latest job if not provided
            if not job_id:
                jobs_dir = self.doc_engine.JOBS_DIR
                if os.path.exists(jobs_dir):
                     files = [os.path.join(jobs_dir, f) for f in os.listdir(jobs_dir) if f.endswith(".json")]
                     if files:
                         latest = max(files, key=os.path.getmtime)
                         job_id = os.path.splitext(os.path.basename(latest))[0]

            if not job_id:
                return {
                    "type": "ERROR",
                    "content": "No job ID provided and no recent jobs found."
                }

            self.pending_action = {
                "type": "DOCUMENT_JOB_RESUME",
                "job_id": job_id
            }

            if god_mode:
                return self.route("confirm", god_mode=True)

            return {
                "type": "CONFIRM_REQUIRED",
                "content": f"Confirm RESUME of document job: {job_id}"
            }

        # ---------- FILE DELETE ----------
        if intent == "FILE_DELETE":
            self.pending_action = {
                "type": "DELETE",
                "path": decision["path"]
            }

            if god_mode:
                return self.route("confirm", god_mode=True)

            return {
                "type": "CONFIRM_REQUIRED",
                "content": f"Confirm deletion of {decision['path']}"
            }

        # ---------- POLICY CHECK (PRE-EDIT) ----------
        if intent == "FILE_EDIT":
            recent_actions = self.ledger.read(limit=100)
            reflection = self.reflection.analyze(recent_actions)
            warnings = self.policy.evaluate(intent, decision, reflection)

            if warnings:
                return {
                    "type": "POLICY_WARNING",
                    "content": warnings
                }

            data = self.files.read_file(decision["path"])
            if data.get("status") == "ERROR":
                self.ledger.log("FILE_EDIT", decision["path"], "ERROR", False)
                return {"type": "ERROR", "content": "File not found"}

            original = data["preview"]

            proposal = self.brain.think(
                "ONLY raw Python code. FULL FILE. NO prose.\n\n" + original
            )

            if not self._is_valid_code(proposal):
                self.ledger.log("FILE_EDIT", decision["path"], "REJECTED", False)
                return {"type": "ERROR", "content": "Invalid code proposal"}

            diff = list(
                difflib.unified_diff(
                    original.splitlines(),
                    proposal.splitlines(),
                    lineterm=""
                )
            )

            if not diff:
                self.ledger.log("FILE_EDIT", decision["path"], "NO_CHANGE", False)
                return {"type": "ERROR", "content": "Empty diff"}

            self.pending_action = {
                "type": "EDIT",
                "path": decision["path"],
                "proposal": proposal
            }

            if god_mode:
                return self.route("confirm", god_mode=True)

            return {
                "type": "EDIT_PROPOSAL",
                "content": {
                    "path": decision["path"],
                    "diff": "\n".join(diff)
                }
            }

             # ---------- CONFIRM ----------
        if intent == "CONFIRM":
            # [COGNITIVE LOOP] Voice Priority
            if self.pending_voice_intent in ["EXECUTE_PLAN", "CONTINUE_PLAN"]:
                self.tts.speak("Proceeding with plan.")
                self.step_approved = True
                self.pending_voice_intent = None
                self._run_active_plan()
                return {"type": "PLAN_EXECUTION", "status": "Running"}

            if not self.pending_action:
                return {"type": "ERROR", "content": "Nothing to confirm"}

            action = self.pending_action
            self.pending_action = None

            if action["type"] == "DELETE":
                res = self.files.delete_file(action["path"])
                self.ledger.log("FILE_DELETE", action["path"], "SUCCESS", True)
                return {"type": "FILE_DELETED", "content": res}

            if action["type"] == "EDIT":
                backup = self.files.delete_file(action["path"])
                with open(action["path"], "w", encoding="utf-8") as f:
                    f.write(action["proposal"])
                self.ledger.log("FILE_EDIT", action["path"], "SUCCESS", True)
                return {"type": "FILE_EDITED", "content": backup}
            if action["type"] == "DOCUMENT_JOB_START":
                # 1. Start Job
                fmt = action.get("format", "md")
                mode = action.get("mode", "standard")
                pages = action.get("pages") # Extract pages

                job = self.doc_engine.start_job(
                    action["topic"],
                    context=action.get("context"),
                    mode=mode,
                    output_format=fmt,
                    pages=pages # Pass to engine
                )
                self.tts.speak(f"Starting job {job.job_id}. This is crash-safe.")

                try:
                    # 2. Process (Blocking Loop)
                    result_info = self.doc_engine.process_job()

                    # 3. Export
                    import re
                    safe_filename = re.sub(r'[\\/*?:"<>|]', "", action['filename']).strip()
                    if not safe_filename:
                        safe_filename = "ORION_DOCUMENT"
                    final_path = os.path.abspath(f"{safe_filename}.{fmt}")
                    print(f"[ORION DOC] Finalizing export to: {final_path}")

                    if fmt == "docx":
                        with open(job.output_path, "r", encoding="utf-8") as f:
                            md_content = f.read()
                        DocumentWriter.write_docx(final_path, md_content)
                        return {"type": "DOCUMENT_CREATED", "content": f"Saved to {final_path}"}

                    elif fmt == "pptx":
                        # PPTX is already created at job.output_path by finalize_pptx
                        import os, shutil
                        if not os.path.exists(job.output_path):
                            raise FileNotFoundError(f"PPTX file was not generated at {job.output_path}")
                        shutil.move(job.output_path, final_path)
                        return {"type": "PRESENTATION_CREATED", "content": f"Presentation saved to {final_path}"}

                    return {"type": "DOCUMENT_CREATED", "content": f"Markdown saved to {job.output_path}"}

                except Exception as e:
                    print(f"❌ Document/PPT Generation Failed: {e}")
                    import traceback
                    traceback.print_exc()
                    return {"type": "ERROR", "content": f"Failed to generate or save file: {e}"}

            if action["type"] == "DOCUMENT_JOB_RESUME":
                job = self.doc_engine.resume_job(action["job_id"])
                if not job:
                    return {"type": "ERROR", "content": "Job not found"}

                self.tts.speak(f"Resuming job {job.job_id}...")
                try:
                    result_info = self.doc_engine.process_job()

                    # 3. Export
                    fmt = getattr(job, "output_format", "md")
                    import re
                    safe_topic = re.sub(r'[\\/*?:"<>|]', "", job.topic).strip()
                    if not safe_topic:
                        safe_topic = "ORION_DOCUMENT"
                    safe_filename = safe_topic.replace(" ", "_").upper()
                    final_path = os.path.abspath(f"{safe_filename}.{fmt}")

                    if fmt == "docx":
                        with open(job.output_path, "r", encoding="utf-8") as f:
                            md_content = f.read()
                        DocumentWriter.write_docx(final_path, md_content)
                        return {"type": "DOCUMENT_CREATED", "content": f"Saved to {final_path}"}

                    elif fmt == "pptx":
                        import os, shutil
                        if not os.path.exists(job.output_path):
                            raise FileNotFoundError(f"PPTX file was not generated at {job.output_path}")
                        shutil.move(job.output_path, final_path)
                        return {"type": "PRESENTATION_CREATED", "content": f"Presentation saved to {final_path}"}

                    return {"type": "DOCUMENT_CREATED", "content": f"Markdown saved to {job.output_path}"}

                except Exception as e:
                    print(f"❌ Document/PPT Resume Failed: {e}")
                    import traceback
                    traceback.print_exc()
                    return {"type": "ERROR", "content": f"Failed to resume or save file: {e}"}

            # ---------- EXECUTE ----------
            if action["type"] == "EXECUTE":
                result = self.executor.execute(
                    action["action"],
                    action["payload"]
                )

                if isinstance(result, dict):
                    status = result.get("status", "SUCCESS")
                else:
                    status = "SUCCESS"

                self.ledger.log(
                    action["action"],
                    str(action["payload"]),
                    status,
                    True
                )

                return {
                    "type": "EXECUTION_RESULT",
                    "content": result
                }

        # ---------- CANCEL ----------
        if intent == "CANCEL":
            if self.pending_action:
                self.ledger.log(
                    self.pending_action["type"],
                    self.pending_action.get("path", ""),
                    "CANCELLED",
                    False
                )
            self.pending_action = None
            return {"type": "CANCELLED", "content": "Cancelled"}

        # ---------- ACTION LOG ----------
        if intent == "ACTION_LOG":
            return {
                "type": "ACTION_LOG",
                "content": self.ledger.read()
            }

        # ---------- ACTION LOG FILTER ----------
        if intent == "ACTION_LOG_FILTER":
            q = decision["query"]

            action = None
            target = None
            result = None

            for part in q.split():
                if part.upper() in ("FILE_EDIT", "FILE_DELETE", "MEMORY_STORE"):
                    action = part.upper()
                elif part.upper() in ("SUCCESS", "ERROR", "CANCELLED", "REJECTED"):
                    result = part.upper()
                else:
                    target = part

            return {
                "type": "ACTION_LOG",
                "content": self.ledger.read(
                    action=action,
                    target=target,
                    result=result
                )
            }

               # ---------- REFLECTION ----------
        if intent == "REFLECTION":
            actions = self.ledger.read(limit=100)
            analysis = self.reflection.analyze(actions)
            return {
                "type": "REFLECTION",
                "content": analysis
            }

          # ---------- RAG ADD ----------
        if intent == "RAG_ADD":
            res = self.rag.add_document(decision["text"])
            self.ledger.log("RAG_ADD", "knowledge", "SUCCESS", True)
            return {"type": "RAG", "content": res}

        # ---------- RAG QUERY ----------
        if intent == "RAG_QUERY":
            retrieved = self.rag.retrieve(decision["query"])

            if not retrieved:
                return {
                    "type": "RAG",
                    "content": "No relevant knowledge found"
                }

            context = "\n\n".join(
                f"[{r['source']}] {r['text']}"
                for r in retrieved
            )

            answer = self.brain.think(
                "Use the following context ONLY for reasoning. "
                "Do NOT assume authority or perform actions.\n\n"
                f"Context:\n{context}\n\n"
                f"Question:\n{decision['query']}"
            )

            return {
                "type": "RAG_RESPONSE",
                "content": answer,
                "sources": retrieved
            }

              # ---------- PLANNER ----------
        if intent == "PLAN":
            # Optional: use RAG to enrich planning
            retrieved = self.rag.retrieve(decision["goal"]) if hasattr(self, "rag") else []

            context = None
            if retrieved:
                context = "\n".join(r["text"] for r in retrieved)

            plan = self.planner.plan(
                goal=decision["goal"],
                context=context
            )

            self.ledger.log("PLAN", "goal", "SUCCESS", False)

            return {
                "type": "PLAN",
                "content": plan
            }

                # ---------- CODE GENERATION ----------
        if intent == "CODE_GEN":
            topic = decision.get("topic")
            print(f"🧩 Generating Code for: {topic}")

            # Simple direct prompt to Brain
            prompt = (
                f"Write a complete, executable Python script for: {topic}.\n"
                "Provide ONLY the code block. No markdown, no explanations.\n"
                "Start with 'import' and end with 'if __name__ == \"__main__\":'."
            )

            code = self.brain.think(prompt)

            # Save to file
            filename = topic.replace(" ", "_").lower() + ".py"
            orion_root = os.environ.get('ORION_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            # Save generated code to output dir
            out_dir = os.path.join(orion_root, "brain", "outputs")
            os.makedirs(out_dir, exist_ok=True)
            filepath = os.path.join(out_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)

            return {
                "type": "CODE_GEN",
                "content": f"Generated code saved to {filename}",
                "path": filepath
            }

        # ---------- DEFENSE COMMANDS ----------
        if intent == "DEFENSE_KILL":
            target = decision.get("target")
            res = self.kernel.execute_manual_action("KILL_PROCESS", target)
            return {"type": "DEFENSE_ACTION", "content": res}

        if intent == "DEFENSE_BLOCK":
            target = decision.get("target")
            res = self.kernel.execute_manual_action("BLOCK_IP", target)
            return {"type": "DEFENSE_ACTION", "content": res}

        if intent == "DEFENSE_SCAN":
            # Just a status report for now as kernel is always scanning
            state = self.kernel.memory.incident_state.value
            return {"type": "DEFENSE_STATUS", "content": f"System Scan Active. Status: {state.upper()}"}

        # ================= MAINTENANCE COMMANDS =================
        if intent == "MAINTENANCE_SCAN":
            return self.trigger_agent_scan()

        if intent == "MAINTENANCE_CLEAN":
            return self.trigger_agent_clean()

        if intent == "MAINTENANCE_INTEGRITY":
            return self.trigger_agent_integrity()


        # ---------- EXECUTE STEP (EXPLICIT) ----------
        if intent == "EXECUTE":
            action = decision.get("action")
            payload = decision.get("payload", {})

            if not self.executor.can_execute(action):
                return {
                    "type": "ERROR",
                    "content": f"Execution not allowed: {action}"
                }

            # FINAL CONFIRMATION GATE
            self.pending_action = {
                "type": "EXECUTE",
                "action": action,
                "payload": payload
            }

            return {
                "type": "CONFIRM_REQUIRED",
                "content": f"Confirm execution of {action}"
            }

        # ---------- CHAT (CONVERSATIONAL, SAFE) ----------

        # [MEMORY] Retrieve Context (Phase 13)
        past_episodes = self.memory.search_episodes(user_input, limit=2)
        context_str = ""
        if past_episodes:
            context_str = "\n[RELEVANT PAST CONVERSATIONS]\n" + "\n".join(
                [f"User: {e['user']}\nOrion: {e['agent']}" for e in past_episodes]
            )

        # Inject Context into Prompt
        base_prompt = ConversationPolicy.wrap(user_input)
        full_prompt = f"{context_str}\n\n{base_prompt}"

        reply = self.brain.think(full_prompt)

        if not reply or not reply.strip():
            reply = (
                "I am listening. "
                "You can speak to me naturally, or ask me to explain something."
            )

        response = {
            "type": "CHAT",
            "content": reply
        }

        # [NEW] Record interaction history across all modes
        self.memory.add_episode(user_input, response.get("content", ""))

        # [NEW] Check for facts after the response
        threading.Thread(target=self._extract_and_store_facts, args=(user_input, response.get("content", "")), daemon=True).start()

        return response

    def _extract_and_store_facts(self, user_text: str, agent_text: str):
        """Asynchronously extracts facts and preferences from conversation."""
        prompt = (
            "Analyze the following conversation and extract any new concrete personal facts "
            "or preferences about the user. Only return facts that represent long-term knowledge "
            "(e.g., 'User likes dark mode', 'User is a developer'). "
            "If there are none, simply output 'NONE'.\n\n"
            f"User: {user_text}\n"
            f"Orion: {agent_text}\n\n"
            "Format your answer as a JSON key-value pair, e.g., {\"user_preference\": \"dark mode\"} or NONE."
        )

        try:
            extraction = self.brain.think(prompt, max_tokens=150)
            if "NONE" not in extraction.upper() and "{" in extraction:
                import json
                # Try to parse the json
                start = extraction.find("{")
                end = extraction.rfind("}") + 1
                if start != -1 and end != -1:
                    data = json.loads(extraction[start:end])
                    for k, v in data.items():
                        print(f"[ORION] 🧠 Learned new fact: {k} -> {v}")
                        self.memory.add(k, v)
        except Exception as e:
            print(f"[ORION] Fact Extraction Error: {e}")


    # ==========================================================
    # VOICE LOOP
    # ==========================================================
    def always_on_voice_loop(self):
        print("🟢 ORION Always-On Voice Active")

        while True:
            self.check_emergency_timeout()

            # 🔒 DO NOT LISTEN while system is speaking / processing
            if not self.voice_active:
                time.sleep(0.1)
                continue

            # ---------------- LISTEN ----------------
            text = self.voice.listen_for_command(is_active_cb=lambda: getattr(self, "voice_active", True))
            if not text:
                time.sleep(0.1)
                continue

            # 🔒 STOP LISTENING while processing
            self.voice_active = False

            # ---------------- CLASSIFY ONCE ----------------
            decision = self.intent.classify(text)
            intent = decision.get("intent")

            # ---------------- STRAY CONFIRM / CANCEL ----------------
            if intent in ("CONFIRM", "CANCEL") and not self.pending_voice_intent:
                self.tts.speak("There is no pending command.")
                self.voice_active = True
                continue

            # ---------------- CONFIRMATION PHASE ----------------
            if self.pending_voice_intent:

                if intent == "CONFIRM":
                    confirmed_text = self.pending_voice_intent
                    self.pending_voice_intent = None

                    self.tts.speak("Confirmed. Routing request.")
                    response = self.route(confirmed_text)
                    self._speak_response(response)

                    self.voice_active = True
                    continue

                if intent == "CANCEL":
                    self.pending_voice_intent = None
                    self.tts.speak("Cancelled.")

                    self.voice_active = True
                    continue

                # Correction / replacement command
                self.pending_voice_intent = text
                self.tts.speak("Command changed. Say confirm to execute.")

                self.voice_active = True
                continue

            # ---------------- NEW ACTIONABLE COMMAND ----------------
            if intent in (
                "EXECUTE",
                "FILE_DELETE",
                "FILE_EDIT",
                "PLAN",
                "MEMORY_STORE",
                "RAG_ADD",
            ):
                self.pending_voice_intent = text
                self.tts.speak(f"I heard: {text}. Say confirm to proceed.")

                self.voice_active = True
                continue

            # ---------------- SAFE / NON-ACTIONABLE ----------------
            self.voice._emit_status('orion', 'processing')
            response = self.route(text)
            self._speak_response(response)
            time.sleep(0.3)  # allow TTS pipeline to start

            self.voice_active = True

    # ==========================================================
    # SYSTEM MAINTENANCE TRIGGERS
    # ==========================================================
    def trigger_agent_scan(self):
        """
        Triggers a Deep Scan directly on the underlying host operating system.
        """
        if not hasattr(self, 'kernel'):
            return {"status": "error", "message": "Defense Kernel not initialized"}

        cmd_id = str(uuid.uuid4())
        print(f"[ORCHESTRATOR] 🛡️ Triggering Deep Scan: {cmd_id}")

        self.tts.speak("Initiating deep system scan on the host operating system.")

        # Execute the scan block directly using the Kernel
        findings = self.kernel.perform_local_host_scan()

        # Summarize Findings
        if len(findings) > 0:
            self.tts.speak(f"Scan complete. I have detected {len(findings)} potential anomalies.")
        else:
            self.tts.speak("Scan complete. The system appears secure.")

        return {
            "status": "triggered",
            "id": cmd_id,
            "scan_complete": True,
            "threats_found": len(findings),
            "findings": findings
        }

    def trigger_agent_clean(self):
        """
        Triggers System Cleanup (Portable Mode).
        """
        cmd_id = str(uuid.uuid4())
        print(f"[ORCHESTRATOR] 🧹 Triggering System Cleanup: {cmd_id}")

        self.memory.optimize_storage()

        self.tts.speak("Starting portable system cleanup protocol and optimizing cache.")
        return {"status": "triggered", "id": cmd_id}

    def trigger_agent_integrity(self):
        """
        Triggers Sandbox Integrity Check (Portable Mode).
        """
        cmd_id = str(uuid.uuid4())
        print(f"[ORCHESTRATOR] 🛡️ Triggering Integrity Check: {cmd_id}")

        # Check basic portable dependencies
        orion_root = os.environ.get('ORION_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        models_safe = os.path.exists(os.path.join(orion_root, "models"))

        if models_safe:
            self.tts.speak("Verifying system integrity. Neural pathways are intact.")
        else:
            self.tts.speak("Integrity failure. Missing neural models.")

        return {"status": "triggered", "id": cmd_id}

    def _lock_mic(self):
        self.voice_active = False

    def _unlock_mic(self):
        self.voice_active = True

    # ==========================================================
    # SPEAK RESPONSE (MIC SAFE)
    # ==========================================================
    # ==========================================================
    # SPEAK RESPONSE (MIC SAFE)
    # ==========================================================
    def _clean_text_for_tts(self, text: str) -> str:
        """
        Strip markdown, special characters, and lengthy formatting
        before sending to NeMo TTS.
        """
        if not text: return ""

        # 1. Strip Markdown Bold/Italic
        text = text.replace("**", "").replace("__", "").replace("`", "")
        text = text.replace("#", "")

        # 2. Normalize Punctuation (NeMo hates em-dashes and weird quotes)
        text = text.replace("–", "-").replace("—", "-")
        text = text.replace('"', "").replace("'", "")

        # 3. Collapse Newlines
        text = " ".join(text.split())

        return text

    def _speak_response(self, response):
        print("🔊 _speak_response CALLED:", response)

        if not response or not isinstance(response, dict):
            return

        content = response.get("content")
        if not content:
            return

        # CLEANUP FOR VOICE CLARITY
        clean_content = self._clean_text_for_tts(str(content))

        # 🔒 HARD MIC LOCK
        self._lock_mic()

        self.tts.speak(clean_content)
        self._unlock_mic()

# ==========================================================
#           SECURITY EVENT RECEIVER (FROM ODK)
# ==========================================================
    def receive_security_event(self, event: dict):
        #
        # Called by ORION Defense Kernel (BACKGROUND THREAD).
        # MUST NEVER THROW.
        #
        try:
            print("[ORCHESTRATOR] Event received from Defense:")
            print(event)

            # 🛑 1. HANDLE DEFENSE PROPOSALS (Voice Interrupt)
            if event.get("type") == "DEFENSE_PROPOSAL":
                finding = event.get("finding")
                action = event.get("action")
                target = event.get("target")

                # Voice Alert
                msg = f"Rohith, there is an attack: {finding}. Should I act?"
                self.tts.speak(msg)

                # Queue the Remediation Command
                if action == "KILL_PROCESS":
                    self.pending_voice_intent = f"kill process {target}"
                elif action == "BLOCK_IP":
                    self.pending_voice_intent = f"block ip {target}"

                # Unlock voice so user can say "Confirm" or "Yes"
                self.voice_active = True
                return

            # 2. STANDARD EVENT LOGGING
            # Ignore duplicate confirmed incidents
            if self.last_security_event:
                if (
                    self.last_security_event.get("finding") == event.get("finding")
                    and self.last_security_event.get("state") == event.get("state")
                ):
                    return

            self.last_security_event = event
            self.awaiting_authority_since = time.time()

            # Log deterministically
            self.ledger.log(
                "SECURITY_INCIDENT",
                event.get("finding"),
                event.get("state"),
                False
            )
        # ✅ SEMANTIC SAFE SUMMARY ONLY
            summary = (
                f"Security incident detected: {event.get('finding')} | "
                f"state={event.get('state')} | "
                f"confidence={event.get('confidence')}"
            )
            self.memory.add("last_incident", summary)

        except Exception as e:
        # ABSOLUTE LAST LINE OF DEFENSE
         print("[ORCHESTRATOR][ERROR] receive_security_event failed:", e)

# ----------------------------------------------------------
#                 EMERGENCY TIMEOUT CHECK
# ----------------------------------------------------------

    def check_emergency_timeout(self):
        if not self.awaiting_authority_since or not self.last_security_event:
            return

        elapsed = time.time() - self.awaiting_authority_since

        if EmergencyPolicy.is_emergency(self.last_security_event, elapsed):
            self.awaiting_authority_since = None
            self._emergency_act(self.last_security_event)

# ----------------------------------------------------------
#                 EMERGENCY ACTION
# ----------------------------------------------------------


    def _emergency_act(self, incident):
        print("[ORION EMERGENCY] Authority timeout exceeded")
        print("[ORION EMERGENCY] Acting to prevent damage")

        actions = incident.get("mitigation_plan", {}).get("actions", [])
        executed = []
        for action in actions:
            try:
                if EmergencyPolicy.is_action_allowed(action):
                    result = self.executor.security_engine.execute(action)
                    executed.append({
                    "action": action,
                    "result": result
                })
            except Exception as e:
                self.ledger.log(
                "EMERGENCY_ACTION",
                    action.get("type"),
                    f"FAILED: {e}",
                    False
                )
        snapshot = self._take_forensic_snapshot()

        self.memory.add(
            "emergency_snapshot",
            f"Forensic snapshot taken at {snapshot.get('timestamp')}"
        )


        self.ledger.log(
            "EMERGENCY_FALLBACK",
            "system",
            "CONTAINED",
            True
        )
        print("[ORION EMERGENCY] System contained")

# ----------------------------------------------------------
#                 FORENSIC SNAPSHOT
# ----------------------------------------------------------

    def _take_forensic_snapshot(self):
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu": psutil.cpu_percent(),
            "memory": psutil.virtual_memory().percent,
            "processes": [p.info for p in psutil.process_iter(["pid", "name", "exe"])],
            "network": [str(c) for c in psutil.net_connections(kind="inet")]
        }

    # 5. [NEW] Check Voice Input (Non-blocking check if possible, or blocking for now)
    # For simplicity in this loop, we might need a separate thread or a quick check.
    # But since `listen_for_wake_word` is blocking by design in the current implementation,
    # we should add a dedicated "Voice Mode" or run it in a thread.
    # For now, let's assume the user triggers voice via a specific key or we just poll if we have a non-blocking way.
    # Since we don't have a non-blocking wake word yet, we will skip adding it to the *infinite* loop for now
    # to avoid blocking the bridge/telemetry.
    # Ideally, we would run `self.voice.listen_for_wake_word()` in a thread.

    def enter_voice_mode(self):
        """
        Dedicated mode where Orion LISTENS for wake word, then records.
        (Hands-Free)
        """
        print("🎙️ Entering HANDS-FREE VOICE MODE (Press Ctrl+C to exit)...")
        self.voice.speak("Voice systems online. Say Orion.")

        while True:
            try:
                # 1. Wait for Wake Word (BLOCKING)
                if self.voice.listen_for_wake_word():
                    # 2. Acknowledge
                    self.voice.speak("Yes?")

                    # 3. Record Command (5s)
                    audio = self.voice.record_command(seconds=5)

                    print("📝 Transcribing...")
                    try:
                        text = self.voice.transcribe(audio)
                    except Exception as e:
                        print(f"Transcription Error: {e}")
                        text = ""

                    if text:
                        print(f"🗣️ USER: {text}")
                        # Route the command
                        response = self.route(text)

                        # Speak result
                        if response:
                             content = response.get("content", "")
                             if content:
                                 self.voice.speak(content)
                    else:
                        self.voice.speak("I didn't catch that.")

            except KeyboardInterrupt:
                print("\n👋 Exiting Voice Mode...")
                break

if __name__ == "__main__":
    print("🟢 ORION Orchestrator Online (VOICE MODE)")

    orion = OrionOrchestrator()
    # orion.always_on_voice_loop()

    # Main loop (text-based)
    if len(sys.argv) > 1 and sys.argv[1] == "--voice":
        orion.enter_voice_mode()
    else:
        while True:
            try:
                user_input = input("ORION > ").strip()
                if not user_input:
                    continue

                response = orion.route(user_input)
                # print(response) # Optional debug

            except KeyboardInterrupt:
                print("\n🛑 ORION shutting down safely")
                break
