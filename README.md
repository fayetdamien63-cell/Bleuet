# Bleuet

Assistant vocal domestique, francophone, auto-hébergé.
Mot de réveil : **« Hey Bleuet »**.

Architecture **satellite / serveur** : un Raspberry Pi 1B+ sert de satellite audio
volontairement stupide (capture, détection de parole, streaming, lecture), toute
l'intelligence — reconnaissance vocale, routage d'intentions, skills, synthèse vocale —
tourne sur un serveur séparé (PC fixe ou VPS).

> **État du projet : conception.** Aucun code n'est encore écrit. Le plan ci-dessous est
> le livrable actuel ; il commence délibérément par une phase de mesures matérielles
> avec critère d'abandon.

## Documentation

| Document | Contenu |
|---|---|
| [1. Challenge de l'architecture](docs/01-challenge-architecture.md) | Les 12 façons dont ce projet peut échouer, et les parades retenues |
| [2. Architecture cible](docs/02-architecture.md) | Schéma, stack, justification des choix, arborescence |
| [3. Contrat client ↔ serveur](docs/03-protocole.md) | Protocole WebSocket, machine à états, format des skills |
| [4. Plan d'implémentation](docs/04-plan.md) | Phases 0 à 6 avec définitions de terminé |
| [5. Ressources](docs/05-ressources.md) | Matériel, clés API, modèles, coûts |

## En bref

- **Le Pi 1B+ est ARMv6, sans NEON, mono-cœur à 700 MHz.** L'écosystème moderne de wake
  word (onnxruntime, tflite) n'y tourne pas. La réponse n'est pas de se battre contre le
  matériel, mais de rendre le client **jetable et remplaçable** derrière un contrat réseau
  versionné. Un Pi Zero 2 W à 20 € est le plan de secours, sans réécriture.
- **Pas de scraping Google.** Météo via Open-Meteo (structuré, gratuit, sans clé API),
  recherche web via une vraie API de recherche.
- **Le LLM est un repli, pas le moteur.** Un routeur déterministe traite les tâches
  récurrentes en moins de 20 ms et pour 0 €.
- **La latence prime sur la précision.** Cible : premier son entendu en moins de 1,5 s.
- **La v1 peut tourner sans une seule clé API** si le serveur est ton PC.

## Premier pas

Lire [la Phase 0](docs/04-plan.md#phase-0--spike-matériel--go--no-go-1-week-end) et faire
les six mesures avant d'écrire la moindre ligne de code applicatif.
