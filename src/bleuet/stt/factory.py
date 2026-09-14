from __future__ import annotations

from ..logging_setup import get_logger
from .base import Transcriber

log = get_logger("bleuet.stt")


def build_transcriber(cfg) -> Transcriber:
    backend = cfg.get("stt.backend", "faster_whisper")
    if backend == "mock":
        from .mock import MockTranscriber

        return MockTranscriber(cfg.get("stt.mock_text", "Quelle est la météo aujourd'hui ?"))
    if backend == "faster_whisper":
        from .faster_whisper_backend import FasterWhisperTranscriber

        return FasterWhisperTranscriber(
            model=cfg.get("stt.model", "small"),
            language=cfg.get("stt.language", "fr"),
            compute_type=cfg.get("stt.compute_type", "int8"),
            beam_size=cfg.get("stt.beam_size", 1),
        )
    raise ValueError(f"Backend STT inconnu : {backend!r} (attendu: faster_whisper | mock)")
