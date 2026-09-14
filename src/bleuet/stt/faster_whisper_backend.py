"""Transcription locale avec faster-whisper (CTranslate2, CPU, hors-ligne)."""

from __future__ import annotations

import time

import numpy as np

from ..logging_setup import get_logger
from .base import Transcriber, Transcription

log = get_logger("bleuet.stt.faster_whisper")


class FasterWhisperTranscriber(Transcriber):
    def __init__(
        self,
        model: str = "small",
        language: str = "fr",
        compute_type: str = "int8",
        beam_size: int = 1,
        device: str = "auto",
    ):
        self.model_name = model
        self.language = language
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.device = device
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper n'est pas installé : `pip install -e '.[stt]'`"
            ) from exc
        started = time.monotonic()
        log.info("chargement du modèle Whisper « %s » (%s)…", self.model_name, self.compute_type)
        self._model = WhisperModel(
            self.model_name, device=self.device, compute_type=self.compute_type
        )
        log.info("modèle chargé en %.1f s", time.monotonic() - started)
        return self._model

    def warmup(self) -> None:
        self._load()

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> Transcription:
        if sample_rate != 16000:
            raise ValueError("faster-whisper attend du 16 kHz")
        model = self._load()
        started = time.monotonic()
        segments, info = model.transcribe(
            samples,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        elapsed = time.monotonic() - started
        log.info("transcription en %.1f s : %r", elapsed, text)
        return Transcription(text=text, language=info.language, duration=elapsed)
