"""Interface de transcription : une seule méthode, pour pouvoir déplacer le STT
sur un serveur séparé sans toucher à l'orchestrateur."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class Transcription:
    text: str
    language: str | None = None
    duration: float | None = None


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> Transcription:
        """Transcrit un tableau float32 mono."""

    def warmup(self) -> None:
        """Pré-charge le modèle (évite de payer le chargement au 1er wake word)."""
