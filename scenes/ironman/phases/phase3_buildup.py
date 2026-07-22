"""
Phase 3 - Pulsations Synchronisees
==================================

Montee en puissance avec pulsations lumineuses rouge/bleu.
Les beats sont synchronises avec la musique YouTube via catt info.

Timeline:
    1. Attendre que YouTube joue (poll catt info)
    2. Synchroniser les beats avec current_time
    3. Progression lineaire brightness: 0 -> 254
    4. Duree ~12-15 secondes selon les beats de la chanson

Position scene: T+8.5s -> T+20.5s
"""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Optional

import requests
from requests.auth import HTTPDigestAuth
import urllib3
import yaml

# Disable SSL warnings for TV API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Fichier des beats analysés
BEATS_FILE = Path(__file__).parent.parent.parent.parent / "assets" / "back_in_black_beats.json"

# Constantes timing
PHASE_DURATION = 12.0  # Duree cible de la phase
FLASH_DURATION = 0.08  # 80ms flash rouge

# CALIBRATION: Ajuster cette valeur si les beats sont décalés
# Positif = retarder les beats (si lumières en avance)
# Négatif = avancer les beats (si lumières en retard)
BEAT_SYNC_OFFSET = 0.0  # secondes

# Couleurs
BLUE_ARC_REACTOR_RGB = (0, 0, 255)

HUE_BEAT_PID_FILE = Path("/tmp/ironman_hue.pid")
HUE_BEAT_CTRL_FILE = Path("/tmp/lyra_hue_beat.ctrl")
HUE_BEAT_STATE_FILE = Path("/tmp/lyra_hue_beat.state.json")
RED_INTENSE_RGB = (255, 0, 0)

# Fenetre d'observation avant de basculer en pulses pilotes:
# si hue_beat n'a detecte aucun beat audio apres ce delai (cas normal
# quand YouTube joue sur la TV: aucun audio ne passe par le PC), la
# phase pilote les pulses via CTRL_FILE sur les beats precalcules.
HUE_BEAT_OBSERVE_S = 2.0
# Avance d'ecriture du pulse (compense le poll 50ms du watcher)
CTRL_PULSE_LEAD_S = 0.03

# Pulses pilotes: plancher lumineux entre les pulses (0 = noir) et
# pattern d'intensite cyclique pour garder un groove (temps fort a 1.0)
CTRL_FLOOR = 0.22
CTRL_INTENSITY_PATTERN = (1.0, 0.7, 0.85, 0.7)

# API
API_TIMEOUT = 1.5  # Timeout court pour les beats rapides

# Chromecast device
CAST_DEVICE = "55OLED705/12"


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


