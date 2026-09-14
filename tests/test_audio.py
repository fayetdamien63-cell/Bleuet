"""Tests de la logique de capture, sans matériel audio : on alimente
directement la file du MicStream au lieu d'ouvrir un flux PortAudio."""

import numpy as np

from bleuet.audio.capture import BLOCK_SIZE, AudioConfig, MicStream

AUDIO = AudioConfig(
    sample_rate=16000,
    max_duration=2.0,
    silence_duration=0.24,      # 3 blocs de 80 ms
    min_duration=0.16,          # 2 blocs
    silence_threshold=0.01,
    preroll_duration=0.4,       # 5 blocs
)


def loud(value: int = 8000) -> np.ndarray:
    return np.full(BLOCK_SIZE, value, dtype=np.int16)


def silent() -> np.ndarray:
    return np.zeros(BLOCK_SIZE, dtype=np.int16)


def feed(mic: MicStream, blocks) -> None:
    for block in blocks:
        mic._queue.put(block)


def test_arret_sur_silence():
    mic = MicStream(AUDIO)
    feed(mic, [loud()] * 4 + [silent()] * 3 + [loud()] * 20)
    samples = mic.record_until_silence(with_preroll=False)
    # 4 blocs de parole + les 3 blocs de silence qui déclenchent l'arrêt.
    assert len(samples) == 7 * BLOCK_SIZE


def test_le_preroll_est_ajoute_en_tete():
    mic = MicStream(AUDIO)
    for block in [loud(4000)] * 3:          # audio « déjà passé »
        mic._recent.append(block)
    feed(mic, [loud()] * 2 + [silent()] * 3)
    samples = mic.record_until_silence()
    assert len(samples) == (3 + 5) * BLOCK_SIZE
    assert np.isclose(samples[0], 4000 / 32768.0, atol=1e-4)


def test_le_preroll_est_borne_par_sa_duree():
    mic = MicStream(AUDIO)
    for _ in range(50):                      # bien plus que les 5 blocs gardés
        mic._recent.append(loud())
    assert len(mic.preroll()) == 5 * BLOCK_SIZE


def test_flush_vide_la_file_et_le_preroll():
    mic = MicStream(AUDIO)
    feed(mic, [loud()] * 5)
    mic._recent.append(loud())
    mic.flush()
    assert mic._queue.empty()
    assert mic.preroll().size == 0


def test_duree_maximale_respectee():
    mic = MicStream(AUDIO)
    feed(mic, [loud()] * 100)                # jamais de silence
    samples = mic.record_until_silence(with_preroll=False)
    assert len(samples) == int(AUDIO.max_duration / 0.08) * BLOCK_SIZE
