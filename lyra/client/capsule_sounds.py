"""Branchement des sons de la capsule sur le client vocal.

Le client vocal (modules/audio.py::VoiceInterface, lance par main_rag.py
--vocal) est un client standalone : il n'y a pas de messages du demon a
traduire, les evenements sont emis aux points d'appel du client.

Correspondance evenement -> son (ids de lyra.client.sounds.SOUND_IDS) :
  listen_start  debut de l'ecoute (VoiceInterface.listen, remplace le bip)
  listen_end    fin de l'enregistrement, avant la transcription
  speak_start   juste avant la synthese (VoiceInterface.speak, sauf si un
                signal plus precis est passe via cue=)
  ask           question ouverte (arguments manquants, confirmation vocale)
  confirm       confirmation d'une action (non dangereuse)
  warn          confirmation d'une action dangereuse
  success       action terminee sans erreur
  error         action en echec (journal d'erreur ecrit)
  cancel        action annulee
  thinking      API prete, desactive par defaut, aucune source pour l'instant
  choice, pin   API prete (VoiceInterface.cue("choice")), aucune source :
                pas de message demon ni d'interaction cliente correspondante

Configuration : bloc `capsule.sounds.*` de config.yaml, lu directement
(le module capsule_settings.py n'existe que dans feat/capsule-protocol ; apres
fusion, remplacer load_sound_config par `capsule_settings().sounds`).
Un son ne bloque ni ne fait jamais echouer le client : tout est journalise.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path

from lyra.client.sounds import SOUND_IDS, SoundConfig, SoundPlayer

log = logging.getLogger(__name__)

# Tout actif sauf `thinking` (boucle potentiellement longue : opt-in).
DEFAULT_EVENTS: dict[str, bool] = {
    **{event_id: True for event_id in SOUND_IDS},
    "thinking": False,
}

# Pause apres listen_start : le micro ne doit pas enregistrer le son lui-meme
# (listen_start.wav dure 0.36 s).
LISTEN_SETTLE_S = 0.4


def build_sound_config(cfg: Mapping | None) -> SoundConfig:
    """SoundConfig depuis le dict YAML complet (config.yaml), tolerant."""
    capsule = cfg.get("capsule") if isinstance(cfg, Mapping) else None
    raw = capsule.get("sounds") if isinstance(capsule, Mapping) else None
    raw = dict(raw) if isinstance(raw, Mapping) else {}
    user_events = raw.get("events")
    events = dict(DEFAULT_EVENTS)
    if isinstance(user_events, Mapping):
        for key, value in user_events.items():
            if key in DEFAULT_EVENTS:
                events[key] = bool(value)
    return SoundConfig.from_mapping({**raw, "events": events})


def load_sound_config(config_path: str | Path = "config.yaml") -> SoundConfig:
    """Lit capsule.sounds.* ; fichier absent ou invalide -> valeurs par defaut."""
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as exc:  # fichier absent, YAML invalide...
        log.debug("config des sons illisible (%s) : valeurs par defaut", exc)
        cfg = None
    return build_sound_config(cfg)


def make_player(cfg: Mapping | None) -> SoundPlayer | None:
    """SoundPlayer pret, ou None si les sons sont desactives (ou echec)."""
    try:
        config = build_sound_config(cfg)
        return SoundPlayer(config) if config.enabled else None
    except Exception as exc:
        log.warning("sons de la capsule indisponibles : %s", exc)
        return None


def play_cue(player: SoundPlayer | None, event_id: str) -> bool:
    """Joue `event_id` sans jamais lever ; True si un lecteur a demarre."""
    if player is None:
        return False
    try:
        return bool(player.play(event_id))
    except Exception as exc:
        log.warning("son %s non joue : %s", event_id, exc)
        return False


def settle_after_listen_start(played: bool, sleep=time.sleep) -> None:
    """Laisse finir le son de debut d'ecoute avant d'ouvrir le micro."""
    if played:
        sleep(LISTEN_SETTLE_S)