class Phase3Buildup:
    """
    Phase 3: Pulsations Synchronisees avec la musique.

    Utilise les beats pre-analyses du MP3 et synchronise
    avec la position de lecture YouTube via catt.

    Usage:
        phase3 = Phase3Buildup()
        result = phase3.execute()
    """

    def __init__(self, config_path: Path = None):
        """Initialise Phase3 avec la configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

        self.config = self._load_config(config_path)
        self.hue_config = self.config.get("hue", {})
        self.tv_config = self.config.get("tv", {})
        self.beats = self._load_beats()

        # Stats d'execution
        self._beats_executed = 0
        self._last_brightness = 0

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

    def _load_beats(self) -> List[float]:
        """Charge les timestamps des beats depuis le fichier JSON."""
        try:
            with open(BEATS_FILE, 'r') as f:
                data = json.load(f)
                # Utiliser les beats des 15 premières secondes
                beats = data.get("beats_first_15s", data.get("beats", []))
                logger.info(f"Chargé {len(beats)} beats depuis {BEATS_FILE.name}")
                return beats
        except Exception as e:
            logger.warning(f"Impossible de charger les beats: {e}")
            # Fallback: beats réguliers à 94 BPM
            return [i * 0.638 for i in range(24)]  # ~94 BPM

    def _get_playback_position(self) -> Optional[float]:
        """
        Obtient la position de lecture actuelle via catt.

        Returns:
            Position en secondes, ou None si erreur
        """
        try:
            result = subprocess.run(
                ["catt", "-d", CAST_DEVICE, "info"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith("current_time:"):
                        return float(line.split(":")[1].strip())
            return None
        except Exception as e:
            logger.debug(f"Erreur catt info: {e}")
            return None

    def _wait_for_playback(self, timeout: float = 5.0) -> Optional[float]:
        """
        Attend que la lecture YouTube commence.

        Returns:
            Position de départ, ou None si timeout
        """
        start = time.perf_counter()

        while time.perf_counter() - start < timeout:
            pos = self._get_playback_position()
            if pos is not None and pos > 0:
                logger.info(f"Lecture détectée à {pos:.2f}s")
                return pos
            time.sleep(0.1)

        logger.warning("Timeout en attendant la lecture")
        return None

    def _set_hue_group_state(self, brightness: int, rgb: Tuple[int, int, int],
                             transition_time: int = 0) -> bool:
        """Change l'etat du groupe Hue 81."""
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            logger.warning("Configuration Hue manquante")
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
            logger.debug(f"Hue error (beat): {e}")
            return False

    def _calculate_brightness(self, progress: float) -> int:
        """
        Calcule le brightness selon la progression (0.0 à 1.0).

        Returns:
            Brightness 0-254
        """
        return int(min(1.0, max(0.0, progress)) * 254)

    def _execute_beat(self) -> bool:
        """Execute un beat: flash de 0% à 100% puis retour à 0%."""
        # Flash rouge à 100% brightness instantané
        flash_ok = self._set_hue_group_state(
            brightness=254,  # 100%
            rgb=RED_INTENSE_RGB,
            transition_time=0
        )

        if flash_ok:
            time.sleep(FLASH_DURATION)
            # Retour bleu à faible luminosité
            self._set_hue_group_state(
                brightness=1,  # ~0%
                rgb=BLUE_ARC_REACTOR_RGB,
                transition_time=1  # 100ms
            )

        return flash_ok

    def _hue_beat_running(self) -> bool:
        """Retourne True si hue_beat tourne (PID file valide)."""
        try:
            pid = int(HUE_BEAT_PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return True
        except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
            return False

    def _hue_beat_beat_count(self) -> int:
        """
        Lit beat_count dans le state file de hue_beat (0 si absent).

        Le PID du state doit correspondre au PID file courant, sinon le
        state provient d'un ancien run (beat_count residuel trompeur).
        """
        try:
            state = json.loads(HUE_BEAT_STATE_FILE.read_text())
            current_pid = int(HUE_BEAT_PID_FILE.read_text().strip())
            if int(state.get("pid", -1)) != current_pid:
                return 0
            return int(state.get("beat_count", 0))
        except Exception:
            return 0

    def _send_hue_beat_ctrl(self, cmd: dict) -> bool:
        """
        Ecrit une commande dans le CTRL_FILE de hue_beat (atomique).

        tmp + os.replace: le watcher ne peut jamais lire un JSON partiel.
        """
        try:
            tmp = HUE_BEAT_CTRL_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(cmd))
            os.replace(tmp, HUE_BEAT_CTRL_FILE)
            return True
        except Exception as e:
            logger.debug(f"ctrl erreur: {e}")
            return False

    def _send_hue_beat_pulse(self, intensity: float = 1.0) -> bool:
        """Envoie un pulse a hue_beat via le CTRL_FILE."""
        return self._send_hue_beat_ctrl({"pulse": intensity})

    def _measure_video_position(self) -> Optional[float]:
        """
        Mesure la position de lecture reelle de YouTube via ADB.

        dumpsys media_session expose position (ms), speed et updated
        (elapsedRealtime ms de la derniere mise a jour). La position
        courante = position + (uptime_ms - updated) * speed.

        Returns:
            Position en secondes si YouTube est en lecture, sinon None
        """
        import shutil
        adb = shutil.which("adb")
        host = self.tv_config.get("host", "192.168.1.50")
        if not adb:
            return None
        try:
            result = subprocess.run(
                [adb, "-s", f"{host}:5555", "shell",
                 "dumpsys media_session; echo ---UPTIME---; cat /proc/uptime"],
                capture_output=True, text=True, timeout=4
            )
            if result.returncode != 0:
                return None
            output, _, uptime_part = result.stdout.partition("---UPTIME---")
            uptime_ms = float(uptime_part.strip().split()[0]) * 1000.0

            # Bloc de la session YouTube uniquement
            yt_block = output.split("com.google.android.youtube.tv", 1)
            if len(yt_block) < 2:
                return None
            match = re.search(
                r"state=(\d+), position=(\d+), buffered position=\d+, "
                r"speed=([\d.]+), updated=(\d+)",
                yt_block[1]
            )
            if not match:
                return None
            state, position_ms, speed, updated_ms = (
                int(match.group(1)), float(match.group(2)),
                float(match.group(3)), float(match.group(4)),
            )
            if state != 3:  # 3 = PLAYING
                return None
            current_s = (position_ms + (uptime_ms - updated_ms) * speed) / 1000.0
            if current_s < 0 or current_s > 300:
                return None
            return current_s
        except Exception as e:
            logger.debug(f"mesure position video: {e}")
            return None

    def _drive_hue_beat_pulses(self, phase_start: float,
                               deadline: float) -> int:
        """
        Pilote les pulses hue_beat sur les beats precalcules.

        Utilise quand l'audio ne passe pas par le PC (YouTube sur la TV):
        hue_beat n'entend rien, on lui envoie les beats via CTRL_FILE.
        L'intensite suit CTRL_INTENSITY_PATTERN (temps fort a 1.0) pour
        garder un groove au lieu d'un strobe monotone.

        Args:
            phase_start: perf_counter du debut de la video (t=0 des beats)
            deadline: perf_counter de fin de phase (jamais depasse)

        Returns:
            Nombre de pulses envoyes
        """
        # Ambiance entre les pulses + pas d'ancres aleatoires en cadence fixe
        self._send_hue_beat_ctrl({"floor": CTRL_FLOOR, "anchor": False})

        sent = 0
        for i, beat_time in enumerate(self.beats):
            target = phase_start + beat_time + BEAT_SYNC_OFFSET - CTRL_PULSE_LEAD_S
            if target >= deadline:
                break
            wait = target - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            elif wait < -0.5:
                continue  # beat deja depasse (observation), ne pas rafaler
            intensity = CTRL_INTENSITY_PATTERN[i % len(CTRL_INTENSITY_PATTERN)]
            if self._send_hue_beat_pulse(intensity):
                sent += 1
        return sent

    def execute(self, video_start_delay: float = 0.0, music_offset: float = 0.0) -> dict:
        """
        Execute la Phase 3: Pulsations Synchronisees.

        Args:
            video_start_delay: Secondes à attendre avant que la vidéo commence.
            music_offset: Secondes déjà écoulées dans la musique (si vidéo déjà en cours).

        Returns:
            dict avec: success, beats_executed, duration
        """
        logger.info(f"Phase 3: BUILDUP - Debut (attente video: {video_start_delay:.2f}s)")

        # hue_beat (Entertainment API) gere les beats en temps reel
        if self._hue_beat_running():
            phase_entry = time.perf_counter()

            # Attendre le vrai demarrage de la video (t=0 des beats)
            if video_start_delay > 0:
                time.sleep(video_start_delay)
            video_start = time.perf_counter()
            deadline = phase_entry + PHASE_DURATION

            # Ancrage exact: position de lecture reelle via ADB (le
            # delai de chargement YouTube estime peut etre faux de
            # plusieurs secondes -> tous les beats seraient decales)
            video_anchor = "estimated"
            measured = self._measure_video_position()
            if measured is not None:
                video_start = time.perf_counter() - measured
                video_anchor = "measured"
                logger.info(f"Phase 3: position video mesuree {measured:.2f}s "
                            f"(ancrage exact des beats)")

            # Observation: hue_beat entend-il l'audio ? (non quand
            # YouTube joue sur la TV: rien ne passe par le PC)
            observe_until = min(video_start + HUE_BEAT_OBSERVE_S, deadline)
            while time.perf_counter() < observe_until:
                if self._hue_beat_beat_count() > 0:
                    break
                time.sleep(0.1)

            if self._hue_beat_beat_count() > 0:
                logger.info("Phase 3: hue_beat audio-reactif, attente passive")
                remaining = deadline - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
                mode, beats_sent = "hue_beat", -1
            else:
                logger.info("Phase 3: hue_beat silencieux -> pulses pilotes "
                            "(beats precalcules via CTRL_FILE)")
                beats_sent = self._drive_hue_beat_pulses(video_start, deadline)
                remaining = deadline - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
                mode = "hue_beat_ctrl"
                logger.info(f"Phase 3: {beats_sent} pulses pilotes envoyes")

            return {
                "success": True,
                "beats_executed": beats_sent,
                "total_beats": len(self.beats),
                "duration": time.perf_counter() - phase_entry,
                "mode": mode,
                "video_anchor": video_anchor,
            }

        # Attendre que la vidéo commence vraiment
        if video_start_delay > 0:
            logger.info(f"Attente {video_start_delay:.1f}s pour démarrage vidéo...")
            time.sleep(video_start_delay)

        self._beats_executed = 0

        # Prendre tous les beats disponibles (jusqu'à la durée max)
        relevant_beats = [b for b in self.beats if b <= 20.0]  # Max 20s

        if not relevant_beats:
            logger.warning("Aucun beat trouvé!")
            relevant_beats = [5.78, 6.46, 7.11, 7.73, 8.41, 9.06]  # Fallback

        logger.info(f"Beats à jouer: {len(relevant_beats)}")

        # Démarrer le timer de synchronisation
        phase_start = time.perf_counter()

        # Jouer les beats synchronisés avec les timestamps du fichier
        # Les timestamps sont relatifs au début de la vidéo (t=0 = début vidéo)
        for i, beat_time in enumerate(relevant_beats):
            # Temps écoulé depuis le début de la vidéo (après le délai d'attente)
            elapsed = time.perf_counter() - phase_start
            # Le beat doit arriver à beat_time + ajustement éventuel
            target_time = beat_time + BEAT_SYNC_OFFSET
            wait_time = target_time - elapsed

            if wait_time > 0:
                time.sleep(wait_time)

            # Exécuter le beat (flash 0% -> 100% -> 0%)
            if self._execute_beat():
                self._beats_executed += 1
                logger.debug(f"Beat {i+1}/{len(relevant_beats)} @ {beat_time:.2f}s")

        # S'assurer qu'on reste au moins PHASE_DURATION
        elapsed = time.perf_counter() - phase_start
        if elapsed < PHASE_DURATION:
            time.sleep(PHASE_DURATION - elapsed)

        duration = time.perf_counter() - phase_start

        # Résultat
        success = self._beats_executed >= len(relevant_beats) * 0.8  # 80% minimum

        logger.info(
            f"Phase 3: BUILDUP - Fin (duree: {duration:.2f}s, "
            f"beats: {self._beats_executed}/{len(relevant_beats)})"
        )

        return {
            "success": success,
            "beats_executed": self._beats_executed,
            "total_beats": len(relevant_beats),
            "duration": duration,
        }
