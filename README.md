# Bleuet

Assistant vocal familial, local et modulaire : **mot de réveil → transcription →
Claude (avec le contexte de la maison) → réponse parlée**.

MVP développé et testé sur PC (Linux/macOS/Windows), écrit pour être porté
ensuite sur un Raspberry Pi 3 — voir [`docs/raspberry-pi.md`](docs/raspberry-pi.md).

## Documentation

| Document | Contenu |
|---|---|
| **Ce README** | le MVP, c'est-à-dire le code réellement présent dans le dépôt |
| [`docs/wakeword.md`](docs/wakeword.md) | entraîner un mot de réveil français, plus tard |
| [`docs/raspberry-pi.md`](docs/raspberry-pi.md) | points durs du portage sur Pi 3 |
| `docs/01`–`docs/05` | conception antérieure (satellite Go sur Pi 1B+, WebSocket), **écartée** — conservée pour ses analyses |

## Le pipeline

```
micro ──► openWakeWord ──► enregistrement ──► faster-whisper ──► orchestrateur ──► API Claude
                                                                       │
                      data/knowledge (RAG, SQLite FTS5) ───────────────┤
                      data/calendar/famille.ics (agenda) ──────────────┤
                      data/schedules/*.yaml (enfants) ─────────────────┤
                      météo (mock ou OpenWeatherMap) ──────────────────┘
                                                                       │
haut-parleur ◄──────── Piper (TTS local) ◄─────────────────────────────┘
```

Chaque brique est un module indépendant, testable seul, et remplaçable :
`wakeword/`, `stt/`, `rag/` + `context/`, `orchestrator/`, `tts/`.

## Installation

Prérequis système :

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt install python3-venv libportaudio2 libsndfile1 ffmpeg
# macOS
brew install portaudio libsndfile ffmpeg
# Windows : rien à installer, les roues Python embarquent PortAudio.
```

Puis :

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -e ".[wakeword,stt,server,dev]"
```

Les extras sont séparés exprès : sur le Pi, seul `[wakeword]` sera installé.

### Modèles à télécharger

```bash
bleuet download-models                       # modèles openWakeWord pré-entraînés
python scripts/download_piper_voice.py       # voix française Piper (~60 Mo)
```

Le modèle Whisper se télécharge tout seul au premier `bleuet stt` (~500 Mo pour
`small`, mis en cache dans `~/.cache/huggingface`).

### Clés API

```bash
cp .env.example .env
```

| Variable | Obligatoire | Pour quoi |
|---|---|---|
| `ANTHROPIC_API_KEY` | **oui** | l'appel à Claude (<https://console.anthropic.com>) |
| `BLEUET_CITY` | non | ta commune ; Open-Meteo la géocode tout seul |
| `BLEUET_LATITUDE` / `BLEUET_LONGITUDE` | non | évite l'appel de géocodage au démarrage |
| `OPENWEATHER_API_KEY` | non | uniquement si tu préfères OpenWeatherMap à Open-Meteo |

**Une seule clé est nécessaire, celle de Claude.** La météo passe par Open-Meteo,
gratuit et sans clé ; faster-whisper et Piper tournent en local, hors ligne.

## Tester brique par brique

L'ordre recommandé — chaque commande ne dépend que des précédentes :

```bash
bleuet devices                    # 1. quels micros / sorties voit-on ?
bleuet record test.wav            # 2. le micro capte-t-il ? (s'arrête au silence)
bleuet stt test.wav               # 3. la transcription est-elle correcte ?
bleuet tts "Bonjour la famille"   # 4. la synthèse parle-t-elle ?
bleuet wakeword                   # 5. le mot de réveil se déclenche-t-il ?
bleuet index                      # 6. indexer data/knowledge pour le RAG
bleuet search "cantine"           # 7. le RAG retrouve-t-il le bon passage ?
bleuet context "Que fait Léa ?"   # 8. à quoi ressemble le prompt envoyé ? (sans appeler Claude)
bleuet ask "Que fait Léa ?"       # 9. question texte -> réponse texte (appelle Claude)
bleuet say "Que fait Léa ?"       # 10. question texte -> réponse parlée
bleuet run                        # 11. pipeline complet, en écoute permanente
```

Ajoute `--log-level DEBUG` pour voir le prompt complet envoyé à Claude.

Pour travailler sans micro ni modèle Whisper, mets `stt.backend: mock` et
`tts.backend: console` dans `config/config.yaml`.

### Mode client/serveur

```bash
bleuet serve                                     # expose /health, /ask, /ask-audio
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
     -d '{"question":"À quelle heure finit l école aujourd hui ?"}'
curl -X POST localhost:8000/ask-audio -F file=@test.wav
```

C'est la frontière Pi ↔ serveur : plus tard, le Pi enverra son wav sur
`/ask-audio` et synthétisera localement le texte renvoyé.

## Configuration

