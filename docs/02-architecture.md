# 2. Architecture cible

> [!NOTE]
> **Document d'étude, conservé pour référence — il ne décrit pas le code du dépôt.**
> Cette conception visait un satellite Go sur Raspberry Pi 1B+ relié à un serveur
> par WebSocket. Elle a été écartée : le Pi 1B+ est trop juste (ARMv6, pas de NEON,
> pas de Wi-Fi ni d'entrée audio) et un Pi 3 est déjà disponible. L'implémentation
> retenue est le MVP Python décrit dans le [README](../README.md).
> Ce qui en a été repris : le pre-roll audio, Open-Meteo, les règles de rédaction
> orale, et les analyses de latence et de vie privée.

## 2.1 Vue d'ensemble

```
┌──────────────────────────────────────┐        ┌────────────────────────────────────────────┐
│  SATELLITE — Raspberry Pi 1B+        │        │  SERVEUR — PC fixe (recommandé) ou VPS     │
│  binaire Go statique, ~10 Mo RAM     │        │  Docker Compose                            │
│                                      │        │                                            │
│  ┌────────────────────────────────┐  │        │  ┌──────────────────────────────────────┐  │
│  │ Capture ALSA 16 kHz mono 16bit │  │        │  │ Gateway WebSocket (TLS + token)      │  │
│  └──────────────┬─────────────────┘  │        │  │  auth · sessions · rate limit        │  │
│                 ▼                    │        │  └──────────────┬───────────────────────┘  │
│  ┌────────────────────────────────┐  │        │                 ▼                          │
│  │ VAD (WebRTC) — détecte parole  │  │        │  ┌──────────────────────────────────────┐  │
│  └──────────────┬─────────────────┘  │        │  │ Wake word (openWakeWord "Hey Bleuet")│  │
│                 ▼                    │        │  │  confirme, sinon jette le buffer     │  │
│  ┌────────────────────────────────┐  │        │  └──────────────┬───────────────────────┘  │
│  │ Wake word local (si Phase 0 OK)│  │        │                 ▼                          │
│  │  sinon : passe tout au serveur │  │        │  ┌──────────────────────────────────────┐  │
│  └──────────────┬─────────────────┘  │        │  │ ASR streaming — faster-whisper fr    │  │
│                 ▼                    │        │  │  repli : Deepgram nova (fr)          │  │
│  ┌────────────────────────────────┐  │        │  └──────────────┬───────────────────────┘  │
│  │ Encodage Opus 16 kHz / 24 kbps │  │        │                 ▼                          │
│  └──────────────┬─────────────────┘  │        │  ┌──────────────────────────────────────┐  │
│                 │                    │        │  │ ROUTEUR                              │  │
│  ┌──────────────▼─────────────────┐  │        │  │  étage 1 : intents déterministes     │  │
│  │ WebSocket TLS  ◄──────────────────────────►│  │  étage 2 : LLM + tool calling        │  │
│  └──────────────┬─────────────────┘  │        │  └──────────────┬───────────────────────┘  │
│                 ▼                    │        │                 ▼                          │
│  ┌────────────────────────────────┐  │        │  ┌──────────────────────────────────────┐  │
│  │ Lecture Opus → ALSA (aplay)    │  │        │  │ SKILLS (registre d'outils)           │  │
│  │ mute micro pendant lecture     │  │        │  │ météo · heure · minuteur · domotique │  │
│  └────────────────────────────────┘  │        │  │ recherche web · listes               │  │
│  ┌────────────────────────────────┐  │        │  └──────────────┬───────────────────────┘  │
│  │ Earcons + LED d'état           │  │        │                 ▼                          │
│  └────────────────────────────────┘  │        │  ┌──────────────────────────────────────┐  │
│                                      │        │  │ TTS streaming — Piper fr_FR          │  │
│                                      │        │  │  repli qualité : ElevenLabs / OpenAI │  │
│                                      │        │  └──────────────────────────────────────┘  │
│                                      │        │  ┌──────────────────────────────────────┐  │
│                                      │        │  │ Observabilité : logs, latences, coût │  │
└──────────────────────────────────────┘        └────────────────────────────────────────────┘
                        └──── Tailscale / Cloudflare Tunnel (aucun port ouvert) ────┘
```

## 2.2 Principes directeurs

1. **Le satellite est jetable.** Zéro logique métier. Il ne connaît ni la météo, ni les
   lampes, ni le LLM. Il connaît une URL, un token, un micro et un haut-parleur.
2. **Le contrat réseau est la frontière stable.** Versionné (`protocol_version`).
   On peut réécrire entièrement client ou serveur sans toucher à l'autre.
3. **Tout est en streaming.** Aucune étape n'attend la fin de la précédente si elle peut
   commencer avant.
4. **Le déterministe avant le probabiliste.** Le LLM est un repli, pas le moteur.
5. **Dégradation gracieuse.** LLM down → intents déterministes ok. Réseau down → earcon
   d'erreur explicite, jamais un silence.
6. **Tout est mesuré.** Chaque tour émet un enregistrement de latences par étape.
   Sans ça, l'optimisation est une superstition.

## 2.3 Choix de stack, et pourquoi

### Client — **Go**, pas Python

C'est le choix le moins évident et le plus important du projet.

Sur ARMv6, `pip install` compile depuis les sources (pas de roues précompilées) : chaque
dépendance devient 20 minutes de compilation sur un cœur à 700 MHz, quand ça compile. Et
il faut ensuite entretenir un venv sur une carte SD.

Avec Go : `GOOS=linux GOARCH=arm GOARM=6 go build` depuis ton PC produit **un binaire
statique unique**, sans runtime, sans dépendance, ~10 Mo de RAM. Le déploiement est un
`scp` + `systemctl restart`. La concurrence (capture / réseau / lecture en parallèle) est
native, ce qui est exactement le besoin ici.

Alternative acceptable si Go te bloque : Python 3.11 minimaliste, dépendances réduites au
strict minimum (`websockets` seulement), capture et lecture déléguées à `arecord`/`aplay`
en sous-processus. C'est jouable, mais tu paieras l'installation et la RAM.

### Transport — **WebSocket TLS**, audio en **Opus**

Une seule connexion persistante, bidirectionnelle, qui traverse n'importe quel NAT.
Trames binaires pour l'audio, trames texte JSON pour le contrôle.
Opus à 24 kbps en 16 kHz : ~3 ko/s montant, encodage négligeable en CPU (Opus est conçu
pour l'embarqué), et une reconnexion coûte un handshake, pas une resynchronisation.

### ASR — **faster-whisper** auto-hébergé, repli **Deepgram**

`faster-whisper` (CTranslate2) sur ton PC : `small` en français est un très bon compromis
qualité/latence, `medium` si tu as un GPU. Gratuit, l'audio reste chez toi.
Repli si tu pars sur un VPS CPU-only : Deepgram (`nova`, français), streaming natif,
facturé à la minute d'audio réellement traitée.

### Routeur — deux étages

Étage 1 : normalisation (minuscules, sans accents, sans ponctuation) puis règles
+ correspondance floue sur un dictionnaire d'entités (pièces, appareils, villes).
Étage 2 : LLM avec **tool-calling** — il choisit un outil et ses arguments, il n'exécute
rien lui-même. La réponse finale est reformulée pour être **dite**, pas lue.

### TTS — **Piper** (fr_FR), repli qualité **ElevenLabs / OpenAI**

Piper est local, gratuit, largement plus rapide que le temps réel sur un PC, et les voix
françaises (`fr_FR-siwis-medium`, `fr_FR-upmc-medium`) sont honnêtes. On synthétise
**phrase par phrase** pour commencer à jouer pendant que la suite se génère.

### Serveur — **Python 3.11 + FastAPI + Docker Compose**

L'écosystème ASR/TTS/LLM est en Python, autant ne pas se battre. FastAPI gère nativement
le WebSocket et l'async. Docker Compose rend le serveur portable entre ton PC et un VPS
le jour où tu changes d'avis — ce qui arrivera.

## 2.4 Règles de rédaction des réponses (souvent oublié)

Une réponse destinée à être **entendue** n'est pas une réponse destinée à être lue.

- 1 à 2 phrases, jamais de liste à puces, jamais d'URL, jamais de markdown.
- Unités développées : « trente-six degrés », pas « 36°C ».
- Heures dites naturellement : « seize heures trente ».
- Chiffres arrondis : « environ vingt minutes », pas « 19,4 minutes ».
- Si une donnée manque, le dire en une phrase courte plutôt que broder.

Ces règles vivent côté serveur, dans une couche de post-traitement **et** dans le prompt
système de l'étage 2. Elles sont testables unitairement — fais-le.

## 2.5 Arborescence proposée

```
bleuet/
├── client/                     # Go — satellite Pi
│   ├── cmd/bleuet/main.go
│   ├── internal/audio/         # capture, lecture, ALSA, earcons
│   ├── internal/vad/           # WebRTC VAD
│   ├── internal/wake/          # wake word local (optionnel selon Phase 0)
│   ├── internal/transport/     # WebSocket, reconnexion, backoff
│   ├── internal/state/         # machine à états + LED
│   ├── configs/bleuet.yaml
│   ├── deploy/bleuet.service   # unit systemd
│   └── Makefile                # build GOARM=6 + deploy
├── server/
│   ├── app/gateway/            # WebSocket, auth, sessions
│   ├── app/asr/                # faster-whisper | deepgram (interface commune)
│   ├── app/wake/               # vérification wake word serveur
│   ├── app/router/             # étage 1 déterministe + étage 2 LLM
│   ├── app/skills/             # meteo.py, heure.py, minuteur.py, domotique.py, web.py
│   ├── app/tts/                # piper | elevenlabs (interface commune)
│   ├── app/telemetry/          # latences, coûts, xruns
│   ├── tests/
│   ├── compose.yaml
│   └── .env.example            # jamais de .env dans Git
├── docs/
└── tools/                      # scripts de spike Phase 0
```
