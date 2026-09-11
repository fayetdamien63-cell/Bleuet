#!/usr/bin/env python3
"""Télécharge une voix française Piper dans data/models/.

    python scripts/download_piper_voice.py              # fr_FR-siwis-medium
    python scripts/download_piper_voice.py fr_FR-upmc-medium
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.request import urlopen

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR"
VOICES = {
    "fr_FR-siwis-medium": f"{BASE}/siwis/medium/fr_FR-siwis-medium.onnx",
    "fr_FR-siwis-low": f"{BASE}/siwis/low/fr_FR-siwis-low.onnx",
    "fr_FR-upmc-medium": f"{BASE}/upmc/medium/fr_FR-upmc-medium.onnx",
    "fr_FR-gilles-low": f"{BASE}/gilles/low/fr_FR-gilles-low.onnx",
}
DESTINATION = Path(__file__).resolve().parents[1] / "data" / "models"


def download(url: str, target: Path) -> None:
    print(f"  {url}\n  -> {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, open(target, "wb") as handle:
        handle.write(response.read())


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "fr_FR-siwis-medium"
    if name not in VOICES:
        print(f"Voix inconnue : {name}\nDisponibles : {', '.join(VOICES)}")
        return 1
    url = VOICES[name]
    download(url, DESTINATION / f"{name}.onnx")
    download(url + ".json", DESTINATION / f"{name}.onnx.json")
    print(f"\nRenseigne dans config/config.yaml :\n  tts.voice: data/models/{name}.onnx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