Tout est dans [`config/config.yaml`](config/config.yaml), commenté. Chaque clé
est surchargeable par une variable d'environnement :
`BLEUET_STT_MODEL=tiny`, `BLEUET_TTS_BACKEND=console`, etc.

Réglages qu'on touche en pratique :

| Clé | Effet |
|---|---|
| `audio.silence_threshold` | seuil RMS de fin d'enregistrement. Trop bas = ça n'arrête jamais ; trop haut = ça coupe au milieu d'une phrase |
| `audio.input_device` | index du micro (`bleuet devices`) |
| `wakeword.threshold` | 0.4 = permissif, 0.7 = strict |
| `stt.model` | `tiny` (rapide, approximatif) → `small` (bon compromis) → `medium` (lent sur CPU) |
| `llm.effort` | `low` pour la latence, `high` pour des réponses plus fouillées |

## Les données de la famille

Trois sources, toutes éditables à la main et versionnées :

- **`data/schedules/<prénom>.yaml`** — l'emploi du temps d'un enfant : une
  `semaine_type` (lundi→dimanche) et des `exceptions` datées (vacances, sortie
  scolaire, annulation). Une exception remplace la semaine type ce jour-là, ou
  s'y ajoute avec `remplace: false`. Ajouter un enfant = ajouter un fichier.
- **`data/calendar/famille.ics`** — l'agenda partagé, au format iCalendar
  (événements ponctuels, journées entières, récurrences hebdo/mensuelles).
  Aujourd'hui un fichier de test ; l'interface `CalendarProvider` est prête pour
  une implémentation CalDAV ou Google Calendar, sans toucher au reste.
- **`data/knowledge/*.md`** — les infos non structurées (règlement de l'école,
  horaires de cantine, poubelles, médecins…). Relancer `bleuet index` après
  modification.

## Choix techniques, et pourquoi

- **STT : `faster-whisper` en local** — hors ligne, gratuit, aucune donnée
  familiale envoyée à un tiers autre qu'Anthropic. En contrepartie c'est la
  brique qui ne tournera **jamais** sur le Pi 3 : elle restera côté serveur.
- **RAG : SQLite FTS5 (BM25) plutôt que des embeddings** — le corpus fait
  quelques pages et les questions reprennent le vocabulaire des documents ;
  BM25 suffit largement. Surtout, un modèle d'embeddings tire `torch`
  (~2 Go, plusieurs centaines de Mo de RAM), incompatible avec un Pi 3.
  L'interface reste ouverte si le besoin évolue.
- **TTS : Piper appelé en sous-processus** — mêmes commandes sur PC et sur Pi,
  et ça évite de faire dépendre le serveur d'`onnxruntime`.
- **Météo : Open-Meteo** — gratuit, sans clé, réponse structurée (pas de page à
  interpréter). OpenWeatherMap reste disponible en changeant une ligne de config.
- **Un seul flux micro, avec pre-roll** — le wake word et l'enregistrement
  puisent dans le même flux. Ouvrir un second flux échouerait sur ALSA, et le
  tampon d'une seconde évite de perdre le premier mot de chaque question.
- **Pas d'historique de conversation** — chaque question est indépendante.
  Simple, prévisible, et la partie stable du prompt est mise en cache côté API.
- **Modèle : `claude-opus-5` avec `effort: low`** — la latence prime pour une
  réponse parlée.

## Tests

```bash
pytest
```

Les tests couvrent les briques sans audio ni réseau : emplois du temps,
lecture de l'agenda ICS, RAG, construction du prompt, configuration.

## Limites connues du MVP

- La fin d'enregistrement se fait sur un simple seuil RMS, pas un vrai VAD :
  à revoir si la maison est bruyante (webrtcvad / silero-vad).
- Le mot de réveil est `hey_jarvis` (anglais), modèle standard de la
  bibliothèque : c'est un choix assumé pour démarrer vite. Le modèle français
  « Dis Bleuet » viendra ensuite — voir [`docs/wakeword.md`](docs/wakeword.md).
- L'agenda est un fichier `.ics` local, pas encore un agenda partagé réel.
- Pas de reconnaissance du locuteur, pas de multi-utilisateur (hors périmètre).
- L'assistant ne peut rien modifier : il répond, il n'agit pas.

## Structure

```
config/config.yaml          configuration commentée
data/                       schedules/, calendar/, knowledge/, models/
docs/                       wakeword.md, raspberry-pi.md
scripts/                    téléchargement des voix Piper
src/bleuet/
  audio/                    capture micro, lecture
  wakeword/                 openWakeWord
  stt/                      base, faster_whisper, mock, factory
  tts/                      base, piper, console, factory
  context/                  weather, calendar_provider, schedules
  rag/                      store (SQLite FTS5)
  orchestrator/             prompt, claude_client, pipeline
  server/                   API FastAPI
  assistant.py              la boucle complète
  cli.py                    toutes les commandes
tests/
```
