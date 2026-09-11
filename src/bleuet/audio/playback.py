"""Lecture audio (réponse synthétisée)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..logging_setup import get_logger

log = get_logger("bleuet.audio.playback")


def play_array(samples: np.ndarray, sample_rate: int, output_device: int | None = None) -> None:
    import sounddevice as sd

    log.info("lecture de %.2f s d'audio", len(samples) / sample_rate)
    sd.play(samples, samplerate=sample_rate, device=output_device)
    sd.wait()


def play_wav(path: str | Path, output_device: int | None = None) -> None:
    import soundfile as sf

    samples, rate = sf.read(str(path), dtype="float32", always_2d=False)
    play_array(samples, rate, output_device)
