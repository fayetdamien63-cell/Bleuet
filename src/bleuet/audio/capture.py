"""Capture micro : un flux unique, partagé entre wake word et enregistrement.

`sounddevice` + `numpy` uniquement : portable PC/Pi, aucune dépendance lourde.
Tout l'audio circule en 16 kHz mono, le format commun à openWakeWord et à
Whisper — en int16 vers le wake word, en float32 vers Whisper.
"""

from __future__ import annotations

import collections
import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from ..logging_setup import get_logger

log = get_logger("bleuet.audio.capture")

BLOCK_SIZE = 1280  # 80 ms à 16 kHz : la taille attendue par openWakeWord
INT16_SCALE = 32768.0


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    input_device: int | None = None
    max_duration: float = 12.0
    silence_duration: float = 1.2
    min_duration: float = 0.8
    silence_threshold: float = 0.012
    preroll_duration: float = 1.0

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


class MicStream:
    """Un seul flux d'entrée, pour toute la durée de vie de l'assistant.

    Deux raisons de ne pas ouvrir un flux par usage :

    1. Ouvrir un second `InputStream` sur le même périphérique pendant que le
       premier tourne échoue sur la plupart des backends ALSA (`Device or
       resource busy`).
    2. Repartir d'un flux neuf après la détection du mot de réveil fait perdre
       les ~300 ms suivantes — soit, en pratique, le premier mot de la question.
       Le tampon circulaire (« pre-roll ») restitue cet audio déjà capté.
    """

    def __init__(self, audio: AudioConfig, block_size: int = BLOCK_SIZE):
        self.audio = audio
        self.block_size = block_size
        self.block_duration = block_size / audio.sample_rate
        preroll_blocks = int(audio.preroll_duration / self.block_duration)
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self._recent: collections.deque[np.ndarray] = collections.deque(
            maxlen=max(0, preroll_blocks)
        )
        self._stream = None

    def __enter__(self) -> "MicStream":
        sd = _import_sounddevice()

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                log.debug("statut du flux audio : %s", status)
            self._queue.put(indata.copy().reshape(-1))

        self._stream = sd.InputStream(
            samplerate=self.audio.sample_rate,
            channels=self.audio.channels,
            dtype="int16",
            blocksize=self.block_size,
            device=self.audio.input_device,
            callback=callback,
        )
        self._stream.start()
        log.info(
            "flux micro ouvert (%d Hz, blocs de %d ms, pre-roll %.1f s)",
            self.audio.sample_rate,
            int(self.block_duration * 1000),
            self._recent.maxlen * self.block_duration if self._recent.maxlen else 0.0,
        )
        return self

    def __exit__(self, *exc_info) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("flux micro fermé")

    def blocks(self) -> Iterator[np.ndarray]:
        """Itère indéfiniment sur des blocs int16, en alimentant le pre-roll."""
        while True:
            block = self._queue.get()
            self._recent.append(block)
            yield block

    def flush(self) -> None:
        """Jette l'audio en attente : évite de réécouter sa propre réponse."""
        dropped = 0
        while not self._queue.empty():
            self._queue.get_nowait()
            dropped += 1
        self._recent.clear()
        if dropped:
            log.debug("%d bloc(s) audio jetés après la réponse", dropped)

    def preroll(self) -> np.ndarray:
        """L'audio capté juste avant le mot de réveil, en float32."""
        if not self._recent:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(list(self._recent)).astype(np.float32) / INT16_SCALE

    def record_until_silence(self, with_preroll: bool = True) -> np.ndarray:
        """Enregistre jusqu'à `silence_duration` s de silence (ou `max_duration`).

        Retourne un tableau float32 dans [-1, 1]. Détection de silence par RMS :
        suffisant pour une pièce calme et quasi gratuit en CPU — un vrai VAD
        (webrtcvad, silero) serait la première amélioration si la maison est
        bruyante.
        """
        audio = self.audio
        silence_blocks_needed = int(audio.silence_duration / self.block_duration)
        max_blocks = int(audio.max_duration / self.block_duration)
        min_blocks = int(audio.min_duration / self.block_duration)

        collected: list[np.ndarray] = []
        if with_preroll:
            head = self.preroll()
            if head.size:
                collected.append(head)
                log.info("pre-roll : %.2f s d'audio récupérées", head.size / audio.sample_rate)

        silent_streak = 0
        log.info("enregistrement en cours (max %.0f s)…", audio.max_duration)
        for index in range(max_blocks):
            mono = self._queue.get().astype(np.float32) / INT16_SCALE
            collected.append(mono)
            rms = float(np.sqrt(np.mean(np.square(mono))))
            silent_streak = silent_streak + 1 if rms < audio.silence_threshold else 0
            if index >= min_blocks and silent_streak >= silence_blocks_needed:
                log.info("silence détecté, fin de l'enregistrement")
                break

        samples = np.concatenate(collected) if collected else np.zeros(0, dtype=np.float32)
        log.info("audio capturé : %.2f s", len(samples) / audio.sample_rate)
        return samples.astype(np.float32)


def stream_chunks(audio: AudioConfig, block_size: int = BLOCK_SIZE) -> Iterator[np.ndarray]:
    """Flux de blocs int16, pour tester le wake word seul (`bleuet wakeword`)."""
    with MicStream(audio, block_size) as mic:
        yield from mic.blocks()


def record_until_silence(audio: AudioConfig) -> np.ndarray:
    """Enregistrement ponctuel, hors boucle d'assistant (`bleuet record`, `stt`)."""
    with MicStream(audio) as mic:
        return mic.record_until_silence(with_preroll=False)


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
