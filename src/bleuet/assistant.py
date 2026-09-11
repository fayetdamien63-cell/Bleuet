"""Boucle complète : wake word -> enregistrement -> STT -> Claude -> TTS."""

from __future__ import annotations

import time

from .audio.capture import AudioConfig, record_until_silence, stream_chunks
from .config import Config
from .logging_setup import get_logger
from .orchestrator.pipeline import Orchestrator
from .stt.factory import build_transcriber
from .tts.factory import build_speaker
from .wakeword.detector import WakeWordConfig, WakeWordDetector

log = get_logger("bleuet.assistant")


class Assistant:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.audio = AudioConfig.from_config(cfg)
        self.detector = WakeWordDetector(WakeWordConfig.from_config(cfg), self.audio.sample_rate)
        self.transcriber = build_transcriber(cfg)
        self.orchestrator = Orchestrator(cfg)
        self.speaker = build_speaker(cfg)

    def warmup(self) -> None:
        """Charge les modèles avant la première question (sinon le premier
        « Dis Bleuet » attend 10 s le chargement de Whisper)."""
        log.info("préchauffage des modèles…")
        self.transcriber.warmup()
        log.info("prêt.")

    def handle_utterance(self) -> str | None:
        """Une interaction : enregistre, transcrit, interroge Claude, parle."""
        samples = record_until_silence(self.audio)
        transcription = self.transcriber.transcribe(samples, self.audio.sample_rate)
        if not transcription.text:
            log.warning("rien de transcrit, on retourne à l'écoute")
            return None
        answer = self.orchestrator.answer(transcription.text)
        self.speaker.speak(answer.text)
        return answer.text

    def run(self) -> None:
        self.warmup()
        log.info("Bleuet est à l'écoute. Ctrl+C pour arrêter.")
        for block in stream_chunks(self.audio):
            if self.detector.process_block(block) is None:
                continue
            try:
                self.handle_utterance()
            except Exception:  # une question ratée ne doit pas tuer la boucle
                log.exception("échec du traitement de la question")
                try:
                    self.speaker.speak("Désolé, je n'ai pas réussi à répondre.")
                except Exception:
                    log.exception("échec du message d'erreur vocal")
            # Laisse retomber l'écho de notre propre réponse avant de réécouter.
            time.sleep(0.3)
