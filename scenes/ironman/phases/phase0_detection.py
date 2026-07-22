"""
Phase 0 - Detection & Validation
================================

Detecte les triggers vocaux "je suis iron man" et valide que TV + Hue sont disponibles.
Sauvegarde l'etat actuel pour rollback si necessaire.

Duree: <2 secondes
"""

import json
import logging
import re
import unicodedata
import urllib3
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

import requests
import yaml

# Disable SSL warnings for TV API (self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Fichier de sauvegarde pour rollback
ROLLBACK_FILE = Path("/tmp/ironman_rollback.json")

# Triggers vocaux (normalises, sans accents, lowercase)
TRIGGERS = [
    "je suis iron man",
    "je suis tony stark",
    "je suis tony",
    "mode iron man",
    "scene iron man",
]

# Timeout pour les checks de disponibilite (secondes)
DEVICE_TIMEOUT = 2.0


def normalize_text(text: str) -> str:
    """Normalise le texte: lowercase, sans accents."""
    # Lowercase
    text = text.lower()
    # Remove accents
    normalized = unicodedata.normalize('NFD', text)
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents


class Phase0Detection:
    """
    Phase 0: Detection des triggers et validation des devices.

    Usage:
        phase0 = Phase0Detection()
        if phase0.is_trigger_detected("je suis iron man"):
            success, message, saved_state = phase0.validate_and_prepare()
            if success:
                # Lancer la scene
                pass
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialise Phase0 avec la configuration.

        Args:
            config_path: Chemin vers config.yaml (defaut: lyra/config.yaml)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

        self.config = self._load_config(config_path)
        self.tv_config = self.config.get("tv", {})
        self.hue_config = self.config.get("hue", {})

    def _load_config(self, config_path: Path) -> dict:
        """Charge config.yaml et fusionne secrets.yaml si present."""
        config = {}
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Impossible de charger config.yaml: {e}")

        secrets_path = config_path.parent / "secrets.yaml"
        if secrets_path.exists():
            try:
                with open(secrets_path, 'r') as f:
                    secrets = yaml.safe_load(f) or {}
                for section, values in secrets.items():
                    if section in config and isinstance(config[section], dict):
                        config[section].update(values)
                    else:
                        config[section] = values
            except Exception as e:
                logger.warning(f"Impossible de charger secrets.yaml: {e}")

        return config

    def is_trigger_detected(self, text: str) -> bool:
        """
        Verifie si le texte contient un trigger de la scene Iron Man.

        Args:
            text: Texte a analyser (peut etre une phrase complete)

        Returns:
            True si un trigger est detecte, False sinon
        """
        if not text:
            return False

        normalized = normalize_text(text)

        for trigger in TRIGGERS:
            if trigger in normalized:
                logger.info(f"Trigger detecte: '{trigger}' dans '{text}'")
                return True

        return False

    def check_tv_available(self) -> Tuple[bool, str]:
        """
        Teste la connectivite de la TV Philips.

        Returns:
            Tuple (success: bool, message: str)
            - (True, "") si la TV est disponible
            - (False, "message d'erreur") si la TV est indisponible
        """
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"http://{host}:1925/6/system"

        try:
            response = requests.get(url, timeout=DEVICE_TIMEOUT, verify=False)
            if response.status_code == 200:
                logger.info(f"TV Philips disponible ({host})")
                return True, ""
            else:
                msg = f"TV Philips a repondu avec code {response.status_code}"
                logger.warning(msg)
                return False, msg

        except requests.exceptions.Timeout:
            msg = f"TV Philips non disponible (timeout {DEVICE_TIMEOUT}s)"
            logger.warning(msg)
            return False, msg

        except requests.exceptions.ConnectionError as e:
            msg = f"TV Philips non disponible (connexion refusee)"
            logger.warning(f"{msg}: {e}")
            return False, msg

        except Exception as e:
            msg = f"Erreur lors du check TV: {str(e)}"
            logger.error(msg, exc_info=True)
            return False, msg

    def check_hue_available(self) -> Tuple[bool, str]:
        """
        Teste la connectivite du Bridge Hue.

        Returns:
            Tuple (success: bool, message: str)
            - (True, "") si le Bridge est disponible
            - (False, "message d'erreur") si le Bridge est indisponible
        """
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            msg = "Configuration Hue manquante (username)"
            logger.warning(msg)
            return False, msg

        url = f"http://{bridge_ip}/api/{username}/lights"

        try:
            response = requests.get(url, timeout=DEVICE_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                # Verifier que ce n'est pas une erreur Hue
                if isinstance(data, list) and len(data) > 0 and "error" in data[0]:
                    msg = f"Bridge Hue erreur: {data[0]['error'].get('description', 'unknown')}"
                    logger.warning(msg)
                    return False, msg

                logger.info(f"Bridge Hue disponible ({bridge_ip})")
                return True, ""
            else:
                msg = f"Bridge Hue a repondu avec code {response.status_code}"
                logger.warning(msg)
                return False, msg

        except requests.exceptions.Timeout:
            msg = f"Bridge Hue non disponible (timeout {DEVICE_TIMEOUT}s)"
            logger.warning(msg)
            return False, msg

        except requests.exceptions.ConnectionError as e:
            msg = f"Bridge Hue non disponible (connexion refusee)"
            logger.warning(f"{msg}: {e}")
            return False, msg

        except Exception as e:
            msg = f"Erreur lors du check Hue: {str(e)}"
            logger.error(msg, exc_info=True)
            return False, msg

    def _get_tv_state(self) -> dict:
        """Recupere l'etat actuel de la TV."""
        host = self.tv_config.get("host", "192.168.1.50")
        user = self.tv_config.get("user", "")
        password = self.tv_config.get("pass", "")

        state = {
            "power": "unknown",
            "volume": 0,
            "muted": False,
            "app": None,
            "ambilight": None,
        }

        try:
            auth = (user, password) if user and password else None

            # Check power state via powerstate endpoint
            url = f"https://{host}:1926/6/powerstate"
            response = requests.get(url, auth=auth, timeout=DEVICE_TIMEOUT, verify=False)
            if response.status_code == 200:
                data = response.json()
                state["power"] = data.get("powerstate", "unknown")

            # Get volume
            url = f"https://{host}:1926/6/audio/volume"
            response = requests.get(url, auth=auth, timeout=DEVICE_TIMEOUT, verify=False)
            if response.status_code == 200:
                data = response.json()
                state["volume"] = data.get("current", 0)
                state["muted"] = data.get("muted", False)

            # Get current app (activities)
            url = f"https://{host}:1926/6/activities/current"
            response = requests.get(url, auth=auth, timeout=DEVICE_TIMEOUT, verify=False)
            if response.status_code == 200:
                data = response.json()
                pkg = data.get("component", {}).get("packageName")
                if pkg:
                    state["app"] = pkg

            # Get ambilight configuration
            url = f"https://{host}:1926/6/ambilight/currentconfiguration"
            response = requests.get(url, auth=auth, timeout=DEVICE_TIMEOUT, verify=False)
            if response.status_code == 200:
                state["ambilight"] = response.json()

        except Exception as e:
            logger.warning(f"Impossible de recuperer l'etat TV complet: {e}")

        return state

    def _get_hue_state(self) -> dict:
        """Recupere l'etat actuel des lumieres Hue."""
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        state = {
            "lights": {},
            "group_81": {"scene": None},
        }

        if not username:
            return state

        try:
            # Get all lights state
            url = f"http://{bridge_ip}/api/{username}/lights"
            response = requests.get(url, timeout=DEVICE_TIMEOUT)
            if response.status_code == 200:
                lights = response.json()
                for light_id, light_data in lights.items():
                    # Only save lights 1-5 (chambre)
                    if light_id in ["1", "2", "3", "4", "5"]:
                        light_state = light_data.get("state", {})
                        state["lights"][light_id] = {
                            "on": light_state.get("on", False),
                            "brightness": light_state.get("bri", 0),
                            "xy": light_state.get("xy", [0.0, 0.0]),
                            "ct": light_state.get("ct"),
                            "colormode": light_state.get("colormode", "xy"),
                        }

            # Try to get active scene for group 81
            url = f"http://{bridge_ip}/api/{username}/groups/81"
            response = requests.get(url, timeout=DEVICE_TIMEOUT)
            if response.status_code == 200:
                group_data = response.json()
                # Scene is not directly available in group state
                # but we save the action state as reference
                action = group_data.get("action", {})
                state["group_81"]["action"] = {
                    "on": action.get("on", False),
                    "bri": action.get("bri", 0),
                }

        except Exception as e:
            logger.warning(f"Impossible de recuperer l'etat Hue complet: {e}")

        return state

    def save_current_state(self) -> dict:
        """
        Recupere et sauvegarde l'etat actuel de la TV et des lumieres Hue.

        Le fichier est sauvegarde dans /tmp/ironman_rollback.json pour
        permettre une restauration en cas d'erreur.

        Returns:
            Le dictionnaire de l'etat sauvegarde
        """
        state = {
            "timestamp": datetime.now().isoformat(),
            "tv": self._get_tv_state(),
            "hue": self._get_hue_state(),
        }

        try:
            with open(ROLLBACK_FILE, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info(f"Etat sauvegarde dans {ROLLBACK_FILE}")
        except Exception as e:
            logger.error(f"Impossible de sauvegarder l'etat: {e}")

        return state

    def validate_and_prepare(self) -> Tuple[bool, str, dict]:
        """
        Fonction principale qui orchestre la Phase 0.

        1. Verifie la disponibilite de la TV Philips
        2. Verifie la disponibilite du Bridge Hue
        3. Sauvegarde l'etat actuel pour rollback

        Returns:
            Tuple (success: bool, message: str, saved_state: dict)
            - success: True si tout est pret
            - message: Message d'erreur ou de succes
            - saved_state: Etat sauvegarde (vide si echec)
        """
        logger.info("Phase 0: Validation et preparation")

        # Check TV
        tv_ok, tv_msg = self.check_tv_available()
        if not tv_ok:
            return False, tv_msg, {}

        # Check Hue
        hue_ok, hue_msg = self.check_hue_available()
        if not hue_ok:
            return False, hue_msg, {}

        # Save state for rollback
        saved_state = self.save_current_state()

        logger.info("Phase 0: Validation complete, pret pour la scene")
        return True, "Pret pour la scene Iron Man", saved_state


def load_rollback_state() -> Optional[dict]:
    """
    Charge l'etat de rollback depuis le fichier.

    Returns:
        Le dictionnaire de l'etat ou None si non disponible
    """
    try:
        if ROLLBACK_FILE.exists():
            with open(ROLLBACK_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Impossible de charger l'etat de rollback: {e}")
    return None
