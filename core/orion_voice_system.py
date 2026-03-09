import os
import sys
import json
import sounddevice as sd
import queue
import subprocess
import threading
import time
import numpy as np
from tts import OrionTTS

VOSK_AVAILABLE = False
try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

class OrionVoiceSystem:
    """
    Unified Voice Manager for ORION
    -------------------------------
    HYBRID ARCHITECTURE
    1. Wake Word: Vosk (CPU, Efficient)
    2. STT: NeMo Parakeet (1.1B) (GPU, High Accuracy)
    3. TTS: NeMo FastPitch (GPU/CPU)
    """

    def __init__(self, wake_word="orion", socketio=None):
        print("[ORION VOICE] Initializing Hybrid Voice System (Vosk + NeMo)...")

        self.socketio = socketio # [NEW] Real-time events
        self.wake_word = wake_word.lower()
        self.rate = 16000
        self.torch = None
        self.nemo_asr = None
        self.audio_mutex = threading.Lock()

        # 0. Wake Word (Vosk)
        self.vosk_model = None
        if VOSK_AVAILABLE:
            orion_root = os.environ.get('ORION_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_path = os.path.join(orion_root, "models", "vosk-model-en-us-0.22-lgraph")
            if os.path.exists(model_path):
                try:
                    self.vosk_model = vosk.Model(model_path)
                    print("✅ Vosk Wake Word Model Loaded")
                except Exception as e:
                    print(f"⚠️ Vosk Error: {e}")
            else:
                print(f"⚠️ Vosk model missing at {model_path}")

        # 1. STT (NeMo disabled for portable mode due to compiler limitations)
        self.stt_ok = False
        self.asr = None

        # 2. TTS (NeMo)
        try:
            self.tts = OrionTTS(socketio=self.socketio)
            if self.tts.ok:
                self.tts_ok = True
            else:
                self.tts_ok = False
        except Exception as e:
            print(f"⚠️ NeMo TTS Failed: {e}")
            self.tts_ok = False

    def listen_for_wake_word(self, is_active_cb=None):
        """
        Continuous listening loop using 'arecord' piped to Vosk.
        Blocks until wake word is detected, but checks is_active_cb if provided.
        """
        if not self.vosk_model:
            print("❌ Vosk Model missing. Cannot listen for wake word.")
            return False

        rec = vosk.KaldiRecognizer(self.vosk_model, self.rate, '["orion", "[unk]"]')

        print(f"🟢 [LISTENING] Vosk Active. Say '{self.wake_word}'...")
        # self._emit_status('user', 'idle') # Listening                        # Use robust native Python sounddevice to prevent libvosk segment faults
        import sounddevice as sd
        import queue

        # Increase queue size and drop old frames if NeMo blocks the thread too long
        q = queue.Queue(maxsize=100)

        def callback(indata, frames, time, status):
            if status:
                print(status, flush=True)
            try:
                q.put_nowait(bytes(indata))
            except queue.Full:
                pass # Drop frame gracefully rather than locking ALSA

        stream = None
        while stream is None:
            try:
                self.audio_mutex.acquire()
                stream = sd.RawInputStream(samplerate=self.rate, blocksize=2048, device=None, dtype='int16', channels=1, callback=callback)
            except Exception as e:
                self.audio_mutex.release()
                print(f"⚠️ Audio device contention: {e}. Retrying in 0.5s...")
                time.sleep(0.5)

        try:
            # Drop blocksize to decrease latency buffer lock
            with stream:
                while True:
                    # [BUG FIX] Check if we should still be listening
                    if is_active_cb and not is_active_cb():
                        return False

                    try:
                        # Use timeout so we can periodically check is_active_cb
                        data = q.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    # Yield slightly so we don't monopolize the GIL
                    time.sleep(0.005)

                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result())
                        text = res.get("text", "")
                        if self.wake_word in text.lower():
                            print(f"⚡ WAKE DETECTED: '{text}'")
                            self._emit_status('user', 'speaking')
                            return True
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Error in listen loop: {e}")
        finally:
            if self.audio_mutex.locked():
                self.audio_mutex.release()

    def _emit_status(self, source, state):
        if self.socketio:
            self.socketio.emit('voice_status', {'source': source, 'state': state})

    def listen_for_command(self, is_active_cb=None):
        """
        Listens for wake word, then records a command, then transcribes it.
        Returns the transcribed text.
        """
        if self.listen_for_wake_word(is_active_cb):
            audio = self.record_command()
            text = self.transcribe(audio)
            return text
        return ""

    def record_command(self, max_seconds=10, silence_threshold=0.015, silent_chunks=10):
        """Records command natively until silence is detected or max_seconds is reached"""
        print("🔴 [RECORDING COMMAND]...")
        self._emit_status('user', 'speaking')

        import sounddevice as sd
        import numpy as np
        import queue

        q = queue.Queue()
        def callback(indata, frames, time_info, status):
            if status:
                print(status, flush=True)
            q.put(indata.copy())

        recording = []
        silence_count = 0
        chunk_size = 1600 # 0.1 seconds at 16000Hz

        time.sleep(0.1) # Allow system audio lock to release before recording
        with self.audio_mutex:
            try:
                stream = sd.InputStream(samplerate=self.rate, channels=1, dtype='float32', blocksize=chunk_size, callback=callback)
                with stream:
                    for _ in range(int((max_seconds * self.rate) / chunk_size)):
                        try:
                            chunk = q.get(timeout=2.0)
                        except queue.Empty:
                            break

                        recording.append(chunk)

                        rms = np.sqrt(np.mean(chunk**2))
                        if rms < silence_threshold:
                            silence_count += 1
                        else:
                            silence_count = 0

                        if silence_count > silent_chunks: # ~1 second of silence
                            break
            except Exception as e:
                print(f"⚠️ Recording Error: {e}")

        time.sleep(0.1) # Small gap after recording before TTS can engage

        print("⏹️ [RECORDING COMPLETE]")
        self._emit_status('user', 'idle')

        if not recording:
            return np.zeros((1, 1), dtype='float32').flatten()
        return np.concatenate(recording).flatten()

    def transcribe(self, audio_signal):
        """Transcribes audio signal using Vosk (Portable Fallback)"""
        if getattr(self, "vosk_model", None) is None:
            print("⚠️ Vosk model not available. Cannot transcribe.")
            return ""

        import vosk
        import json
        import numpy as np

        # Convert float32 [-1.0, 1.0] to int16 for Vosk
        audio_int16 = (audio_signal * 32767).astype(np.int16)

        rec = vosk.KaldiRecognizer(self.vosk_model, self.rate)

        # Process in chunks to prevent memory spikes
        chunk_size = 4000
        for i in range(0, len(audio_int16), chunk_size):
            chunk = audio_int16[i:i+chunk_size]
            rec.AcceptWaveform(chunk.tobytes())

        res = json.loads(rec.FinalResult())
        text = res.get("text", "")

        if text.strip():
            print(f"📝 STT: '{text}'")

        return text

    def speak(self, text):
        if self.tts_ok:
            self.tts.speak(text)
        else:
            print(f"[SILENT TTS]: {text}")
