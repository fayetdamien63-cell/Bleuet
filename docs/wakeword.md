# Mot de réveil « Dis Bleuet »

**Pour le MVP, on reste sur `hey_jarvis`**, un modèle standard de la bibliothèque :
il fonctionne immédiatement, sans entraînement, et permet de valider le pipeline
tout de suite. Ce document décrit l'étape d'après.

openWakeWord fournit des modèles pré-entraînés en anglais uniquement
(`hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`…). Pour un mot de réveil
français il faut entraîner son propre modèle — c'est prévu par le projet et ça
ne demande pas de données enregistrées à la main.

## Principe

openWakeWord s'entraîne sur de l'audio **synthétique** : un TTS génère quelques
milliers de prononciations variées de « Dis Bleuet », mélangées à du bruit de
fond et à des négatifs (parole quelconque). Le modèle produit est un `.onnx` de
quelques centaines de kilo-octets qui tourne sans peine sur un Pi 3.

## Marche à suivre

1. Ouvre le notebook officiel d'entraînement automatique :
   <https://github.com/dscripka/openWakeWord#training-new-models> → lien
   « automatic model training » (Google Colab, GPU gratuit, ~1 h).
2. Renseigne le mot cible : `dis bleuet`. Ajoute quelques variantes de
   prononciation si le mot est ambigu (`di bleuet`, `dis bleuette`).
3. Lance toutes les cellules. Le notebook télécharge les jeux de données de
   bruit, génère les positifs, entraîne, puis propose le `.onnx` au téléchargement.
4. Place le fichier dans `data/models/dis_bleuet.onnx`.
5. Dans `config/config.yaml` :

   ```yaml
   wakeword:
     model_path: data/models/dis_bleuet.onnx
     threshold: 0.5
   ```

6. Teste : `bleuet wakeword`, puis ajuste `threshold`.

## Régler le seuil

- Trop de déclenchements intempestifs → monte le seuil (0.6, 0.7).
- Le mot n'est pas reconnu → descends (0.4), ou ré-entraîne avec plus de
  variantes de prononciation.
- Un seuil fiable en journée peut devenir bruyant le soir (télévision) :
  `wakeword.vad_threshold: 0.5` ajoute un filtre de détection de voix, au prix
  d'un peu de CPU.

## Autres modèles standards

Si « hey jarvis » ne te convient pas à l'oral, la bibliothèque en fournit
d'autres, tout aussi immédiats : `alexa`, `hey_mycroft`, `hey_rhasspy`. Une
ligne dans `config/config.yaml` suffit :

```yaml
wakeword:
  pretrained_model: hey_mycroft
```

Le code charge indifféremment un modèle pré-entraîné ou un `.onnx` maison :
basculer vers « Dis Bleuet » le jour venu ne demandera aucune modification de code.
