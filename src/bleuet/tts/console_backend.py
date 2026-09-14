"""Sortie « vocale » sur la console : utile pour développer sans carte son."""

from __future__ import annotations

from pathlib import Path

from ..logging_setup import get_logger
from .base import Speaker

log = get_logger("bleuet.tts.console")


class ConsoleSpeaker(Speaker):
    def speak(self, text: str) -> Path | None:
        log.info("(TTS console) %s", text)
        print(f"\n🔊 {text}\n")
        return None
