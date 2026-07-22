"""
Phase 2 - Premier Impact
========================

Flash blanc aveuglant puis transition vers bleu arc reactor.
Allumage TV + lancement YouTube AC/DC + activation Ambilight.

Timeline:
    T+0.0s:  Flash blanc pur instantane
    T+0.2s:  Transition vers bleu arc reactor
    T+0.5s:  Allumer TV
    T+2.5s:  Lancer YouTube video AC/DC
    T+3.0s:  Activer Ambilight mode audio
    T+3.5s:  Phase terminee

Duree: 3.5 secondes
"""

import logging
import os
import re
import subprocess
import time
import urllib3
from pathlib import Path
from typing import Tuple

import requests
from requests.auth import HTTPDigestAuth
import yaml

logger = logging.getLogger(__name__)

# Disable SSL warnings for TV API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constantes
YOUTUBE_VIDEO_ID = "pAgnJDJN4VA"  # AC/DC - Back In Black
FLASH_DURATION = 0.2  # 200ms
BLUE_TRANSITION = 0.3  # 300ms (transition Hue = 3 * 100ms)
TV_BOOT_TIME = 2.0  # Temps de boot TV
PHASE_DURATION = 3.5  # Duree totale de la phase

# Couleurs
WHITE_RGB = (255, 255, 255)
BLUE_ARC_REACTOR_RGB = (0, 0, 255)

# Timeout API (TV lente au boot apres blackout)
API_TIMEOUT = 5.0


def rgb_to_xy(red: int, green: int, blue: int) -> Tuple[float, float]:
    """Convertit RGB en coordonnees xy pour Hue."""
    # Normaliser
    r = red / 255.0
    g = green / 255.0
    b = blue / 255.0

    # Gamma correction
    r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
    g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
    b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92

    # RGB to XYZ
    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    # XYZ to xy
    total = X + Y + Z
    if total == 0:
        return (0.0, 0.0)

    x = X / total
    y = Y / total

    return (x, y)


