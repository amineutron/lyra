"""
Phase 4 - Transition & Stabilisation
=====================================

Ralentissement progressif puis stabilisation calme.
Du chaos energetique vers le calme maitrise.

Timeline:
    T+0s -> T+3s:   Ralentissement beats progressif (5 beats)
    T+3s -> T+5s:   Fondu brightness 254 -> 150
    T+4s:           Couper musique
    T+5s -> T+7s:   Stabilisation complete
    T+7s:           Phase terminee

Duree: 7 secondes
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Tuple

import requests
from requests.auth import HTTPDigestAuth
import urllib3
import yaml

logger = logging.getLogger(__name__)

# Disable SSL warnings for TV API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constantes timing
DURATION = 7.0
SLOWDOWN_BEATS = [0.0, 0.5, 1.2, 2.0, 3.0]  # 5 beats ralentis
FADE_START = 3.0  # Debut du fondu
FADE_DURATION = 2.0  # Duree du fondu
MUSIC_STOP = 4.0  # Moment de couper la musique
STABLE_BRIGHTNESS = 150  # Brightness final

# Couleurs
BLUE_ARC_REACTOR_RGB = (0, 100, 255)
RED_INTENSE_RGB = (255, 0, 0)

# Timing beats
FLASH_DURATION = 0.1  # 100ms
TRANSITION_DURATION = 0.2  # 200ms

# API
API_TIMEOUT = 3.0


def rgb_to_xy(red: int, green: int, blue: int) -> Tuple[float, float]:
    """Convertit RGB en coordonnees xy pour Hue."""
    r = red / 255.0
    g = green / 255.0
    b = blue / 255.0

    r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
    g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
    b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92

    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    total = X + Y + Z
    if total == 0:
        return (0.0, 0.0)

    return (X / total, Y / total)


class Phase4Transition:
    """
    Phase 4: Transition & Stabilisation.

    Ralentit les pulsations, fait un fondu vers bleu stable,
    et coupe la musique.

    Usage:
        phase4 = Phase4Transition()
        result = phase4.execute()
    """

    def __init__(self, config_path: Path = None):
        """Initialise Phase4 avec la configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

        self.config = self._load_config(config_path)
        self.hue_config = self.config.get("hue", {})
        self.tv_config = self.config.get("tv", {})

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
        """Change l'etat du groupe Hue 81."""
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            return False

        url = f"http://{bridge_ip}/api/{username}/groups/81/action"
        xy = rgb_to_xy(*rgb)

        payload = {
            "on": True,
            "bri": max(1, brightness),
            "xy": list(xy),
            "transitiontime": transition_time,
        }

        try:
            response = requests.put(url, json=payload, timeout=API_TIMEOUT)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Hue error: {e}")
            return False

    def _set_hue_brightness(self, brightness: int, transition_time: int = 0) -> bool:
        """Change uniquement le brightness du groupe Hue 81."""
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            return False

        url = f"http://{bridge_ip}/api/{username}/groups/81/action"
        payload = {
            "bri": max(1, brightness),
            "transitiontime": transition_time,
        }

        try:
            response = requests.put(url, json=payload, timeout=API_TIMEOUT)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Hue brightness error: {e}")
            return False

    def _execute_beat(self, brightness: int = 254) -> bool:
        """Execute un beat: flash rouge puis retour bleu."""
        flash_ok = self._set_hue_group_state(
            brightness=brightness,
            rgb=RED_INTENSE_RGB,
            transition_time=0
        )

        if flash_ok:
            time.sleep(FLASH_DURATION)
            self._set_hue_group_state(
                brightness=brightness,
                rgb=BLUE_ARC_REACTOR_RGB,
                transition_time=2  # 200ms
            )

        return flash_ok

    def _slowdown_beats(self) -> int:
        """
        Execute 5 beats avec espacement croissant.

        Returns:
            Nombre de beats executes
        """
        beats_executed = 0
        start = time.perf_counter()

        for beat_time in SLOWDOWN_BEATS:
            elapsed = time.perf_counter() - start
            wait_time = beat_time - elapsed

            if wait_time > 0:
                time.sleep(wait_time)

            if self._execute_beat(brightness=254):
                beats_executed += 1
                logger.debug(f"Beat ralenti @ {time.perf_counter() - start:.2f}s")

        return beats_executed

    def _fade_to_stable(self) -> bool:
        """
        Transition fluide brightness 254 -> 150 en 2 secondes.

        Returns:
            True si succes
        """
        logger.debug("Fondu vers brightness stable...")
        return self._set_hue_brightness(
            brightness=STABLE_BRIGHTNESS,
            transition_time=20  # 2 secondes (20 * 100ms)
        )

    def _stop_music(self) -> bool:
        """
        Tente d'arreter la musique YouTube.

        Essaye dans l'ordre:
        1. Pause YouTube via ADB
        2. Volume a 0
        3. Power off TV

        Returns:
            True si musique arretee
        """
        host = self.tv_config.get("host", "192.168.1.50")

        # Methode 1: Pause YouTube via ADB
        if self._send_pause_adb(host):
            logger.info("Musique: Pause via ADB")
            return True

        # Methode 2: Volume a 0
        if self._set_volume(0):
            logger.info("Musique: Volume a 0")
            return True

        # Methode 3: Power off (dernier recours)
        if self._power_off_tv():
            logger.info("Musique: TV eteinte")
            return True

        logger.warning("Impossible d'arreter la musique")
        return False

    def _send_pause_adb(self, host: str) -> bool:
        """Envoie pause via ADB."""
        adb_path = "/tmp/platform-tools/adb"

        if not os.path.exists(adb_path):
            return False

        try:
            # Envoyer keycode MEDIA_PAUSE (127)
            result = subprocess.run(
                [adb_path, "-s", f"{host}:5555", "shell",
                 "input", "keyevent", "127"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"ADB pause error: {e}")
            return False

    def _set_volume(self, level: int) -> bool:
        """Regle le volume TV."""
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"https://{host}:1926/6/audio/volume"

        payload = {"current": level, "muted": level == 0}

        try:
            response = requests.post(
                url, json=payload, auth=self._get_tv_auth(),
                timeout=API_TIMEOUT, verify=False
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Volume error: {e}")
            return False

    def _power_off_tv(self) -> bool:
        """Eteint la TV."""
        host = self.tv_config.get("host", "192.168.1.50")
        url = f"https://{host}:1926/6/powerstate"

        payload = {"powerstate": "Standby"}

        try:
            response = requests.put(
                url, json=payload, auth=self._get_tv_auth(),
                timeout=API_TIMEOUT, verify=False
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Power off error: {e}")
            return False

    def execute(self) -> dict:
        """
        Execute la Phase 4: Transition & Stabilisation.

        Timeline:
            T+0s -> T+3s:   Ralentissement beats
            T+3s -> T+5s:   Fondu brightness
            T+4s:           Couper musique
            T+5s -> T+7s:   Stabilisation
            T+7s:           Fin

        Returns:
            dict avec: success, beats_executed, music_stopped, duration
        """
        logger.info("Phase 4: TRANSITION - Debut")
        phase_start = time.perf_counter()

        results = {
            "beats_executed": 0,
            "fade_ok": False,
            "music_stopped": False,
        }

        # T+0s -> T+3s: Ralentissement beats
        results["beats_executed"] = self._slowdown_beats()

        # T+3s: Demarrer le fondu
        elapsed = time.perf_counter() - phase_start
        if elapsed < FADE_START:
            time.sleep(FADE_START - elapsed)

        results["fade_ok"] = self._fade_to_stable()

        # T+4s: Couper musique
        elapsed = time.perf_counter() - phase_start
        if elapsed < MUSIC_STOP:
            time.sleep(MUSIC_STOP - elapsed)

        results["music_stopped"] = self._stop_music()

        # Attendre fin de phase (stabilisation)
        elapsed = time.perf_counter() - phase_start
        if elapsed < DURATION:
            time.sleep(DURATION - elapsed)

        duration = time.perf_counter() - phase_start

        # Succes si au moins le fondu a fonctionne
        results["success"] = results["fade_ok"]
        results["duration"] = duration

        logger.info(
            f"Phase 4: TRANSITION - Fin (duree: {duration:.2f}s, "
            f"beats: {results['beats_executed']}, music_stopped: {results['music_stopped']})"
        )

        return results
