# 5. Ressources nécessaires

## 5.1 Matériel

### Indispensable

| Élément | Pourquoi | Repère de prix |
|---|---|---|
| Raspberry Pi 1B+ | tu l'as | 0 € |
| **Micro USB** (omni ou réseau 2 micros) | le Pi n'a **aucune entrée audio** | 15–40 € |
| **Sortie audio USB** (carte son ou enceinte USB) | le jack 3,5 mm du Pi 1B+ est bruité (PWM, partagé avec la vidéo composite) | 10–30 € |
| Alim **5 V / 2 A** de qualité | sous-alimentation = corruption SD + xruns audio | 10 € |
| Carte microSD **classe A1**, 16–32 Go | les cartes lentes provoquent des blocages I/O | 8 € |
| Câble Ethernet ou adaptateur CPL | **fortement préféré au Wi-Fi USB** (cf. § 1.2) | 5–30 € |

> **Le meilleur achat unique : un speakerphone USB de conférence** (type Jabra Speak,
> Anker PowerConf, ou équivalent générique). Micro + haut-parleur + parfois AEC matériel,
> dans un seul port USB. Il résout d'un coup la qualité micro, la sortie audio, le nombre
> de ports et une partie du problème d'écho. 40–90 € qui font gagner des semaines.

### Optionnel

| Élément | Pourquoi | Prix |
|---|---|---|
| **Raspberry Pi Zero 2 W** | **le plan de secours du risque R1** — ARMv7/aarch64, 4 cœurs, Wi-Fi intégré, wake word local sans douleur | ~20 € |
| Hub USB auto-alimenté | si > 2 périphériques (polyfuse 1,2 A partagé) | 15 € |
| LED RGB + résistances (GPIO) | retour d'état visible, indispensable au debug | 3 € |
| Bouton poussoir GPIO | déclenchement de secours, très utile en Phase 1 | 1 € |
| Boîtier | ne le mets pas dans un tiroir, le micro doit être dégagé | 10 € |

**Total réaliste : 60 à 130 €** selon les choix (le speakerphone étant le gros poste).

### Côté serveur

- **Recommandé : ton PC fixe**, allumé en permanence ou réveillé par Wake-on-LAN.
  Un GPU même modeste (≥ 6 Go VRAM) rend `faster-whisper medium` confortable, mais un CPU
  récent suffit pour `small`.
- **Alternative : VPS** 2 vCPU / 4 Go (Hetzner CX22 ~4 €/mois, Scaleway, OVH). Attention :
  sans GPU, whisper est lent → prévoir un ASR cloud, ce qui change ton profil de coût
  **et** de vie privée.

---

## 5.2 Clés API et comptes

### Obligatoire : rien.

C'est volontaire. La v1 complète (météo + ASR + TTS) peut tourner **sans une seule clé API**
si le serveur est ton PC : Open-Meteo sans clé, faster-whisper local, Piper local.

### Selon les options retenues

| Service | Rôle | Clé requise | Coût | Quand |
|---|---|---|---|---|
| **Open-Meteo** | météo | **non** | gratuit (usage non commercial, < 10 000 appels/j) | Phase 3 — **retenu** |
| **Open-Meteo Geocoding** | ville → coordonnées | **non** | gratuit | Phase 3 |
| **Anthropic API** | LLM étage 2 (tool calling) | `ANTHROPIC_API_KEY` | à l'usage, quelques €/mois en usage domestique | Phase 4 |
| **Brave Search API** | recherche web propre | `BRAVE_API_KEY` | palier gratuit ~2 000 req/mois | Phase 4 |
| **Tavily** | alternative recherche web, orientée LLM | `TAVILY_API_KEY` | palier gratuit | Phase 4 (alt.) |
| **Deepgram** | ASR cloud (repli VPS) | `DEEPGRAM_API_KEY` | ~0,004 €/min, crédit offert à l'inscription | si pas de PC fixe |
| **ElevenLabs** | TTS haut de gamme FR | `ELEVENLABS_API_KEY` | palier gratuit limité, puis ~5 €/mois | si Piper te déçoit |
| **OpenAI** | TTS et/ou ASR alternatifs | `OPENAI_API_KEY` | à l'usage | alternative |
| **Tailscale** | tunnel privé | compte (pas de clé applicative) | gratuit en perso | Phase 1 — **retenu** |
| **Home Assistant** | domotique | jeton d'accès longue durée | auto-hébergé, gratuit | Phase 6 |

> Piège CGU à noter : le palier gratuit d'Open-Meteo est **réservé à l'usage non commercial**.
> Pour un assistant chez toi, tu es dans les clous.

### Modèles et ressources à télécharger (gratuits)

| Ressource | Usage | Note |
|---|---|---|
| `faster-whisper small` ou `medium` | ASR français | ~500 Mo / ~1,5 Go |
| **Piper** `fr_FR-siwis-medium` / `fr_FR-upmc-medium` | TTS français | ~60 Mo, teste les deux, les voix sont très différentes |
| **openWakeWord** (framework + entraînement) | wake word « Hey Bleuet » | modèle final ~1 Mo |
| **py-webrtcvad** / `libopus` | VAD et codec | compilent sur ARMv6 |
| Corpus de bruit de fond | robustesse du wake word | **enregistre le tien** : ta cuisine, ta télé, ton lave-vaisselle |

---

## 5.3 Compétences et outils de développement

- **Go** (client) : cross-compilation `GOOS=linux GOARCH=arm GOARM=6`. Pas besoin d'être expert.
- **Python 3.11 async** (serveur) : FastAPI, WebSocket, `asyncio`.
- **ALSA** : `arecord`, `aplay`, `alsamixer`, `asound.conf`. Prévois d'y passer une soirée entière — tout le monde y passe.
- **Docker Compose** (serveur).
- **systemd** : units, `Restart`, `WatchdogSec`.
- Un **PC de développement** : tu ne compileras jamais sur le Pi.

---

## 5.4 Coût mensuel estimé

| Scénario | Coût / mois |
|---|---|
| PC fixe + tout en local + Open-Meteo | **0 €** (hors électricité) |
| PC fixe + LLM étage 2 en usage domestique | **1–4 €** |
| VPS + ASR cloud + TTS cloud + LLM | **12–25 €** |

Le routeur déterministe (§ 1.4) est ce qui maintient la ligne du milieu à quelques euros
plutôt qu'à quelques dizaines.

---

## 5.5 Ce qu'il te faut décider avant d'écrire du code

1. **PC fixe ou VPS ?** → détermine ASR/TTS local vs cloud, et donc coût + vie privée.
2. **Es-tu prêt à mettre 20 € dans un Pi Zero 2 W** si la Phase 0 dit non ? Réponds
   maintenant, à froid, pas dans trois semaines à 23 h.
3. **Quelles sont tes 5 phrases quotidiennes réelles ?** Écris-les. Elles définissent la v1
   mieux que n'importe quel document d'architecture.
4. **Speakerphone USB ou micro + carte son séparés ?**
