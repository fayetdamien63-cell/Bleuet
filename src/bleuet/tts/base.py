"""Interface de synthèse vocale."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Speaker(ABC):
    @abstractmethod
    def speak(self, text: str) -> Path | None:
        """Synthétise et joue `text`. Retourne le wav produit s'il y en a un."""

    def synthesize_to_file(self, text: str, path: str | Path) -> Path:
        raise NotImplementedError
