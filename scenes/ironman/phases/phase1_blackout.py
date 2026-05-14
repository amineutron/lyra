"""
Phase 1 - Blackout Dramatique
=============================

Eteint toutes les lumieres et la TV, puis attend 3 secondes dans le noir total.
Cree la tension initiale de la scene Iron Man.

Timeline:
    T+0.0s: Extinction lumieres + TV
    T+0.0s → T+3.0s: Attente noir complet
    T+3.0s: Phase terminee

Duree: 3.0 secondes exactement
"""

import logging
import time
import urllib3
from typing import Tuple

import requests
from requests.auth import HTTPDigestAuth
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

# Disable SSL warnings for TV API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Duree du blackout en secondes
BLACKOUT_DURATION = 3.0

# Latence max acceptable pour extinction (ms)
MAX_EXTINCTION_LATENCY_MS = 500

# Timeout pour les requetes API (secondes)
API_TIMEOUT = 2.0


class Phase1Blackout:
    """
    Phase 1: Blackout dramatique - noir total pendant 3 secondes.

    Usage:
        phase1 = Phase1Blackout()
        result = phase1.execute()
        # result = {"success": True, "lights_off": True, "tv_off": True, "duration": 3.01}
    """

    def __init__(self, config_path: Path = None):
        """
        Initialise Phase1 avec la configuration.

        Args:
            config_path: Chemin vers config.yaml (defaut: lyra/config.yaml)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

        self.config = self._load_config(config_path)
        self.tv_config = self.config.get("tv", {})
        self.hue_config = self.config.get("hue", {})

    def _load_config(self, config_path: Path) -> dict:
        """Charge la configuration depuis config.yaml."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Impossible de charger config.yaml: {e}")
            return {}

    def _turn_off_lights(self) -> Tuple[bool, float]:
        """
        Eteint toutes les lumieres du groupe 81 (chambre).

        Returns:
            Tuple (success: bool, latency_ms: float)
        """
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            logger.warning("Configuration Hue manquante (username)")
            return False, 0.0

        url = f"http://{bridge_ip}/api/{username}/groups/81/action"
        payload = {"on": False, "transitiontime": 0}  # 0 = instantane

        start = time.perf_counter()
        try:
            response = requests.put(url, json=payload, timeout=API_TIMEOUT)
            latency_ms = (time.perf_counter() - start) * 1000

            if response.status_code == 200:
                logger.info(f"Lumieres eteintes (latence: {latency_ms:.0f}ms)")
                if latency_ms > MAX_EXTINCTION_LATENCY_MS:
                    logger.warning(f"Latence extinction > {MAX_EXTINCTION_LATENCY_MS}ms")
                return True, latency_ms
            else:
                logger.warning(f"Erreur extinction lumieres: HTTP {response.status_code}")
                return False, latency_ms

        except requests.exceptions.Timeout:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning(f"Timeout extinction lumieres ({latency_ms:.0f}ms)")
            return False, latency_ms

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning(f"Erreur extinction lumieres: {e}")
            return False, latency_ms

    def _get_tv_auth(self):
        """Retourne l'auth HTTPDigest pour la TV."""
        user = self.tv_config.get("user", "")
        password = self.tv_config.get("pass", "")
        if user and password:
            return HTTPDigestAuth(user, password)
        return None

    def _check_tv_power(self) -> str:
        """
        Verifie l'etat d'alimentation de la TV.

        Returns:
            "On", "Standby", ou "unknown"
        """
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"https://{host}:1926/6/powerstate"

        try:
            response = requests.get(url, auth=self._get_tv_auth(), timeout=API_TIMEOUT, verify=False)
            if response.status_code == 200:
                return response.json().get("powerstate", "unknown")
        except Exception as e:
            logger.debug(f"Check TV power: {e}")

        return "unknown"

    def _turn_off_tv(self) -> Tuple[bool, str]:
        """
        Eteint la TV si elle est allumee.

        Returns:
            Tuple (success: bool, action: str)
            - action: "off", "skipped", ou "error"
        """
        # Check current state
        power_state = self._check_tv_power()

        if power_state == "Standby":
            logger.info("TV deja en veille, skip")
            return True, "skipped"

        if power_state == "unknown":
            # On essaie quand meme d'eteindre
            logger.debug("Etat TV inconnu, tentative extinction")

        # Send power off
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"https://{host}:1926/6/powerstate"
        payload = {"powerstate": "Standby"}

        try:
            response = requests.put(url, json=payload, auth=self._get_tv_auth(), timeout=API_TIMEOUT, verify=False)
            if response.status_code == 200:
                logger.info("TV eteinte")
                return True, "off"
            else:
                logger.warning(f"Erreur extinction TV: HTTP {response.status_code}")
                return False, "error"

        except requests.exceptions.Timeout:
            logger.warning("Timeout extinction TV")
            return False, "error"

        except Exception as e:
            logger.warning(f"Erreur extinction TV: {e}")
            return False, "error"

    def execute(self) -> dict:
        """
        Execute la Phase 1: Blackout dramatique.

        1. Eteint toutes les lumieres (instantane)
        2. Eteint la TV si allumee
        3. Attend 3 secondes dans le noir

        Returns:
            dict avec:
                - success: bool (True si au moins une action reussie)
                - lights_off: bool
                - tv_off: bool (True si eteinte ou skipped)
                - tv_action: str ("off", "skipped", "error")
                - duration: float (duree reelle en secondes)
                - latency_ms: float (latence extinction lumieres)
        """
        logger.info("Phase 1: BLACKOUT - Debut")
        phase_start = time.perf_counter()

        # Extinction simultanee lumieres + TV
        extinction_start = time.perf_counter()

        lights_ok, latency_ms = self._turn_off_lights()
        tv_ok, tv_action = self._turn_off_tv()

        extinction_time = (time.perf_counter() - extinction_start) * 1000
        logger.debug(f"Extinction complete en {extinction_time:.0f}ms")

        # Calcul du temps restant pour atteindre exactement 3s
        elapsed = time.perf_counter() - phase_start
        remaining = BLACKOUT_DURATION - elapsed

        if remaining > 0:
            logger.debug(f"Attente noir total: {remaining:.2f}s")
            time.sleep(remaining)

        # Duree totale
        duration = time.perf_counter() - phase_start

        # Verification tolerance (±50ms)
        if abs(duration - BLACKOUT_DURATION) > 0.05:
            logger.warning(f"Duree blackout hors tolerance: {duration:.3f}s (cible: {BLACKOUT_DURATION}s)")

        logger.info(f"Phase 1: BLACKOUT - Fin (duree: {duration:.2f}s)")

        return {
            "success": lights_ok or tv_ok,  # Au moins une action reussie
            "lights_off": lights_ok,
            "tv_off": tv_ok,
            "tv_action": tv_action,
            "duration": duration,
            "latency_ms": latency_ms,
        }
