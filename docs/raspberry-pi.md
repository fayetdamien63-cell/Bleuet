# Portage sur Raspberry Pi 3 — points de vigilance

Le portage n'est **pas** au programme du MVP, mais voici ce qui a été pris en
compte dès maintenant, et ce qui coincera le jour venu. Rappel des contraintes :
ARM Cortex-A53 4 × 1,2 GHz, **1 Go de RAM**, pas de GPU, carte SD lente.

## Verdict par dépendance

| Brique | Paquet | Sur Pi 3 ? | Détail |
|---|---|---|---|
| Wake word | `openwakeword` + `onnxruntime` | ✅ oui | ~50 Mo de RAM, ~15 % d'un cœur en continu. Roues ARM64 disponibles pour `onnxruntime` — **impose un OS 64 bits** (Raspberry Pi OS *arm64*, pas la version 32 bits par défaut). |
| Capture / lecture audio | `sounddevice`, `soundfile` | ✅ oui | Nécessite `libportaudio2` (`sudo apt install libportaudio2 libsndfile1`). Pas de roue ARM pour `sounddevice` : il compile, c'est rapide. |
| STT | `faster-whisper` | ❌ **non** | C'est le vrai blocage. `small` int8 demande ~1 Go de RAM à lui seul et transcrit ~10× plus lentement que le temps réel sur un Pi 3 : inutilisable. Même `tiny` reste pénible (~3-5 s pour 5 s d'audio, ~400 Mo). **→ le STT reste sur le serveur** (c'est exactement ce que prévoit l'architecture : le Pi POST son wav sur `/ask-audio`). |
| Orchestrateur + RAG | `sqlite3` (stdlib) | ✅ oui | Le choix de FTS5 plutôt que d'embeddings est motivé par le Pi : `sentence-transformers` tire `torch` (~2 Go d'installation, plusieurs centaines de Mo de RAM) — exclu. Mais l'orchestrateur a de toute façon vocation à rester sur le serveur. |
| Appel Claude | `anthropic` | ✅ oui | Pur Python + HTTP. Aucun souci, si le Pi doit l'appeler directement. |
| TTS | Piper | ✅ oui | Binaire natif ARM fourni par le projet. Une voix `medium` occupe ~60 Mo de RAM et synthétise à peu près en temps réel sur un Pi 3 ; préférer une voix **`low`** (`fr_FR-siwis-low`) si la latence gêne. |
| API HTTP | `fastapi` + `uvicorn` | ✅ oui | Mais inutile côté Pi : le Pi est client, pas serveur. |
| — | `numpy` | ⚠️ attention | Roues ARM64 disponibles ; sur un OS 32 bits il compile pendant 20 minutes. Encore une raison de partir sur du 64 bits. |

## Répartition cible

```
Raspberry Pi 3                      Serveur (PC / NAS)
──────────────────                  ──────────────────
openwakeword    ─┐
sounddevice      │  POST /ask-audio  ┌─ faster-whisper
Piper (TTS)     ─┘ ───────────────►  ├─ orchestrateur + RAG
                   ◄───────────────  └─ API Claude
                     texte réponse
```

Concrètement, côté Pi il ne restera que `openwakeword`, `onnxruntime`,
`sounddevice`, `soundfile`, `requests` et le binaire Piper — soit les extras
`[wakeword]` du `pyproject.toml`, sans `[stt]` ni `[server]`.

Le code est déjà découpé dans ce sens : `assistant.py` est la seule classe qui
assemble les briques localement ; la variante « Pi » se contentera de remplacer
l'appel à `Orchestrator.answer()` par un POST vers `/ask-audio`. Aucun autre
module n'aura à changer.

## Autres pièges connus

- **Le micro.** Le Pi 3 n'a pas d'entrée audio. Il faut un micro USB (ou un
  ReSpeaker HAT). Vérifier le périphérique avec `bleuet devices` et fixer
  `audio.input_device` : l'index par défaut change parfois au redémarrage.
- **La sortie jack du Pi est de mauvaise qualité** et souffle. Un petit DAC USB
  ou une enceinte Bluetooth (attention à la latence) change tout.
- **La carte SD.** Charger un modèle ONNX depuis une SD de classe 10 est lent ;
  prévoir le préchargement au démarrage (`Assistant.warmup()` le fait déjà).
- **Démarrage automatique** : un service `systemd` avec `Restart=always` et
  `After=sound.target`. À écrire au moment du portage.
- **Chauffe.** Le wake word tourne en continu ; un dissipateur est conseillé si
  le Pi est dans un boîtier fermé.
