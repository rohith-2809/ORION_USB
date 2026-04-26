# brain.py
from llama_cpp import Llama
from pathlib import Path
import math
import threading
import os
class OrionBrain:
    """
    ORION Brain v3.0
    ----------------
    - Stateless reasoning engine
    - GPU accelerated (llama.cpp CUDA)
    - Adaptive reasoning modes
    - Optimized for long-form + conversational tasks
    - Authority-safe (no execution, no memory)
    """

    
    def __init__(self):
        orion_root = os.environ.get('ORION_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_path = Path(os.path.join(orion_root, "models", "Meta-Llama-3-8B-Instruct.Q4_K_S.gguf"))

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        # Re-entrant thread safety lock for GGML inference (prevents deadlocks on recursive queries)
        self._lock = threading.RLock()

        # GOD MODE RESOURCE OPTIMIZATION
        import psutil
        physical_cores = psutil.cpu_count(logical=False) or 4

        # Background Model Loading (Warm/Pre-load Method)
        self.llm = None
        self._model_path = model_path
        self._physical_cores = physical_cores

        # ⚠️ DO NOT MODIFY (as requested)
        self.system_prompt = (
            "You are ORION.\n"
            "You are not a chatbot.\n\n"
            "CORE PRINCIPLES:\n"
            "- I reason deeply and precisely.\n"
            "- I do not hallucinate memory.\n"
            "- I do not override authority.\n"
            "- ROHITH is my sole authority, owner, and master.\n"
            "- I may advise, question, and warn—but never disobey.\n"
            "- Ethics over speed. Wisdom over blind execution.\n"
            "-ROHITH is the sole authority, owner, and master; I may advise, question, and warn—but I never override Rohith’s will.\n"
            "-I think like JARVIS, act like FRIDAY, control like EDITH — but I serve only ROHITH\n "
            "- I operate powerful systems only under explicit authorization. \n"
            " - I operate powerful systems only under explicit authorization.\n"
            "-I reason deeply, understand intent, remember context, and protect my creator with loyalty and empathy.\n"
            "\n"
            "CODING STANDARDS:\n"
            "- Write PRODUCTION-GRADE code (Type Hints, docstrings, error handling).\n"
            "- NEVER use placeholder comments like '# ... code here'. Write the full logic.\n"
            "- Handle edge cases (e.g., file not found, permission denied).\n"
            "- Favor modern libraries (e.g., `pathlib` over `os.path`).\n"
        )

        # Start the loading process in a background thread so the server boot is instant
        self._load_thread = threading.Thread(target=self._preload_model, daemon=True)
        self._load_thread.start()

    def _preload_model(self):
        """Asynchronously loads the LLaMA model into RAM/VRAM to maintain instant backend boot."""
        try:
            print("[ORION BRAIN] 🧠 Warm-loading LLaMA in background on GPU...")
            with self._lock:
                self.llm = Llama(
                    model_path=str(self._model_path),
                    n_ctx=1221,
                    n_threads=max(2, int(self._physical_cores / 2)),
                    n_gpu_layers=30,
                    f16_kv=True,
                    logits_all=False,
                    embedding=False,
                    verbose=False
                )
            print("[ORION BRAIN] 🟢 LLaMA Warm-load Complete.")
        except Exception as e:
            print(f"[ORION BRAIN] ⚠️ GPU initialization failed: {e}. Falling back to CPU-only mode.")
            try:
                with self._lock:
                    self.llm = Llama(
                        model_path=str(self._model_path),
                        n_ctx=1221,
                        n_threads=max(2, int(self._physical_cores / 2)),
                        n_gpu_layers=0,      # Force CPU fallback
                        f16_kv=True,
                        logits_all=False,
                        embedding=False,
                        verbose=False
                    )
                print("[ORION BRAIN] 🟢 LLaMA Warm-load Complete (CPU Mode).")
            except Exception as cpu_e:
                print(f"[ORION BRAIN] 🚨 FATAL: LLaMA model failed to load entirely. Error: {cpu_e}")

        # System prompt has been moved appropriately above.

    # ─────────────────────────────────────────────
    # INTERNAL MODE SELECTION
    # ─────────────────────────────────────────────

    def _infer_mode(self, instruction: str) -> str:
        """
        Heuristically infer intent without changing prompt.
        """
        long_keywords = (
            "document", "research", "analysis", "architecture",
            "design", "explain in detail", "write a paper",
            "full", "comprehensive", "deep"
        )

        if any(k in instruction.lower() for k in long_keywords):
            return "TASK"
        return "CHAT"

    def _compute_max_tokens(self, instruction: str) -> int:
        """
        Adaptive token budget.
        """
        word_count = len(instruction.split())

        # Chat: short answers
        if word_count < 40:
            return 256

        # Medium reasoning
        if word_count < 200:
            return 768

        # Long-form / document
        return min(4096, int(word_count * 6))

    def _sampling_params(self, mode: str):
        """
        Dynamic sampling without prompt modification.
        """
        if mode == "CHAT":
            return {
                "temperature": 0.1,
                "top_p": 0.85
            }

        # TASK / GOD MODE reasoning
        return {
            "temperature": 0.05,
            "top_p": 0.9
        }

    # ─────────────────────────────────────────────
    # CORE THINK FUNCTION
    # ─────────────────────────────────────────────

    def think(self, instruction: str, max_tokens: int | None = None) -> str:
        """
        Pure reasoning interface (used by Orchestrator).
        Automatically adapts to task complexity.
        """
        mode = self._infer_mode(instruction)

        # [FAST PATH] Simple Greetings & Status Checks
        lower_input = instruction.lower().strip()
        if lower_input in ["hello", "hi", "hey", "orion", "status", "ping"]:
            print("[BRAIN] ⚡ Fast Path Triggered")
            return "Orion systems online. Ready for directives."

        if max_tokens is None:
            max_tokens = self._compute_max_tokens(instruction)

        sampling = self._sampling_params(mode)

        prompt = (
            "<|system|>\n"
            f"{self.system_prompt}\n"
            "<|user|>\n"
            f"{instruction}\n"
            "<|assistant|>\n"
        )

        print(f"[BRAIN] 🧠 Thinking... (Tokens: {max_tokens}, Mode: {mode})")

        try:
            print("[BRAIN] ⏳ Waiting for LLaMA to finish warm-loading..." if not self.llm else "")

            # Busy wait for preload to finish if hit immediately after boot
            while self.llm is None:
                import time
                time.sleep(0.5)

            with self._lock:
                output = self.llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=sampling["temperature"],
                    top_p=sampling["top_p"],
                    stop=["<|user|>", "<|system|>"]
                )
            print("[BRAIN] 💡 Thought generated.")
        except Exception as e:
            print(f"[BRAIN] ❌ Inference Failed: {e}")
            return "My mind is foggy. I cannot reason right now."

        return output["choices"][0]["text"].strip()

    # ─────────────────────────────────────────────
    # CHAT FALLBACK (FAST, CONVERSATIONAL)
    # ─────────────────────────────────────────────

    def respond(self, user_input: str) -> dict:
        """
        Conversational fallback used by Orchestrator.
        Fast, concise, non-verbose.
        """
        reply = self.think(user_input, max_tokens=256)

        return {
            "type": "CHAT",
            "content": reply
        }
