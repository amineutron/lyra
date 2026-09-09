# Voix de synthèse (Piper)

Lyra parle avec [Piper](https://github.com/rhasspy/piper) (licence GPL-3.0, installé séparément par l'installeur, compatible avec l'AGPL de Lyra). Les voix viennent du dépôt [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) ; chacune a sa propre licence, indiquée ci-dessous avec son attribution.

| Voix | Qualité | Licence de la voix | Attribution |
|---|---|---|---|
| `fr_FR-upmc-medium` (défaut, locuteurs Jessica et Pierre) | medium | CC BY-SA 4.0 | jeu de données UPMC, https://github.com/marytts/upmc-pierre-data ; modèle Piper, https://huggingface.co/rhasspy/piper-voices |
| `fr_FR-siwis-medium` | medium | CC BY 4.0 | jeu de données SIWIS, https://datashare.is.ed.ac.uk/handle/10283/2353 |
| `fr_FR-mls-medium` | medium | CC BY 4.0 | Multilingual LibriSpeech, http://openslr.org/94/ |
| `fr_FR-gilles-low` | low | CC0 | https://www.kaggle.com/datasets/bryanpark/french-single-speaker-speech-dataset |
| `fr_FR-tom-medium` | medium | AGPL-3.0 | https://git.bksp.space/Tjiho/French-tts-model-piper |

Note : la voix par défaut est sous CC BY-SA 4.0 (attribution et partage à l'identique des dérivés de la voix, pas du code de Lyra) ; `tom` est sous AGPL-3.0 et n'est proposée qu'en option.

La voix par défaut installée est `fr_FR-upmc-medium`. Pour en changer : menu `/setting` ou `tts.model` dans `config.yaml`.
