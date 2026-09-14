# 4. Plan d'implémentation

Chaque phase a une **définition de terminé** vérifiable. On ne passe pas à la suivante
sans elle. La Phase 0 a en plus un **critère d'abandon** : c'est ce qui t'évite de
découvrir dans 6 semaines que le matériel ne suivait pas.

---

## Phase 0 — Spike matériel · **Go / No-Go** (1 week-end)

> Objectif : répondre à « est-ce que ce Pi peut faire le job ? » **avant** d'écrire
> l'application. Aucune ligne d'architecture ici, uniquement des mesures.

### Décision préalable à trancher
**Où tourne le serveur ?** PC fixe allumé en permanence → faster-whisper + Piper en local,
audio qui ne sort pas de chez toi, coût 0 €. Sinon VPS → ASR/TTS cloud. Ce choix
détermine ta stack, la Phase 3 en dépend.

### Mesures à faire
1. **Capture 30 min en continu** en 16 kHz mono, compter les xruns
   (`/proc/asound/card*/pcm*/sub*/status`). Cible : **0 xrun**, avec et sans trafic réseau.
2. **CPU** de `capture + encodage Opus 24 kbps` en régime permanent. Cible : **< 25 %**.
3. **Qualité micro** : enregistre la même phrase à 1 m, 3 m et 5 m, avec le lave-vaisselle
   en marche. Écoute-les. Si tu ne comprends pas toi-même, aucun modèle ne comprendra.
4. **RTT** Pi → serveur via le tunnel. Cible : **< 30 ms** en LAN, **< 60 ms** via VPS.
5. **Wake word local** : tenter Porcupine sur ARMv6 (les plateformes annoncées listent
   « Raspberry Pi Zero » sans préciser l'architecture — **à vérifier, ne rien construire
   dessus avant preuve**). Mesurer le CPU en veille permanente. Cible : **< 35 %**.
6. **Latence aller-retour audio nue** : Pi → serveur (echo) → Pi. Cible : **< 250 ms**.

### Critères
- **GO** si 1, 2, 4, 6 passent. Le point 5 est un bonus : s'il échoue, le wake word part
  côté serveur, l'architecture ne bouge pas.
- **NO-GO** si les xruns persistent malgré Ethernet + gros buffers, ou si le RTT dépasse
  150 ms. → **commande un Pi Zero 2 W (~20 €)** et continue le plan à l'identique.
  Ce n'est pas un échec, c'est 20 € pour éviter deux mois de frustration.

### Livrables
`tools/spike_capture.sh`, `tools/spike_rtt.py`, et un `docs/00-mesures-phase0.md`
avec les chiffres réels. Ce fichier te resservira à chaque régression.

---

## Phase 1 — Squelette bout en bout (~1 semaine)

**Objectif : « Hey Bleuet » est désactivé, un appui sur Entrée déclenche le tour.**
On valide la plomberie, pas l'intelligence.

- Client Go : capture → Opus → WebSocket ; réception → lecture ; machine à états ; earcons.
- Serveur : gateway WebSocket + auth par token ; ASR branché ; **une seule skill** (`quelle heure est-il`) ;
  TTS branché ; télémétrie des latences par étape.
- Tunnel Tailscale opérationnel, aucun port ouvert sur la box.
- `systemd` + `Restart=always` sur le Pi.

**Terminé quand :** tu appuies sur Entrée, tu dis « quelle heure est-il », tu entends
l'heure en français, et le serveur a loggé les 6 latences intermédiaires.
Cible : **< 2 s** entre la fin de ta phrase et le premier son.

---

## Phase 2 — Wake word « Hey Bleuet » (~1 semaine)

- Entraîner un modèle **openWakeWord** sur « Hey Bleuet » (échantillons synthétiques
  générés par TTS + tes propres enregistrements + bruit de fond de *ta* maison).
- Déploiement selon le résultat de la Phase 0 :
  - **local OK** → détection sur le Pi, confirmation par le serveur sur le pre-roll ;
  - **local KO** → VAD local seul, wake word entièrement côté serveur.
- Pre-roll circulaire de 1 s côté client.
- Half-duplex : micro coupé pendant `SPEAKING` + 200 ms de garde.

**Terminé quand :** sur **8 h d'usage domestique normal**, ≤ 1 faux réveil, et ≥ 9 réveils
sur 10 tentatives volontaires à 3 m. Note ces deux chiffres, ce sont tes métriques de
référence pour toujours.

---

## Phase 3 — Ton cas d'usage réel : la météo (~3 jours)

- Skill `meteo_previsions` sur **Open-Meteo** (aucune clé API).
- Géocodage via l'API de géocodage Open-Meteo, avec un **domicile par défaut** configuré
  pour éviter « à Clermont-Ferrand » dans chaque phrase.
- Routeur étage 1 : règles pour « température max/min », « il va pleuvoir », « météo demain ».
- Formatage vocal : « Demain la température maximale sera de trente-six degrés, avec un
  grand soleil. » Mapping des codes WMO vers du français parlé, **testé unitairement**.
- Cache 30 min : ne pas taper l'API 40 fois par jour pour la même chose.

**Terminé quand :** ton exemple exact fonctionne, en **< 1,8 s**, sans passer par un LLM.

---

## Phase 4 — Routeur LLM + tool calling (~1 semaine)

- Étage 2 : LLM avec les schémas d'outils générés automatiquement depuis le registre de skills.
- Prompt système imposant les règles de style oral (§ 2.4).
- Skill `recherche_web` via **Brave Search API** ou **Tavily** — pas de scraping Google.
- **Garde-fous** : timeout dur 4 s, budget mensuel plafonné, journalisation de chaque
  appel avec son coût.
- **Boucle d'amélioration** : chaque phrase résolue par l'étage 2 est loggée ; celles qui
  reviennent souvent deviennent des règles d'étage 1. Ton système devient plus rapide et
  moins cher avec le temps.

**Terminé quand :** « Hey Bleuet, c'est quoi la capitale de la Mongolie ? » répond
correctement, et « quelle température demain ? » ne touche **toujours pas** le LLM.

---

## Phase 5 — Fiabilité 24/7 (~4 jours)

- `log2ram` + `journald` en volatile.
- Watchdog systemd + watchdog matériel `bcm2835_wdt`.
- Reconnexion à backoff exponentiel + jitter, testée en débranchant réellement le câble.
- Petit tableau de bord : latences p50/p95, taux de faux réveils, xruns, coût du mois.
- `make deploy` = build ARMv6 + scp + restart. Une commande.
- Image SD de restauration sauvegardée. Tu la remercieras.

**Terminé quand :** 7 jours d'uptime sans intervention manuelle, coupure réseau et
redémarrage serveur inclus.

---

## Phase 6 — Les vraies tâches récurrentes (continu)

C'est seulement ici que le projet devient utile au quotidien. Skills candidates :
minuteur / réveil, listes de courses, domotique (Home Assistant expose une API REST
propre — ne réinvente pas), radio et musique, rappels, arrosage, relevés de capteurs.

**Ne les code pas d'avance.** Ajoute une skill quand tu constates que tu demandes la
chose trois fois dans la même semaine.

---

## Ordre de priorité si tu manques de temps

Phase 0 → Phase 1 → Phase 3 → Phase 2 → Phase 5 → Phase 4 → Phase 6.

Oui, la météo (3) avant le wake word (2) : un assistant déclenché par un bouton mais qui
répond vraiment vaut mieux qu'un wake word parfait qui ne sait rien faire — et ça te
donne un truc utilisable dès la deuxième semaine.
