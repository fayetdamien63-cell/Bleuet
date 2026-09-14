"""Détection du mot de réveil via openWakeWord (ONNX, tourne sur ARM)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from ..config import PROJECT_ROOT
from ..logging_setup import get_logger

log = get_logger("bleuet.wakeword")


@dataclass
class WakeWordConfig:
    enabled: bool = True
    model_path: str | None = None
    pretrained_model: str = "hey_jarvis"
    threshold: float = 0.5
    cooldown: float = 2.0
    vad_threshold: float = 0.0

    @classmethod
    def from_config(cls, cfg) -> "WakeWordConfig":
        section = cfg.section("wakeword")
        known = {f: section[f] for f in cls.__dataclass_fields__ if f in section}
        return cls(**known)


class WakeWordDetector:
    """Enveloppe fine autour de openwakeword.Model.

    Accepte indifféremment un modèle pré-entraîné (`hey_jarvis`) ou un `.onnx`
    entraîné maison (« Dis Bleuet ») — c'est le même appel, seul le chemin change.
    """

    def __init__(self, config: WakeWordConfig, sample_rate: int = 16000):
        self.config = config
        self.sample_rate = sample_rate
        self._model = None
        self._blocks_since_trigger = 0
        self._cooldown_blocks = int(config.cooldown / 0.08)  # blocs de 80 ms

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openwakeword n'est pas installé : `pip install -e '.[wakeword]'`"
            ) from exc

        kwargs: dict = {"inference_framework": "onnx"}
        if self.config.vad_threshold:
            kwargs["vad_threshold"] = self.config.vad_threshold

        if self.config.model_path:
            path = Path(self.config.model_path)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if not path.exists():
                raise FileNotFoundError(
                    f"Modèle wake word introuvable : {path}. "
                    "Voir docs/wakeword.md pour entraîner « Dis Bleuet »."
                )
            kwargs["wakeword_models"] = [str(path)]
            log.info("modèle wake word custom : %s", path.name)
        else:
            kwargs["wakeword_models"] = [self.config.pretrained_model]
            log.info("modèle wake word pré-entraîné : %s", self.config.pretrained_model)

        self._model = Model(**kwargs)
        return self._model

    def process_block(self, block: np.ndarray) -> tuple[str, float] | None:
        """Passe un bloc int16 au modèle. Retourne (nom, score) si déclenché."""
        model = self._load()
        scores = model.predict(block)

        if self._blocks_since_trigger > 0:
            self._blocks_since_trigger -= 1
            return None

        for name, score in scores.items():
            if score >= self.config.threshold:
                self._blocks_since_trigger = self._cooldown_blocks
                model.reset()
                log.info("MOT DE RÉVEIL détecté : %s (score %.3f)", name, score)
                return name, float(score)
        return None

    def listen(
        self,
        chunks: Iterable[np.ndarray],
        on_detect: Callable[[str, float], None] | None = None,
    ) -> None:
        """Boucle bloquante : consomme le flux micro et appelle `on_detect`."""
        log.info("écoute du mot de réveil (seuil %.2f)…", self.config.threshold)
        for block in chunks:
            hit = self.process_block(block)
            if hit and on_detect:
                on_detect(*hit)


def download_pretrained_models() -> None:
    """Télécharge les modèles openWakeWord (à faire une fois, avec le réseau)."""
    import openwakeword

    openwakeword.utils.download_models()
    log.info("modèles openWakeWord téléchargés")
