
# tts.py
import os
import sys
import queue
import sounddevice as sd
# import soundfile as sf
# import torch
# from nemo.collections.tts.models import FastPitchModel, HifiGanModel
import subprocess


class OrionTTS:
    """
    NeMo-based TTS (FastPitch + HifiGan).
    """

    def __init__(self, socketio=None):
        os.environ["NEMO_LOG_LEVEL"] = "ERROR"
        self.ok = False
        self.socketio = socketio # [NEW] Real-time events

        print("🔊 Loading NeMo TTS Modules (Lazy Load)...")

        self.ok = False
        self.engine = None

        try:
            import pyttsx3
            # Initialize the Windows offline TTS engine
            self.engine = pyttsx3.init()

            # Configure voice properties
            self.engine.setProperty('rate', 175)    # Speed
            self.engine.setProperty('volume', 1.0)  # Volume 0-1

            # Try to find a good English voice
            voices = self.engine.getProperty('voices')
            for voice in voices:
                if "Zira" in voice.name or "Hazel" in voice.name or "Female" in voice.name:
                    self.engine.setProperty('voice', voice.id)
                    break

            self.ok = True
            print("✅ pyttsx3 Offline TTS ready")

        except Exception as e:
            print(f"⚠️ pyttsx3 TTS Failed: {e}")
            self.ok = False

    def _warmup(self):
        import numpy as np
        print("   → Warming up TTS models to reduce first-time latency...")
        try:
            with self.torch.inference_mode():
                # Run a dummy forward pass to initialize PyTorch JIT and memory caches
                tokens = self.fastpitch.parse("System online.")
                spec = self.fastpitch.generate_spectrogram(tokens=tokens)
                _ = self.hifigan.convert_spectrogram_to_audio(spec=spec)
        except Exception as e:
            print(f"⚠️ Warmup failed: {e}")

    # --------------------------------------------------
    def speak(self, text: str, lock_mic=None, unlock_mic=None):
        if not self.ok or not text.strip():
            return

        if lock_mic:
            lock_mic()

        try:
            if self.socketio:
                self.socketio.emit('voice_status', {'source': 'orion', 'state': 'speaking'})

            print(f"🔊 ORION: {text}")
            self.engine.say(text)
            self.engine.runAndWait()

            if self.socketio:
                self.socketio.emit('voice_status', {'source': 'orion', 'state': 'idle'})

        except Exception as e:
            print(f"⚠️ TTS Playback Error: {e}")
        finally:
            if unlock_mic:
                unlock_mic()
