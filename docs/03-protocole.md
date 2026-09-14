# 3. Contrat client ↔ serveur

> [!NOTE]
> **Document d'étude, conservé pour référence — il ne décrit pas le code du dépôt.**
> Cette conception visait un satellite Go sur Raspberry Pi 1B+ relié à un serveur
> par WebSocket. Elle a été écartée : le Pi 1B+ est trop juste (ARMv6, pas de NEON,
> pas de Wi-Fi ni d'entrée audio) et un Pi 3 est déjà disponible. L'implémentation
> retenue est le MVP Python décrit dans le [README](../README.md).
> Ce qui en a été repris : le pre-roll audio, Open-Meteo, les règles de rédaction
> orale, et les analyses de latence et de vie privée.

C'est la pièce maîtresse du projet : tant que ce contrat est respecté, client et serveur
sont interchangeables. Un satellite ESP32 ou une appli téléphone pourraient le parler.

## 3.1 Connexion

```
wss://bleuet.<ton-tailnet>.ts.net/v1/stream
Authorization: Bearer <device_token>
X-Bleuet-Device: salon-pi1
```

- Connexion **persistante**, rétablie automatiquement (backoff exponentiel 1→30 s + jitter).
- `ping`/`pong` WebSocket toutes les 20 s ; absence de `pong` pendant 45 s → reconnexion.
- Trames **texte** = JSON de contrôle. Trames **binaires** = paquets Opus (20 ms).

## 3.2 Machine à états du client

```
   DISCONNECTED ──connect──► IDLE ──wake──► LISTENING ──endpoint──► THINKING
        ▲                     ▲                  │                     │
        │                     │              (timeout)                 │
        └──── erreur ─────────┴──────────────────┴──── speak_end ──── SPEAKING
                                                                       │
                                                         micro coupé ──┘
```

| État | LED | Micro | Earcon |
|---|---|---|---|
| `DISCONNECTED` | rouge clignotant | off | — |
| `IDLE` | éteint | actif (VAD seul) | — |
| `LISTENING` | bleu fixe | actif, streaming | bip montant (immédiat, local) |
| `THINKING` | bleu pulsé | coupé | — |
| `SPEAKING` | vert | **coupé** (half-duplex) | — |
| erreur | rouge, 2 s | coupé | bip descendant |

Garde-fous : `LISTENING` limité à 12 s, `THINKING` à 15 s, `SPEAKING` à 60 s.
Tout dépassement → earcon d'erreur et retour à `IDLE`. Un assistant qui reste bloqué en
écoute est pire qu'un assistant en panne.

## 3.3 Messages — client → serveur

```jsonc
// à l'ouverture
{ "t": "hello", "protocol_version": 1, "device": "salon-pi1",
  "fw": "0.3.1", "audio": { "codec": "opus", "rate": 16000, "ch": 1, "frame_ms": 20 },
  "caps": { "local_wake": false, "aec": false, "led": true } }

// début d'un tour ; "pre_roll_ms" = audio capturé AVANT la détection, déjà envoyé
{ "t": "turn_start", "turn_id": "01J8Z…", "trigger": "vad|local_wake|button",
  "pre_roll_ms": 700 }

// (les paquets Opus partent en trames binaires entre turn_start et turn_end)

// fin de parole détectée localement (le serveur peut aussi décider seul)
{ "t": "turn_end", "turn_id": "01J8Z…", "reason": "silence|timeout|cancel" }

// télémétrie légère, toutes les 60 s
{ "t": "stats", "xruns": 0, "rss_kb": 9800, "rtt_ms": 14, "temp_c": 46.2 }

{ "t": "pong", "id": 42 }
```

**Le pre-roll est essentiel.** Le client garde en permanence un tampon circulaire de
~1 s. Quand le wake word déclenche, la fin de « Hey Bleuet » **et le début de la question**
sont déjà passés. Sans pre-roll, tu perds systématiquement le premier mot utile et
l'assistant paraîtra bête pour une raison purement mécanique.

## 3.4 Messages — serveur → client

```jsonc
{ "t": "wake_confirmed", "turn_id": "01J8Z…", "score": 0.91 }
{ "t": "wake_rejected",  "turn_id": "01J8Z…", "score": 0.12 }   // client → IDLE, silencieux

{ "t": "asr_partial", "turn_id": "…", "text": "quelle température maximum" }
{ "t": "asr_final",   "turn_id": "…", "text": "quelle température maximum est annoncée pour demain",
  "lang": "fr", "confidence": 0.94 }

{ "t": "state", "turn_id": "…", "value": "thinking" }

// filler optionnel si l'outil dépasse 800 ms
{ "t": "filler", "turn_id": "…", "text": "je regarde" }

{ "t": "speak_start", "turn_id": "…", "codec": "opus", "rate": 24000,
  "text": "Demain la température maximale sera de trente-six degrés, avec un grand soleil." }
// … trames binaires Opus …
{ "t": "speak_end", "turn_id": "…" }

{ "t": "error", "turn_id": "…", "code": "asr_failed|tool_failed|timeout|unauthorized",
  "speak": "Je n'ai pas compris, tu peux répéter ?" }

{ "t": "ping", "id": 42 }
```

Règle : **toute erreur destinée à l'utilisateur porte un champ `speak`.** Le client ne
compose jamais de phrase lui-même — il ne parle pas français, il joue de l'audio.

## 3.5 Cadrage des trames binaires

Chaque trame binaire porte un en-tête de 4 octets suivi du paquet Opus :

```
octet 0    : direction/type  (0x01 = audio montant, 0x02 = audio descendant)
octet 1    : flags           (bit0 = dernière trame du tour)
octets 2-3 : numéro de séquence (uint16, big-endian, rebouclant)
octets 4+  : paquet Opus (20 ms)
```

Le numéro de séquence sert uniquement à **détecter** les pertes et à les compter dans la
télémétrie — pas à les corriger. En TCP il n'y a pas de perte, mais il y a des
reconnexions : le compteur permet de savoir qu'un tour a été tronqué et d'abandonner
proprement plutôt que de transcrire un charabia.

## 3.6 Format d'une skill (côté serveur)

Une skill = une fonction typée, exposée à la fois au routeur déterministe et au LLM.

```python
@skill(
    name="meteo_previsions",
    description="Prévisions météo pour un lieu et un jour donnés.",
    patterns=[
        r"\b(temp[eé]rature|m[eé]t[eé]o|il fera|va-t-il pleuvoir)\b",
    ],
    params={
        "lieu": "Ville ou lieu. Défaut : domicile configuré.",
        "quand": "aujourd'hui | demain | apres-demain | YYYY-MM-DD",
        "metrique": "max | min | pluie | resume",
    },
)
async def meteo_previsions(lieu: str | None, quand: str, metrique: str) -> SkillResult:
    ...
    return SkillResult(
        speak="Demain la température maximale sera de trente-six degrés, avec un grand soleil.",
        data={"tmax": 36.0, "code": 0},
        cacheable_for=1800,
    )
```

Une seule déclaration alimente les deux étages du routeur : les `patterns` pour l'étage 1,
le `description`/`params` pour le schéma d'outil du LLM. **Pas de duplication**, donc pas
de dérive entre les deux.
