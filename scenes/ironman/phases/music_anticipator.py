"""
Anticipation musique pendant le blackout (Phase 1)
==================================================

Lance YouTube EN AVANCE, pendant les 3s de noir, pour que la musique
demarre au moment de l'impact (Phase 2) au lieu de 3-15s apres.

Sequence (thread, demarree au debut de la Phase 1):
    T+0.0s: TV deja allumee -> screensaver ADB (ecran noir, pas de
            power-cycle) ; TV eteinte -> power-on (boot pendant le noir)
    T+1.5s: lancement YouTube via ADB deep-link (compte connecte,
            pas de pubs) ; la video bufferise pendant la fin du blackout
    T+3.0s: impact -> la musique demarre ~au flash

Fallback: si ADB echoue, la Phase 2 garde son lancement catt classique.
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Delai avant le lancement YouTube (laisse le blackout s'installer)
YOUTUBE_LAUNCH_DELAY_S = 1.5
ADB_PORT = 5555


def _adb_path() -> Optional[str]:
    """Retourne le chemin adb (PATH ou /tmp/platform-tools)."""
    path = shutil.which("adb")
    if path:
        return path
    legacy = "/tmp/platform-tools/adb"
    return legacy if os.path.exists(legacy) else None


class MusicAnticipator:
    """
    Prepare la TV et lance YouTube pendant le blackout.

    Usage (orchestrateur):
        anticipator = MusicAnticipator(tv_host, tv_auth, video_id,
                                       tv_power="On")
        anticipator.start()          # non bloquant
        ...
        if anticipator.music_started:
            launch_time = anticipator.launch_time

    Attributs (lecture apres .done.wait() ou en fin de Phase 2):
        music_started: True si YouTube a ete lance avec succes
        launch_time: time.perf_counter() du lancement (sync Phase 3)
        tv_prepared: True si la TV a ete allumee/blanked par l'anticipation
    """

    def __init__(self, tv_host: str, tv_auth, video_id: str,
                 tv_power: str = "unknown"):
        self.tv_host = tv_host
        self.tv_auth = tv_auth
        self.video_id = video_id
        self.tv_power = tv_power

        self.music_started = False
        self.music_method: Optional[str] = None
        self.tv_prepared = False
        self.launch_time: Optional[float] = None
        self.done = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Demarre l'anticipation en arriere-plan (non bloquant)."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        start = time.perf_counter()
        try:
            if self.tv_power == "On":
                self.tv_prepared = self._blank_screen()
            else:
                self.tv_prepared = self._power_on_tv()

            # Attendre le point de lancement YouTube
            elapsed = time.perf_counter() - start
            remaining = YOUTUBE_LAUNCH_DELAY_S - elapsed
            if remaining > 0:
                time.sleep(remaining)

            if self._launch_youtube_adb():
                self.music_started = True
                self.music_method = "adb"
                self.launch_time = time.perf_counter()
                logger.info("[ANTICIPATION] YouTube lance via ADB pendant le blackout")
        except Exception as e:
            logger.warning(f"[ANTICIPATION] Echec: {e}")
        finally:
            self.done.set()

    def _power_on_tv(self) -> bool:
        """Allume la TV (boot pendant le noir du blackout)."""
        try:
            url = f"https://{self.tv_host}:1926/6/powerstate"
            response = requests.post(
                url, json={"powerstate": "On"}, auth=self.tv_auth,
                timeout=3, verify=False
            )
            ok = response.status_code == 200
            if ok:
                logger.info("[ANTICIPATION] TV power-on envoye (boot pendant blackout)")
            return ok
        except Exception as e:
            logger.warning(f"[ANTICIPATION] TV power-on echec: {e}")
            return False

    def _blank_screen(self) -> bool:
        """
        Ecran noir sans power-cycle: screensaver via ADB (DreamerService).

        La TV reste allumee -> YouTube se lance instantanement ensuite.
        """
        adb = _adb_path()
        if not adb:
            return False
        try:
            subprocess.run(
                [adb, "connect", f"{self.tv_host}:{ADB_PORT}"],
                capture_output=True, timeout=4
            )
            result = subprocess.run(
                [adb, "-s", f"{self.tv_host}:{ADB_PORT}", "shell",
                 "am", "broadcast", "-a",
                 "org.droidtv.intent.action.START_SCREENSAVER"],
                capture_output=True, text=True, timeout=4
            )
            ok = result.returncode == 0
            if ok:
                logger.info("[ANTICIPATION] Screensaver active (ecran noir sans power-cycle)")
            return ok
        except Exception as e:
            logger.debug(f"[ANTICIPATION] Screensaver echec: {e}")
            return False

    def _launch_youtube_adb(self) -> bool:
        """Lance la video YouTube via ADB deep-link (voie eprouvee Lyra)."""
        adb = _adb_path()
        if not adb:
            logger.warning("[ANTICIPATION] adb introuvable")
            return False

        url = f"https://www.youtube.com/watch?v={self.video_id}"
        try:
            subprocess.run(
                [adb, "connect", f"{self.tv_host}:{ADB_PORT}"],
                capture_output=True, timeout=5
            )
            result = subprocess.run(
                [adb, "-s", f"{self.tv_host}:{ADB_PORT}", "shell",
                 "am", "start",
                 "-a", "android.intent.action.VIEW",
                 "-d", url,
                 "com.google.android.youtube.tv"],
                capture_output=True, text=True, timeout=8
            )
            if result.returncode == 0 and "Error" not in (result.stdout or ""):
                return True
            logger.warning(
                f"[ANTICIPATION] ADB youtube echec: "
                f"{(result.stderr or result.stdout or '')[:120]}"
            )
            return False
        except Exception as e:
            logger.warning(f"[ANTICIPATION] ADB youtube erreur: {e}")
            return False
