# 1. Challenge de l'architecture

> [!NOTE]
> **Document d'étude, conservé pour référence — il ne décrit pas le code du dépôt.**
> Cette conception visait un satellite Go sur Raspberry Pi 1B+ relié à un serveur
> par WebSocket. Elle a été écartée : le Pi 1B+ est trop juste (ARMv6, pas de NEON,
> pas de Wi-Fi ni d'entrée audio) et un Pi 3 est déjà disponible. L'implémentation
> retenue est le MVP Python décrit dans le [README](../README.md).
> Ce qui en a été repris : le pre-roll audio, Open-Meteo, les règles de rédaction
> orale, et les analyses de latence et de vie privée.

> Ce document existe pour attaquer le projet avant que la réalité ne le fasse.
> Chaque point liste : le problème, pourquoi il tue le projet, la parade retenue.

---

## 1.1 Le Raspberry Pi 1B+ est le mauvais appareil pour du wake word local

C'est le risque n°1 et il conditionne tout le reste.

| Contrainte | Pi 1B+ | Ce qu'il faudrait |
|---|---|---|
| CPU | ARM1176JZF-S, **ARMv6**, 1 cœur, 700 MHz | ARMv7/aarch64 multi-cœur |
| RAM | 512 Mo (partagée avec le GPU) | ≥ 512 Mo utile |
| NEON (SIMD) | **absent** | présent (toutes les libs d'inférence l'assument) |
| Wi-Fi | absent | intégré |
| Audio in | **absent** | micro |

Conséquence concrète : **l'écosystème moderne de wake word ne fonctionne pas sur ARMv6.**
`onnxruntime` ne publie même pas de roue pour ARM32v7 ; `tflite-runtime` publie
`linux_amd64`, `linux_arm64`, `darwin_arm64`, `windows_amd64` — pas d'armhf.
Donc openWakeWord, microWakeWord, Silero : hors jeu sans cross-compilation lourde,
et même une fois compilés, 700 MHz sans NEON pour tourner en permanence sur un flux
16 kHz, c'est optimiste au mieux.

**Parade retenue — la seule décision d'architecture qui compte :**
le client est **volontairement stupide et remplaçable**. Il capture, détecte de la
parole, encode, envoie, joue. Rien d'autre. Toute l'intelligence est derrière un
contrat réseau versionné (`docs/03-protocole.md`).

Bénéfices :
- le Pi 1B+ devient un satellite audio, un rôle qu'il peut tenir ;
- si le wake word local ne passe pas, on le déporte sur le serveur sans toucher au serveur ;
- le jour où ça coince pour de bon, un **Pi Zero 2 W (~20 €, ARMv7/aarch64, Wi-Fi intégré)**
  est un remplacement à l'identique — même binaire à recompiler, même protocole ;
- on peut avoir 3 satellites dans la maison sans changer une ligne côté serveur.

**Ce qu'il ne faut surtout pas faire :** écrire un monolithe Python sur le Pi qui fait
wake word + VAD + appels API + logique métier. C'est le chemin le plus court vers un
projet abandonné dans 3 semaines.

---

## 1.2 Le bus USB du Pi 1B+ va saboter ton audio (piège peu connu)

Sur le Pi 1B+, **l'Ethernet passe par l'USB** (puce LAN9514 : hub USB + Ethernet
sur le même contrôleur). Ce contrôleur, le DWC OTG, est réputé pour ses problèmes
d'ordonnancement isochrone. Si tu branches sur le même bus : carte son USB + dongle
Wi-Fi USB + Ethernet interne, tu obtiens des **coupures audio (xruns)** à la capture,
qui détruisent le wake word et l'ASR — et tu passeras des soirées à croire que ton
modèle est mauvais alors que c'est le bus USB.

Parades :
- **Privilégier l'Ethernet ou le CPL** plutôt qu'un dongle Wi-Fi USB : moins de trafic
  concurrent sur le bus, et l'Ethernet est déjà là.
- Buffers ALSA généreux (période ~40 ms, buffer ~200 ms) : on préfère 200 ms de latence
  à un xrun.
- **Hub USB auto-alimenté** si plus de 2 périphériques (polyfuse 1,2 A partagé pour les 4 ports).
- Instrumenter les xruns dès la Phase 0 (`/proc/asound/card*/pcm*/sub*/status`) et en faire
  une métrique remontée au serveur. Si ça dérape, on le sait au lieu de le deviner.

---

## 1.3 « Recherche Google » n'est pas une brique d'architecture

Ton exemple — *« quelle température maximum demain ? » → recherche Google* — est le
bon cas d'usage mais la mauvaise implémentation.

Problèmes : scraper Google est contraire à ses CGU, casse sans prévenir, ajoute 1–3 s
de latence, et surtout il faut ensuite *extraire* la réponse d'une page HTML — donc un
LLM, donc encore de la latence, pour une donnée que tu peux obtenir structurée.

**Parade : hiérarchie de sources.**

1. **API structurée dédiée** quand elle existe. Pour la météo : **Open-Meteo**, gratuit,
   **sans clé API**, retourne directement `daily.temperature_2m_max` et un code météo.
   Réponse déterministe en ~200 ms, formatable sans LLM.
2. **API de recherche web propre** (Brave Search API, Tavily) pour les questions ouvertes
   — pas de scraping, résultats en JSON, CGU claires.
3. **LLM avec tool-calling** uniquement comme chef d'orchestre au-dessus, pas comme
   lecteur de pages web.

Le web search est un *repli*, pas le moteur principal.

---

## 1.4 Ne mets pas un LLM sur le chemin critique de toutes les requêtes

Tu dis « automatiser des tâches **récurrentes** ». Les tâches récurrentes sont, par
définition, connues à l'avance. Les faire passer par un LLM, c'est payer 800 ms et
0,003 € pour reconnaître « éteins la lumière du salon ».

**Parade : routeur à deux étages.**

- **Étage 1 — déterministe.** Règles / regex normalisées + correspondance floue sur les
  entités (pièces, appareils, villes). Couvre 80–90 % des usages réels d'un assistant
  domestique. Latence < 20 ms, coût 0 €, comportement prévisible, testable en CI, marche
  même si l'API LLM est down.
- **Étage 2 — LLM avec tool-calling.** Repli quand l'étage 1 ne matche pas, avec un score
  de confiance minimal. Il ne « répond » pas librement : il **choisit un outil** parmi ceux
  exposés, et c'est le code qui exécute.

Bonus décisif : chaque phrase non matchée par l'étage 1 mais résolue par l'étage 2 est
loggée. C'est ton backlog gratuit de nouvelles règles déterministes.

---

## 1.5 La latence perçue tuera le projet avant la précision

Un assistant qui répond juste en 6 secondes est inutilisable ; un assistant qui répond
en 1,5 s avec 90 % de justesse est utilisé tous les jours. **Optimise la latence, pas
le taux de reconnaissance.**

Budget cible, mesuré à partir de la **fin de parole de l'utilisateur** :

| Étape | Intent déterministe | Repli LLM |
|---|---|---|
| Détection de fin de parole (endpointing) | 500–700 ms | 500–700 ms |
| Fin d'upload (déjà streamé) | 50–150 ms | 50–150 ms |
| Finalisation ASR (streaming) | 200–500 ms | 200–500 ms |
| Routage | < 20 ms | 600–1500 ms |
| Appel outil (ex. Open-Meteo) | 100–400 ms | 100–400 ms |
| Premier chunk TTS | 150–400 ms | 150–400 ms |
| Réseau + buffer Pi | ~150 ms | ~150 ms |
| **Premier son entendu** | **≈ 1,2–1,9 s** | **≈ 2,0–3,5 s** |

Règles non négociables qui découlent de ce budget :

- **Tout est en streaming.** L'audio monte pendant que l'utilisateur parle, l'ASR
  transcrit en continu, le TTS redescend par chunks joués au fur et à mesure. Jamais de
  « j'attends le fichier complet ».
- **Earcon immédiat.** Un petit « bip » joué **localement** dans les 100 ms suivant la
  détection du wake word, sans aucun aller-retour réseau. C'est la parade psychologique
  la plus rentable du projet : l'utilisateur sait qu'il a été entendu, et perçoit
  l'ensemble comme réactif même si la réponse arrive à 2 s.
- **Filler audio** optionnel (« je regarde… ») uniquement si l'outil dépasse 800 ms.
- **Endpointing agressif mais adaptatif** : 600 ms de silence par défaut, allongé si la
  transcription partielle finit sur un mot manifestement incomplet.

---

## 1.6 Vie privée : c'est une décision, pas un détail

Ton audio va sortir de ta maison. Il faut le décider consciemment, pas le subir.

| Option | Vie privée | Qualité FR | Coût | Verdict |
|---|---|---|---|---|
| ASR cloud (Deepgram, OpenAI, Google) | audio chez un tiers | excellente | ~0,004 €/min | Repli |
| **ASR auto-hébergé (faster-whisper) sur ton PC fixe** | **reste chez toi** | très bonne (`small`/`medium` fr) | 0 € | **Recommandé** |
| ASR sur le Pi | parfait | impossible sur ARMv6 | — | Exclu |

Puisque tu envisages déjà **ton PC fixe** comme serveur, c'est l'argument décisif :
avec un GPU même modeste, `faster-whisper small` en français tourne largement plus vite
que le temps réel, gratuitement, et **l'audio ne quitte jamais le réseau local**. Idem
pour le TTS avec **Piper** (voix françaises, local, rapide).

Le seul flux sortant devient alors les appels d'outils (météo, recherche) et, si tu
l'actives, l'étage 2 LLM — et là c'est du **texte**, pas de la voix.

Contrepartie honnête : ton PC fixe doit être allumé. Si ce n'est pas le cas, il faut un
VPS, et le VPS CPU-only rend whisper lent → tu bascules sur du cloud ASR. **Ce choix
d'hébergement détermine ta stack ASR/TTS, décide-le en Phase 0.**

---

## 1.7 Sécurité : n'ouvre pas de port sur ta box

Un service qui reçoit du micro en continu, exposé sur Internet via un port forwarding,
est exactement ce qu'il ne faut pas faire.

Parades :
- **Tailscale** (le plus simple : réseau privé chiffré, zéro config routeur, gratuit en
  usage perso) ou **Cloudflare Tunnel**. Le serveur n'a aucun port ouvert.
- **Token par appareil** (`Authorization: Bearer <device_token>`), révocable individuellement,
  stocké en `0600` sur le Pi, jamais dans Git.
- **TLS obligatoire** même sur le LAN. Le Pi 1B+ tient largement TLS pour un WebSocket
  long (le coût est au handshake, pas au débit).
- Rate limiting par appareil côté serveur : un satellite qui déraille ne doit pas pouvoir
  brûler ton quota d'API.
- Toute skill qui a un effet dans le monde réel (chauffage, serrure, achat) passe par une
  **liste blanche explicite** et, si tu vas jusque-là, une confirmation vocale.

---

## 1.8 L'assistant va s'entendre lui-même

Sans annulation d'écho acoustique (AEC), le micro capte le haut-parleur : l'assistant se
réveille tout seul et se transcrit lui-même. Implémenter un AEC correct est un projet
en soi, et sûrement pas sur ARMv6.

**Parade v1 : half-duplex.** Micro coupé pendant la lecture, avec ~200 ms de garde après
la fin du son. Simple, robuste, et le coût est de ne pas pouvoir interrompre l'assistant
en parlant (« barge-in »). C'est un compromis parfaitement acceptable en v1 — et si le
barge-in devient indispensable, la vraie réponse est un **micro USB avec AEC matériel**
(type speakerphone de conférence), pas du code.

---

## 1.9 La qualité du micro décide de 80 % du résultat

Aucun modèle ne rattrape un micro à 4 € posé derrière un meuble. Avant d'accuser ton
wake word ou ton ASR, mesure ton audio.

- Micro **omnidirectionnel** ou réseau 2 micros, placé **en hauteur et dégagé**.
- Vise un RMS correct à 3 m sans saturation ; règle les gains avec `alsamixer` **une fois**
  et fige-les dans `asound.conf`.
- Un **speakerphone USB** (micro + HP + parfois AEC dans un seul boîtier) résout d'un coup
  le micro, la sortie audio et le nombre de ports USB. C'est le meilleur rapport
  qualité/effort ici.
- La sortie jack 3,5 mm du Pi 1B+ est de mauvaise qualité (PWM, partagée avec la vidéo
  composite, bruit de fond audible) : **ne l'utilise pas**, passe par l'USB.

---

## 1.10 Le piège du « faux Alexa » : le périmètre

Vouloir égaler Alexa, c'est garantir l'échec. La v1 doit faire **peu de choses,
parfaitement**, sur les tâches que *tu* fais réellement toutes les semaines.

Hors périmètre v1, assumé et écrit noir sur blanc :
- multi-tours et contexte conversationnel (« et après-demain ? ») ;
- reconnaissance du locuteur ;
- barge-in ;
- multi-langue ;
- multi-satellites synchronisés ;
- réponse en local sans réseau.

Écris tes 5 phrases quotidiennes réelles **avant** de coder. Elles définissent la v1.

---

## 1.11 Ça doit tourner 24/7 sur une carte SD

- **`log2ram`** ou `Storage=volatile` dans journald : les logs en écriture continue tuent
  une carte SD en quelques mois. C'est la première cause de mort d'un Pi en production.
- **`systemd`** avec `Restart=always` + `WatchdogSec` ; activer aussi le **watchdog matériel**
  (`bcm2835_wdt`) pour les vrais blocages.
- **Reconnexion réseau à backoff exponentiel** avec jitter, et bufferisation courte : une
  coupure Internet ne doit pas exiger un redémarrage.
- **Retour d'état visible** (LED GPIO ou earcons distincts) : au repos / écoute / réfléchit /
  erreur / déconnecté. Sans ça, tu ne peux rien diagnostiquer à distance.
- **Mise à jour à distance** : le binaire client est un fichier unique, un `scp` + `systemctl
  restart` suffit. Prévois-le dès le début, tu vas itérer des dizaines de fois.

---

## 1.12 Récapitulatif des risques

| # | Risque | Gravité | Parade | Vérifié en |
|---|---|---|---|---|
| R1 | Wake word local infaisable sur ARMv6 | **Critique** | Client stupide + wake word serveur ; repli Pi Zero 2 W | Phase 0 |
| R2 | Xruns audio dus au bus USB/DWC OTG | **Élevée** | Ethernet plutôt que Wi-Fi USB, gros buffers, métrique xrun | Phase 0 |
| R3 | Latence > 3 s → abandon d'usage | Élevée | Streaming bout-en-bout, earcon local, routeur déterministe | Phase 1 |
| R4 | Faux réveils / auto-réveil | Élevée | Half-duplex, seuil réglable, confirmation serveur | Phase 2 |
| R5 | PC fixe éteint → assistant mort | Moyenne | Wake-on-LAN, ou VPS + ASR cloud | Phase 0 |
| R6 | Coûts API qui dérivent | Moyenne | Routeur déterministe, quotas durs, budget mensuel plafonné | Phase 4 |
| R7 | Mort de la carte SD | Moyenne | log2ram, image de restauration prête | Phase 5 |
| R8 | Qualité micro insuffisante | Moyenne | Speakerphone USB, mesure RMS à 3 m | Phase 0 |
