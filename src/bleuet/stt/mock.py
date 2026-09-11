"""Transcripteur factice : permet de tester l'orchestrateur sans micro ni modèle."""

from __future__ import annotations

import numpy as np

from ..logging_setup import get_logger
from .base import Transcriber, Transcription

log = get_logger("bleuet.stt.mock")


class MockTranscriber(Transcriber):
    def __init__(self, text: str = "Quelle est la météo aujourd'hui ?"):
        self.text = text

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> Transcription:  # noqa: ARG002
        log.info("transcription simulée : %r", self.text)
        return Transcription(text=self.text, language="fr", duration=0.0)
