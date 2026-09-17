# memory.py
import json
import os
import threading
from datetime import datetime
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class OrionMemory:
    """
    ORION Memory v3.1 (HARDENED)
    Deterministic + Semantic + File Cognition

    HARD GUARANTEES:
    - Never crashes on bad input
    - Semantic memory accepts TEXT ONLY
    - Thread-safe
    - Atomic persistence
    """

    orion_root = os.environ.get('ORION_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    FILE = os.path.join(orion_root, "brain", "memory.json")
    TMP_FILE = "memory.json.tmp"

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.memories = []
        self._lock = threading.RLock()
        self._load()

    # -------------------------
    # Normalization
    # -------------------------
    def _normalize_key(self, key: str) -> str:
        return key.strip().lower().replace(" ", "_")

    # -------------------------
    # Safe Value Coercion (CRITICAL)
    # -------------------------
    def _coerce_to_text(self, value: Any) -> str:
        """
        Ensures semantic memory ONLY receives text.
        This function must NEVER throw.
        """
        try:
            if value is None:
                return ""

            if isinstance(value, str):
                return value

            if isinstance(value, (int, float, bool)):
                return str(value)

            # dict / list / complex objects
            return json.dumps(value, ensure_ascii=False)

        except Exception:
            # absolute last resort
            return str(value)

    # -------------------------
    # Persistence (ATOMIC)
    # -------------------------
    def _load(self):
        if not os.path.exists(self.FILE):
            self.memories = []
            return

        try:
            with open(self.FILE, "r", encoding="utf-8") as f:
                self.memories = json.load(f)
        except Exception:
            # Corrupt file fallback (do NOT crash)
            self.memories = []

    def _save(self):
        """
        Atomic write to prevent corruption.
        """
        with open(self.TMP_FILE, "w", encoding="utf-8") as f:
            json.dump(self.memories, f, indent=2)

        os.replace(self.TMP_FILE, self.FILE)

    # =========================================================
    # FACT MEMORY (SEMANTIC, GUARDED)
    # =========================================================
    def add(self, key: str, value: Any, mtype="FACT"):
        key = self._normalize_key(key)

        text = self._coerce_to_text(value)

        with self._lock:
            try:
                embedding = self.model.encode(text).tolist()
            except Exception:
                # embedding failure must NEVER crash system
                embedding = []

            # overwrite existing FACT with same key
            self.memories = [
                m for m in self.memories
                if not (m["type"] == "FACT" and self._normalize_key(m["key"]) == key)
            ]

            record = {
                "type": "FACT",
                "key": key,
                "value": text,
                "timestamp": datetime.utcnow().isoformat(),
                "embedding": embedding
            }

            self.memories.append(record)
            self._save()

        return {"status": "STORED"}

    def get_by_key(self, key: str):
        key = self._normalize_key(key)

        with self._lock:
            for m in reversed(self.memories):
                if m["type"] == "FACT" and self._normalize_key(m["key"]) == key:
                    return m
        return None

    def get_all_by_type(self, mtype: str, limit: int = 20):
        """
        Retrieves recent memories of a specific type (e.g., USER_PREF).
        """
        with self._lock:
            # Filter matches
            matches = [m for m in self.memories if m["type"] == mtype]
            # Return most recent first
            return sorted(matches, key=lambda x: x["timestamp"], reverse=True)[:limit]

    # =========================================================
    # FILE MEMORY (DETERMINISTIC, NON-SEMANTIC)
    # =========================================================
    def store_file(self, path: str, metadata: dict, checksum: str, summary: str):
        with self._lock:
            self.memories = [
                m for m in self.memories
                if not (m["type"] == "FILE" and m["path"] == path)
            ]

            record = {
                "type": "FILE",
                "path": path,
                "metadata": metadata,
                "checksum": checksum,
                "summary": summary,
                "history": [],
                "timestamp": datetime.utcnow().isoformat()
            }

            self.memories.append(record)
            self._save()

    def get_file(self, path: str):
        with self._lock:
            for m in reversed(self.memories):
                if m["type"] == "FILE" and m["path"] == path:
                    return m
        return None

    def update_file_history(self, path: str, action: str, details=None):
        with self._lock:
            record = self.get_file(path)
            if not record:
                return

            record["history"].append({
                "action": action,
                "details": details,
                "timestamp": datetime.utcnow().isoformat()
            })

            self._save()

    # =========================================================
    # SEMANTIC SEARCH (FACTS ONLY)
    # =========================================================
    def search(self, query: str, threshold=0.65):
        with self._lock:
            facts = [m for m in self.memories if m["type"] == "FACT"]

        if not facts:
            return None

        try:
            q_emb = self.model.encode(query).reshape(1, -1)
        except Exception:
            return None

        mem_embs = np.array([m["embedding"] for m in facts if m["embedding"]])

        if len(mem_embs) == 0:
            return None

        sims = cosine_similarity(q_emb, mem_embs)[0]
        idx = int(np.argmax(sims))

        if sims[idx] >= threshold:
            return facts[idx]

        return None

    # =========================================================
    # PENDING ACTION (ORCHESTRATOR SUPPORT)
    # =========================================================
    def set_pending_action(self, action: dict):
        with self._lock:
            self.pending_action = action

    def get_pending_action(self):
        return getattr(self, "pending_action", None)

    def clear_pending_action(self):
        with self._lock:
            if hasattr(self, "pending_action"):
                del self.pending_action

    # =========================================================
    # PLAN CACHING (SEMANTIC ACTIONS)
    # =========================================================
    def store_successful_plan(self, goal, steps):
        """
        Stores a proven plan (list of steps) for a goal.
        """
        with self._lock:
            try:
                embedding = self.model.encode(goal).tolist()
            except Exception:
                embedding = []

            record = {
                "type": "PROVEN_PLAN",
                "goal": goal,
                "steps": steps,
                "timestamp": datetime.utcnow().isoformat(),
                "embedding": embedding
            }

            # Prevent Memory and VRAM Leak from runaway caching of duplicate steps/goals
            MAX_PLANS = 100
            plans = [m for m in self.memories if m["type"] == "PROVEN_PLAN"]
            if len(plans) > MAX_PLANS:
                self.memories.remove(plans[0])

            self.memories.append(record)
            self._save()
            print(f"[MEMORY] 🧠 Cached successful plan for: '{goal}'")

    def retrieve_plan(self, goal, threshold=0.85):
        """
        Retrieves a proven plan if the goal is semantically similar.
        """
        try:
            q_emb = self.model.encode(goal).reshape(1, -1)
        except Exception:
            return None

        with self._lock:
            plans = [m for m in self.memories if m["type"] == "PROVEN_PLAN" and m.get("embedding")]

        if not plans:
            return None

        plan_embs = np.array([m["embedding"] for m in plans])
        sims = cosine_similarity(q_emb, plan_embs)[0]
        idx = int(np.argmax(sims))

        if sims[idx] >= threshold:
            print(f"[MEMORY] ⚡ Found cached plan (Confidence: {sims[idx]:.2f})")
            return plans[idx]["steps"]

        return None

    # =========================================================
    # EPISODIC MEMORY (PHASE 13)
    # =========================================================
    def add_episode(self, user_text: str, agent_text: str):
        """
        Logs a conversation exchange.
        """
        # Normalize
        user_text = self._coerce_to_text(user_text)
        agent_text = self._coerce_to_text(agent_text)

        # Create embedding for the USER input (to find similar past queries)
        try:
            embedding = self.model.encode(user_text).tolist()
        except Exception:
            embedding = []

        with self._lock:
            record = {
                "type": "EPISODE",
                "user": user_text,
                "agent": agent_text,
                "timestamp": datetime.utcnow().isoformat(),
                "embedding": embedding
            }
            self.memories.append(record)

            # Prevent memory and JSON leaks by dumping stale episodic nodes
            MAX_EPISODES = 500
            episodes = [m for m in self.memories if m["type"] == "EPISODE"]

            if len(episodes) > MAX_EPISODES:
                # Remove oldest episode (Assuming sorted inherently by append)
                self.memories.remove(episodes[0])

            self._save()

    def get_recent_episodes(self, limit=5):
        """
        Returns the last N interactions for immediate context.
        """
        with self._lock:
            episodes = [m for m in reversed(self.memories) if m["type"] == "EPISODE"]
            return episodes[:limit]

    def optimize_storage(self):
        """
        Self-cleaning garbage collection to ensure fast semantic lookups
        and manage JSON bloat (Cache efficiently managed).
        """
        initial_count = len(self.memories)
        with self._lock:
            # 1. Truncate old Episodes (Keep last 200 for deep context, delete the rest)
            episodes = [m for m in self.memories if m["type"] == "EPISODE"]
            if len(episodes) > 200:
                to_remove = episodes[:-200]
                for r in to_remove:
                    self.memories.remove(r)

            # 2. Truncate File Histories (Keep last 5 actions per file)
            for m in self.memories:
                if m["type"] == "FILE" and len(m.get("history", [])) > 5:
                    m["history"] = m["history"][-5:]

            # 3. Truncate Proven Plans (Keep last 50 highly relevant plans)
            plans = [m for m in self.memories if m["type"] == "PROVEN_PLAN"]
            if len(plans) > 50:
                to_remove = plans[:-50]
                for r in to_remove:
                    self.memories.remove(r)

            self._save()

        final_count = len(self.memories)
        print(f"[MEMORY] 🧹 Cache Optimised. Space efficiently managed (Δ {initial_count - final_count} records).")

    def search_episodes(self, query: str, limit=3, threshold=0.4):
        """
        Finds relevant past conversations.
        """
        with self._lock:
            episodes = [m for m in self.memories if m["type"] == "EPISODE" and m.get("embedding")]

        if not episodes:
            return []

        try:
            q_emb = self.model.encode(query).reshape(1, -1)
            mem_embs = np.array([m["embedding"] for m in episodes])
            sims = cosine_similarity(q_emb, mem_embs)[0]
        except Exception:
            return []

        # Get top indices
        indices = np.argsort(sims)[::-1][:limit]
        results = []

        for i in indices:
            if sims[i] >= threshold:
                results.append(episodes[i])

        return results
