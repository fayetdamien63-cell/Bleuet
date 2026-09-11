"""Synthèse vocale avec Piper (binaire natif, ~50 Mo de RAM, OK sur Pi 3).

On appelle le binaire en sous-processus plutôt que la lib Python : c'est le
chemin le plus portable (mêmes commandes sur PC et sur Pi) et ça évite de
faire dépendre le projet d'onnxruntime côté serveur.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ..config import PROJECT_ROOT
from ..logging_setup import get_logger
from .base import Speaker

log = get_logger("bleuet.tts.piper")


class PiperSpeaker(Speaker):
    def __init__(
        self,
        binary: str = "piper",
        voice: str = "data/models/fr_FR-siwis-medium.onnx",
        length_scale: float = 1.0,
        play: bool = True,
        output_device: int | None = None,
    ):
        self.binary = binary
        self.voice = voice
        self.length_scale = length_scale
        self.play = play
        self.output_device = output_device

    def _resolve_voice(self) -> Path:
        path = Path(self.voice)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            raise FileNotFoundError(
                f"Voix Piper introuvable : {path}\n"
                "Télécharge-la avec : python scripts/download_piper_voice.py"
            )
        if not path.with_suffix(path.suffix + ".json").exists():
            raise FileNotFoundError(
                f"Le fichier de config de la voix manque : {path}.json "
                "(Piper a besoin du .onnx ET du .onnx.json)"
            )
        return path

    def _resolve_binary(self) -> str:
        resolved = shutil.which(self.binary)
        if resolved is None and not Path(self.binary).exists():
            raise FileNotFoundError(
                f"Binaire Piper introuvable : {self.binary!r}. "
                "Installe-le (https://github.com/OHF-Voice/piper1-gpl ou `pip install piper-tts`) "
                "puis renseigne tts.binary dans config/config.yaml."
            )
        return resolved or self.binary

    def synthesize_to_file(self, text: str, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self._resolve_binary(),
            "--model", str(self._resolve_voice()),
            "--output_file", str(destination),
            "--length_scale", str(self.length_scale),
        ]
        started = time.monotonic()
        result = subprocess.run(
            command, input=text.encode("utf-8"), capture_output=True, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Piper a échoué (code {result.returncode}) : "
                f"{result.stderr.decode('utf-8', 'replace').strip()}"
            )
        log.info("synthèse Piper en %.1f s -> %s", time.monotonic() - started, destination.name)
        return destination

    def speak(self, text: str) -> Path | None:
        wav_path = Path(tempfile.gettempdir()) / f"bleuet_{int(time.time() * 1000)}.wav"
        self.synthesize_to_file(text, wav_path)
        if self.play:
            from ..audio.playback import play_wav

            play_wav(wav_path, self.output_device)
        return wav_path
