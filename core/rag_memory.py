# rag_memory.py
import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class OrionRAGMemory:
    """
    ORION RAG Memory – Phase 3.7
    Read-only knowledge retrieval (NO execution authority)
    """

    FILE = "rag_store.json"

    def __init__(self):
        try:
            print("[ORION RAG] Loading Embedding Model...")
            import os
            import torch
            # Memory and thread optimization for CPU embeddings
            os.environ["OMP_NUM_THREADS"] = "4"
            torch.set_num_threads(4)
            self.model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            self.offline_mode = False
            print("✅ RAG Model Loaded (CPU)")
        except Exception as e:
            print(f"⚠️ RAG Model Load Failed (Network/Timeout): {e}")
            print("⚠️ Running in OFFLINE MODE (RAG Disabled)")
            self.model = None
            self.offline_mode = True

        self.docs = []
        self._load()

    def _load(self):
        if os.path.exists(self.FILE):
            with open(self.FILE, "r", encoding="utf-8") as f:
                self.docs = json.load(f)
        else:
            self.docs = []

    def _save(self):
        with open(self.FILE, "w", encoding="utf-8") as f:
            json.dump(self.docs, f, indent=2)

    def add_document(self, text: str, source="manual", metadata=None):
        if self.offline_mode:
            return {"status": "ERROR", "content": "RAG is Offline"}

        embedding = self.model.encode(text).tolist()
        record = {
            "text": text,
            "source": source,
            "embedding": embedding,
            "metadata": metadata or {}
        }
        self.docs.append(record)
        self._save()
        return {"status": "ADDED", "count": len(self.docs)}

    def retrieve(self, query: str, top_k=3):
        if self.offline_mode:
            return []

        if not self.docs:
            return []

        q_emb = self.model.encode(query).reshape(1, -1)
        doc_embs = np.array([d["embedding"] for d in self.docs])

        scores = cosine_similarity(q_emb, doc_embs)[0]
        ranked = sorted(
            zip(scores, self.docs),
            key=lambda x: x[0],
            reverse=True
        )

        return [
            {
                "score": float(score),
                "text": doc["text"],
                "source": doc["source"]
            }
            for score, doc in ranked[:top_k]
        ]
