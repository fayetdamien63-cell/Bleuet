from __future__ import annotations

from .base import Speaker


def build_speaker(cfg) -> Speaker:
    backend = cfg.get("tts.backend", "piper")
    if backend == "console":
        from .console_backend import ConsoleSpeaker

        return ConsoleSpeaker()
    if backend == "piper":
        from .piper_backend import PiperSpeaker

        return PiperSpeaker(
            binary=cfg.get("tts.binary", "piper"),
            voice=cfg.get("tts.voice", "data/models/fr_FR-siwis-medium.onnx"),
            length_scale=cfg.get("tts.length_scale", 1.0),
            play=cfg.get("tts.play", True),
            output_device=cfg.get("audio.output_device"),
        )
    raise ValueError(f"Backend TTS inconnu : {backend!r} (attendu: piper | console)")