class Phase2Impact:
    """
    Phase 2: Premier Impact - Flash blanc + bleu arc reactor + musique.

    Usage:
        phase2 = Phase2Impact()
        result = phase2.execute()
    """

    def __init__(self, config_path: Path = None):
        """Initialise Phase2 avec la configuration."""
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

    def _get_tv_auth(self):
        """Retourne l'auth HTTPDigest pour la TV."""
        user = self.tv_config.get("user", "")
        password = self.tv_config.get("pass", "")
        if user and password:
            return HTTPDigestAuth(user, password)
        return None

    def _set_hue_group_state(self, brightness: int, rgb: Tuple[int, int, int],
                             transition_time: int = 0) -> bool:
        """
        Change l'etat du groupe Hue 81.

        Args:
            brightness: 0-254
            rgb: Tuple (R, G, B) 0-255
            transition_time: en dixiemes de seconde (0 = instantane)

        Returns:
            True si succes
        """
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            logger.warning("Configuration Hue manquante")
            return False

        url = f"http://{bridge_ip}/api/{username}/groups/81/action"
        xy = rgb_to_xy(*rgb)

        payload = {
            "on": True,
            "bri": brightness,
            "xy": list(xy),
            "transitiontime": transition_time,
        }

        try:
            response = requests.put(url, json=payload, timeout=API_TIMEOUT)
            if response.status_code == 200:
                return True
            logger.warning(f"Hue error: HTTP {response.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Hue error: {e}")
            return False

    def _flash_white(self) -> bool:
        """
        Flash blanc instantane (200ms).

        Returns:
            True si succes
        """
        logger.debug("Flash blanc...")
        success = self._set_hue_group_state(
            brightness=254,
            rgb=WHITE_RGB,
            transition_time=0  # Instantane
        )

        if success:
            time.sleep(FLASH_DURATION)

        return success

    def _transition_to_blue(self) -> bool:
        """
        Transition fluide vers bleu arc reactor (300ms).

        Returns:
            True si succes
        """
        logger.debug("Transition bleu arc reactor...")
        success = self._set_hue_group_state(
            brightness=200,
            rgb=BLUE_ARC_REACTOR_RGB,
            transition_time=3  # 300ms (3 * 100ms)
        )

        if success:
            time.sleep(BLUE_TRANSITION)

        return success

    def _power_on_tv(self) -> bool:
        """
        Allume la TV.

        Returns:
            True si succes ou deja allumee
        """
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"https://{host}:1926/6/powerstate"
        payload = {"powerstate": "On"}

        try:
            response = requests.put(
                url, json=payload, auth=self._get_tv_auth(),
                timeout=API_TIMEOUT, verify=False
            )
            if response.status_code == 200:
                logger.info("TV allumee")
                return True
            logger.warning(f"TV power_on: HTTP {response.status_code}")
            return False
        except Exception as e:
            logger.warning(f"TV power_on error: {e}")
            return False

    def _launch_youtube(self, video_id: str, retry: bool = True) -> bool:
        """
        Caste une video YouTube via catt (deja disponible dans Lyra).

        Args:
            video_id: ID de la video YouTube

        Returns:
            True si succes
        """
        import shutil
        catt_path = shutil.which("catt") or os.path.expanduser("~/.local/bin/catt")
        device = self.config.get("catt", {}).get("device", "55OLED705/12")

        if not os.path.exists(catt_path):
            logger.warning("catt non disponible, YouTube skip")
            return False

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            result = subprocess.run(
                [catt_path, "-d", device, "cast_site", url],
                capture_output=True,
                text=True,
                timeout=20
            )
            if result.returncode == 0:
                logger.info(f"YouTube caste via catt: {video_id}")
                return True
            logger.warning(f"catt error: {result.stderr or result.stdout}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("catt timeout")
            return False
        except Exception as e:
            logger.warning(f"catt error: {e}")
            return False

    def _activate_ambilight(self) -> bool:
        """
        Active Ambilight en mode follow_audio.

        Returns:
            True si succes
        """
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"https://{host}:1926/6/ambilight/currentconfiguration"

        payload = {
            "styleName": "FOLLOW_AUDIO",
            "isExpert": False,
            "menuSetting": "ENERGY_ADAPTIVE_BRIGHTNESS"
        }

        try:
            response = requests.post(
                url, json=payload, auth=self._get_tv_auth(),
                timeout=API_TIMEOUT, verify=False
            )
            if response.status_code == 200:
                logger.info("Ambilight follow_audio active")
                return True
            logger.warning(f"Ambilight error: HTTP {response.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Ambilight error: {e}")
            return False

    def execute(self, anticipator=None) -> dict:
        """
        Execute la Phase 2: Premier Impact.

        Timeline classique (sans anticipation):
            T+0.0s: Flash blanc
            T+0.2s: Transition bleu
            T+0.5s: Power on TV
            T+2.5s: Launch YouTube (catt)
            T+3.5s: End

        Avec anticipation (musique deja lancee pendant le blackout):
            T+0.0s: Flash blanc
            T+0.2s: Transition bleu
            T+~0.5s: End (la musique demarre d'elle-meme, la Phase 3
                     se synchronise via youtube_launch_time)

        Args:
            anticipator: MusicAnticipator de l'orchestrateur (ou None)

        Returns:
            dict avec: success, flash_ok, blue_ok, tv_on, music_started,
                      music_method, ambilight_active, duration
        """
        logger.info("Phase 2: IMPACT - Debut")
        phase_start = time.perf_counter()

        results = {
            "flash_ok": False,
            "blue_ok": False,
            "tv_on": False,
            "music_started": False,
            "music_method": None,
            "ambilight_active": False,
        }

        # T+0.0s: Flash blanc
        results["flash_ok"] = self._flash_white()

        # T+0.2s: Transition bleu
        results["blue_ok"] = self._transition_to_blue()

        anticipated = anticipator is not None and anticipator.music_started
        if anticipated:
            # Musique lancee pendant le blackout: rien d'autre a faire,
            # la phase se termine tot et la Phase 3 demarre plus vite
            results["tv_on"] = anticipator.tv_prepared
            results["music_started"] = True
            results["music_method"] = "adb-anticipated"
            results["youtube_launch_time"] = anticipator.launch_time
        else:
            # Voie classique: power-on TV puis catt
            elapsed = time.perf_counter() - phase_start
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)

            results["tv_on"] = self._power_on_tv()

            # T+2.5s: Launch YouTube
            elapsed = time.perf_counter() - phase_start
            if elapsed < 2.5:
                time.sleep(2.5 - elapsed)

            youtube_launch_time = time.perf_counter()
            results["music_started"] = self._launch_youtube(YOUTUBE_VIDEO_ID)
            results["music_method"] = "catt" if results["music_started"] else None
            results["youtube_launch_time"] = (
                youtube_launch_time if results["music_started"] else None
            )

            # Attendre fin de phase
            elapsed = time.perf_counter() - phase_start
            if elapsed < PHASE_DURATION:
                time.sleep(PHASE_DURATION - elapsed)

        duration = time.perf_counter() - phase_start

        # Success = flash OK (YouTube optionnel si indisponible)
        results["success"] = results["flash_ok"]
        results["duration"] = duration

        logger.info(f"Phase 2: IMPACT - Fin (duree: {duration:.2f}s)")
        return results
