# intent_classifier.py
import re


class IntentClassifier:
    """
    ORION Intent Classifier – Phase 3.3 (STABLE)

    Responsibilities:
    - Detect intent ONLY (no execution)
    - Normalize memory keys deterministically
    - Declare file intents (list, read, edit, delete)
    - Support confirmation / rejection gating
    - Support action ledger read
    """

    # ================= NORMALIZATION =================
    def _normalize_key(self, key: str) -> str:
        return (
            key.strip()
            .lower()
            .replace("?", "")
            .replace(" ", "_")
        )

    # ================= SELF-REFERENCE RESOLUTION =================
    def _resolve_self_reference(self, text: str):
        """
        Maps self-referential phrases to actual file paths.
        Intent resolution only — NO execution.
        """
        if "orchestrator" in text:
            return "orchestrator.py"
        if "intent classifier" in text:
            return "intent_classifier.py"
        if "memory" in text:
            return "memory.py"
        return None

    # ================= CLASSIFY =================
    def classify(self, text: str) -> dict:
        raw = text.strip()
        t = raw.lower().strip()

        # ================= ACTION LOG (NO FILTER) =================
        if re.fullmatch(r"(show|list|read)\s+action\s+log", t):
            return {"intent": "ACTION_LOG"}

        # ================= ACTION LOG (WITH FILTER) =================
        m = re.match(r"(show|list|read)\s+action\s+log\s+(.+)", t)
        if m:
            return {
                "intent": "ACTION_LOG_FILTER",
                "query": m.group(2).strip()
            }

        # ================= REFLECTION =================
        if re.search(r"\b(reflect|self reflect|analyze behavior|reflect on)\b", t):
            return {"intent": "REFLECTION"}

        # ================= MEMORY STORE =================
        m = re.match(r"my\s+(.+?)\s+is\s+(.+)", t)
        if m:
            return {
                "intent": "MEMORY_STORE",
                "key": self._normalize_key(m.group(1)),
                "value": m.group(2).strip()
            }

        # ================= MEMORY QUERY =================
        m = re.match(r"what\s+is\s+my\s+(.+)", t)
        if m:
            return {
                "intent": "MEMORY_QUERY",
                "key": self._normalize_key(m.group(1))
            }

        # ================= FILE LIST =================
        if re.search(r"\b(list|show)\b.*\b(files|directory|folder)\b", t):
            return {"intent": "FILE_LIST"}

        # ================= DOCUMENT CREATE (KEYWORD FALLBACK) =================
        # Simplest possible logic: "create" + "document" = INTENT
        is_create = any(w in t for w in ["create", "generate", "write", "draft", "make"])
        is_doc = any(w in t for w in ["document", "report", "paper", "article", "guide", "manual", "presentation", "ppt", "summary", "brief", "overview"])

        if is_create and is_doc:
            # 1. Extract Format
            fmt = "md"
            mode = "standard"

            # Format Detection
            if "docx" in t: fmt = "docx"
            elif "pdf" in t: fmt = "pdf"
            elif any(k in t for k in ["ppt", "pptx", "slide", "deck", "presentation"]):
                fmt = "pptx"
            elif "md" in t: fmt = "md"

            # Mode Detection
            if any(k in t for k in ["deep", "detail", "comprehensive", "long", "full"]):
                mode = "deep"
            elif any(k in t for k in ["brief", "short", "simple", "summary"]):
                mode = "brief"

            # Extract Topic
            doc_kw = "document"
            for k in ["documentation", "document", "presentation", "report", "paper", "analysis", "slide deck", "slides", "summary", "brief", "overview"]:
                if k in t:
                    doc_kw = k
                    break

            # Split by that keyword
            parts = t.split(doc_kw, 1)
            topic_raw = parts[1].strip() if len(parts) > 1 else ""

            # Clean up "about", "on", "in docx", "deeply"
            topic = re.sub(r"^(of|about|on|covering|titled|regarding)\b\s*", "", topic_raw).strip()
            topic = re.sub(r"\b(in|format|as)\s+(docx|doc|pdf|txt|md|ppt|pptx)\b.*", "", topic).strip()

            # Clean mode words from topic
            topic = re.sub(r"\b(deep|detailed|brief|short|comprehensive)\b", "", topic, flags=re.IGNORECASE).strip()

            # Remove parenthetical instructions often pasted by users
            # e.g. "Topic (Triggers: Format=PPTX...)"
            topic = re.sub(r"\(.*?\)", "", topic).strip()

            # Remove trailing format keywords
            for f in ["docx", "pdf", "txt", "md", "pptx", "ppt"]:
                if topic.endswith(f):
                    topic = topic[:-len(f)].strip()

            # Final cleanup of quotes/punctuation
            topic = topic.strip(' ".,')

            if not topic:
                topic = "ORION_DOCUMENT" # Default if no topic found

            # Extract Page Count (e.g., "10 pages", "5 page")
            pages = None
            page_match = re.search(r"(\d+)\s+pages?", t)
            if page_match:
                try:
                   pages = int(page_match.group(1))
                except:
                   pass

            return {
                "intent": "DOCUMENT_CREATE",
                "path": ".",
                "filename": topic.replace(" ", "_").upper(),
                "format": fmt,
                "mode": mode,
                "pages": pages, # New Field
                "topic": topic
            }


        # ================= AUTHORITY ENABLE (GOD MODE) =================
        m = re.match(
            r"(enable|activate|start)\s+god\s+mode"
            r"(\s+for\s+(\d+)\s+(seconds|minutes))?",
            t
        )
        if m:
            duration = 120  # default seconds

            if m.group(3):
                value = int(m.group(3))
                unit = m.group(4)
                duration = value * 60 if unit.startswith("minute") else value

            return {
                "intent": "AUTHORITY_ENABLE",
                "duration": duration
            }

        # ================= DOCUMENT RESUME =================
        if re.search(r"\b(resume|continue)\b.*\b(document|job|generation)\b", t):
            m = re.search(r"(resume|continue)\s+(.+)", t)
            job_id = None
            if m:
                 # Extract potential job ID if provided, otherwise generic resume
                 parts = m.group(2).split()
                 for p in parts:
                     if "doc_" in p:
                         job_id = p
                         break

            return {
                "intent": "DOCUMENT_RESUME",
                "job_id": job_id
            }

        # ================= FILE READ =================
        resolved = self._resolve_self_reference(t)
        if resolved and re.search(r"\b(read|open|show|inspect|look at)\b", t):
            return {
                "intent": "FILE_READ",
                "path": resolved
            }

        m = re.search(r"\b(read|open|show)\b\s+(.+)", t)
        if m:
            return {
                "intent": "FILE_READ",
                "path": m.group(2).replace("file ", "").strip()
            }

        # ================= FILE EDIT =================
        m = re.match(r"(edit|modify|change|update|refactor|fix)\s+(.+)", t)
        if m:
            return {
                "intent": "FILE_EDIT",
                "path": m.group(2).replace("file ", "").strip()
            }

        # ================= FILE DELETE =================
        m = re.match(r"(delete|remove)\s+(.+)", t)
        if m:
            return {
                "intent": "FILE_DELETE",
                "path": m.group(2).replace("file ", "").strip()
            }

        # =================        # 14. CODE GENERATION
        if re.search(r"\b(write|generate|create|code|script)\b.*\b(python|script|program|app|game|tool)\b", t):
            # Extract topic
            topic = raw
            for garbage in ["write a", "generate a", "create a", "code a", "python script for", "python program for"]:
                 topic = topic.replace(garbage, "").strip()

            return {
                "intent": "CODE_GEN",
                "topic": topic,
                "language": "python"
            }

        # Clean punctuation for exact word matches like "confirm." or "yes!"
        clean_t = re.sub(r'[^\w\s]', '', t).strip()

        # ================= CONFIRM =================
        if clean_t in ("confirm", "yes", "approve", "proceed", "y", "ok", "okay", "confrim", "kill it", "act", "do it", "execute"):
            return {"intent": "CONFIRM"}

        # ================= CANCEL =================
        if clean_t in ("cancel", "reject", "no"):
            return {"intent": "CANCEL"}

        # ================= RAG ADD =================
        m = re.match(r"(remember|add knowledge|add info|store knowledge)\s+(.+)", t)
        if m:
            return {
                "intent": "RAG_ADD",
                "text": m.group(2).strip()
            }

        # ================= RAG QUERY =================
        if re.search(r"\b(according to|based on|from knowledge|what do you know)\b", t):
            return {
                "intent": "RAG_QUERY",
                "query": raw
            }

        # ================= COMPLEX TASK (COGNITIVE LOOP) =================
        if re.search(r"\b(create and run|write and execute|make and run|build and start)\b", t):
             return {
                 "intent": "COMPLEX_TASK",
                 "goal": raw
             }

        # ================= PLANNING =================
        if re.search(r"\b(plan|how should i|what steps|strategy for)\b", t):
            return {
                "intent": "PLAN",
                "goal": raw
            }

        # ================= DEFENSE: KILL PROCESS =================
        m = re.match(r"(kill|terminate|stop|end)\s+(process|program|task)?\s*(.+)", t)
        if m:
            target = m.group(3).strip()
            # Extract PID if present
            pid_match = re.search(r"\b(\d{3,6})\b", target)
            if pid_match:
                return {"intent": "DEFENSE_KILL", "target": pid_match.group(1)}
            return {"intent": "DEFENSE_KILL", "target": target} # Name-based (might fail safely)

        # ================= DEFENSE: BLOCK IP =================
        m = re.match(r"(block|ban|denylist)\s+(ip|address|connection)?\s*(.+)", t)
        if m:
             # Basic IP extractions
             ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", t)
             if ip_match:
                 return {"intent": "DEFENSE_BLOCK", "target": ip_match.group(1)}

        # ================= MAINTENANCE: CLEAN =================
        if "clean" in t and ("system" in t or "junk" in t or "temp" in t):
             return {"intent": "MAINTENANCE_CLEAN"}

        # ================= MAINTENANCE: INTEGRITY =================
        if "integrity" in t or "sfc" in t or "fix system" in t or "repair system" in t:
             return {"intent": "MAINTENANCE_INTEGRITY"}

        # ================= MAINTENANCE: SCAN (Deep Scan) =================
        if "scan" in t and ("system" in t or "deep" in t or "malware" in t):
            return {"intent": "MAINTENANCE_SCAN"}

        # ================= DEFENSE: STATUS (Fallback) =================
        if "status" in t and ("defense" in t or "shield" in t):
             return {"intent": "DEFENSE_STATUS"}

        # ================= EXECUTE (EXPLICIT ONLY) =================
        if re.fullmatch(r"execute\s+file\s+list", t):
            return {
                "intent": "EXECUTE",
                "action": "FILE_LIST",
                "payload": {}
            }

        # ================= FALLBACK =================
        return {"intent": "CHAT"}
