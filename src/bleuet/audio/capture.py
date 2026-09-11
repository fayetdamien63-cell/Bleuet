"""Capture micro : flux continu (wake word) et enregistrement à la demande (STT).

`sounddevice` + `numpy` uniquement : portable PC/Pi, aucune dépendance lourde.
Tout l'audio circule en float32 mono à 16 kHz, le format commun à
openWakeWord et à Whisper.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from ..logging_setup import get_logger

log = get_logger("bleuet.audio.capture")


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    input_device: int | None = None
    max_duration: float = 12.0
    silence_duration: float = 1.2
    min_duration: float = 0.8
    silence_threshold: float = 0.012

    @classmethod
    def from_config(cls, cfg) -> "AudioConfig":
        section = cfg.section("audio")
        known = {f: section[f] for f in cls.__dataclass_fields__ if f in section}
        return cls(**known)


def _import_sounddevice():
    try:
        import sounddevice as sd
    except OSError as exc:  # PortAudio absent (fréquent sur une image Linux nue)
        raise RuntimeError(
            "PortAudio introuvable. Linux : `sudo apt install libportaudio2`. "
            "macOS : `brew install portaudio`."
        ) from exc
    return sd


def list_devices() -> str:
    sd = _import_sounddevice()
    return str(sd.query_devices())


def stream_chunks(audio: AudioConfig, chunk_size: int = 1280) -> Iterator[np.ndarray]:
    """Itère indéfiniment sur des blocs int16 (1280 = 80 ms, attendu par openWakeWord)."""
    sd = _import_sounddevice()
    buffer: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames, time_info, status):  # noqa: ARG001
        if status:
            log.debug("statut du flux audio : %s", status)
        buffer.put(indata.copy().reshape(-1))

    with sd.InputStream(
        samplerate=audio.sample_rate,
        channels=audio.channels,
        dtype="int16",
        blocksize=chunk_size,
        device=audio.input_device,
        callback=callback,
    ):
        log.info("flux micro ouvert (%d Hz, blocs de %d échantillons)", audio.sample_rate, chunk_size)
        while True:
            yield buffer.get()


def record_until_silence(audio: AudioConfig) -> np.ndarray:
    """Enregistre jusqu'à `silence_duration` s de silence (ou `max_duration`).

    Retourne un tableau float32 dans [-1, 1]. Détection de silence par RMS :
    suffisant pour une pièce calme, et ~0 coût CPU — un vrai VAD (webrtcvad,
    silero) serait la première amélioration si la maison est bruyante.
    """
    sd = _import_sounddevice()
    frames_per_block = 1024
    block_duration = frames_per_block / audio.sample_rate
    silence_blocks_needed = int(audio.silence_duration / block_duration)
    max_blocks = int(audio.max_duration / block_duration)
    min_blocks = int(audio.min_duration / block_duration)

    collected: list[np.ndarray] = []
    silent_streak = 0

    with sd.InputStream(
        samplerate=audio.sample_rate,
        channels=audio.channels,
        dtype="float32",
        blocksize=frames_per_block,
        device=audio.input_device,
    ) as stream:
        log.info("enregistrement en cours (max %.0f s)…", audio.max_duration)
        for index in range(max_blocks):
            block, overflowed = stream.read(frames_per_block)
            if overflowed:
                log.debug("dépassement du tampon d'entrée")
            mono = block.reshape(-1)
            collected.append(mono)
            rms = float(np.sqrt(np.mean(np.square(mono))))
            silent_streak = silent_streak + 1 if rms < audio.silence_threshold else 0
            if index >= min_blocks and silent_streak >= silence_blocks_needed:
                log.info("silence détecté, fin de l'enregistrement (%.1f s)", index * block_duration)
                break

    samples = np.concatenate(collected) if collected else np.zeros(0, dtype=np.float32)
    log.info("audio capturé : %.2f s", len(samples) / audio.sample_rate)
    return samples.astype(np.float32)


def save_wav(samples: np.ndarray, path: str | Path, sample_rate: int = 16000) -> Path:
    import soundfile as sf

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, samples, sample_rate)
    return destination


def load_wav(path: str | Path, target_rate: int = 16000) -> np.ndarray:
    """Charge un wav en float32 mono. Ne ré-échantillonne pas : il refuse."""
    import soundfile as sf

    samples, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if rate != target_rate:
        raise ValueError(
            f"{path} est à {rate} Hz, or le pipeline attend {target_rate} Hz. "
            f"Convertis-le : ffmpeg -i {path} -ar {target_rate} -ac 1 sortie.wav"
        )
    return samples.astype(np.float32)
