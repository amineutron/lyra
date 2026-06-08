"""
Orchestrateur Scene Iron Man
============================

Chef d'orchestre qui coordonne toutes les phases de la scene Iron Man.
Gere la state machine, les erreurs et le rollback.

Timeline complete (~33 secondes):
    T+0s:    Phase 0 - Validation (2s)
    T+2s:    Phase 1 - Blackout (3s)
    T+5s:    Phase 2 - Impact (3.5s)
    T+8.5s:  Phase 3 - Buildup (12s)
    T+20.5s: Phase 4 - Transition (7s)
    T+27.5s: Phase 5 - TTS (5.5s)
    T+33s:   Etat stable

Usage:
    orchestrator = IronManOrchestrator()
    if orchestrator.trigger("je suis iron man"):
        # Scene lancee automatiquement
        pass
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import requests
from requests.auth import HTTPDigestAuth
import yaml

from .phases import (
    Phase0Detection,
    Phase1Blackout,
    Phase2Impact,
    Phase3Buildup,
    Phase4Transition,
    Phase5TTS,
)
from .phases.phase0_detection import load_rollback_state, ROLLBACK_FILE

logger = logging.getLogger(__name__)

HUE_BEAT_PY = Path("/home/amineutron/dev/ironman-hue/hue_beat.py")
HUE_BEAT_PID_FILE = Path("/tmp/ironman_hue.pid")
LYRA_VENV_PYTHON = Path(__file__).parent.parent.parent / ".venv" / "bin" / "python3"


class SceneState(Enum):
    """Etats possibles de la scene."""
    IDLE = auto()
    VALIDATING = auto()
    BLACKOUT = auto()
    IMPACT = auto()
    BUILDUP = auto()
    TRANSITION = auto()
    TTS = auto()
    STABLE = auto()
    ROLLBACK = auto()


class IronManOrchestrator:
    """
    Orchestrateur principal de la scene Iron Man.

    Coordonne les 6 phases et gere les erreurs avec rollback automatique.

    Usage:
        orchestrator = IronManOrchestrator()

        # Dans la boucle principale de Lyra:
        if orchestrator.trigger(user_input):
            # Scene lancee, skip le LLM
            pass
        else:
            # Pas de trigger, continuer flow normal
            pass
    """

    def __init__(self, config_path: Path = None):
        """
        Initialise l'orchestrateur.

        Args:
            config_path: Chemin vers config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config.yaml"

        self.config_path = config_path
        self.config = self._load_config(config_path)

        # State machine
        self._state = SceneState.IDLE
        self._saved_state: Optional[Dict] = None

        # Phases (lazy init)
        self._phase0: Optional[Phase0Detection] = None
        self._phase1: Optional[Phase1Blackout] = None
        self._phase2: Optional[Phase2Impact] = None
        self._phase3: Optional[Phase3Buildup] = None
        self._phase4: Optional[Phase4Transition] = None
        self._phase5: Optional[Phase5TTS] = None

        # Stats
        self._scene_start_time: float = 0
        self._phase_results: Dict[str, Any] = {}
        self._youtube_launch_time: Optional[float] = None

    def _load_config(self, config_path: Path) -> dict:
        """Charge la configuration."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Config load error: {e}")
            return {}

    def _load_hue_secrets(self) -> dict:
        """Charge clientkey et area_id depuis secrets.yaml."""
        secrets_path = self.config_path.parent / "secrets.yaml"
        try:
            with open(secrets_path) as f:
                s = yaml.safe_load(f)
            return s.get("hue", {})
        except Exception as e:
            logger.warning(f"secrets.yaml non disponible: {e}")
            return {}

    def _start_hue_beat(self) -> bool:
        """
        Lance hue_beat en mode pulse/ironman/bass-only.

        Utilise l'API Entertainment (DTLS/UDP) pour des beats
        audio-reactifs en temps reel (~5ms latence).

        Returns:
            True si le processus a demarre correctement
        """
        if not HUE_BEAT_PY.exists():
            logger.warning(f"hue_beat.py introuvable: {HUE_BEAT_PY}")
            return False

        hue_cfg = self.config.get("hue", {})
        secrets = self._load_hue_secrets()

        env = {
            **os.environ,
            "HUE_BRIDGE_IP": hue_cfg.get("bridge_ip", "192.168.1.51"),
            "HUE_USER": hue_cfg.get("username", ""),
            "HUE_CLIENTKEY": secrets.get("clientkey", ""),
            "HUE_AREA_ID": secrets.get("area_id", ""),
        }

        if not env["HUE_CLIENTKEY"] or not env["HUE_AREA_ID"]:
            logger.warning("hue_beat: clientkey ou area_id manquant dans secrets.yaml")
            return False

        python_bin = str(LYRA_VENV_PYTHON) if LYRA_VENV_PYTHON.exists() else sys.executable

        try:
            subprocess.Popen(
                [python_bin, str(HUE_BEAT_PY),
                 "--mode=pulse", "--palette=ironman", "--bass-only"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # Laisser le temps a hue_beat de demarrer et ecrire son PID
            time.sleep(2.5)
            logger.info("[IRONMAN] hue_beat demarré (pulse/ironman/bass-only)")
            return True
        except Exception as e:
            logger.warning(f"[IRONMAN] hue_beat start failed: {e}")
            return False

    def _stop_hue_beat(self):
        """Arrete hue_beat proprement via SIGTERM sur le PID sauvegarde."""
        try:
            pid = int(HUE_BEAT_PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            logger.info(f"[IRONMAN] hue_beat arrete (PID {pid})")
        except FileNotFoundError:
            pass  # Deja arrete ou jamais demarre
        except (ValueError, ProcessLookupError) as e:
            logger.debug(f"[IRONMAN] hue_beat stop: {e}")
        except Exception as e:
            logger.warning(f"[IRONMAN] hue_beat stop error: {e}")

    @property
    def state(self) -> SceneState:
        """Retourne l'etat actuel."""
        return self._state

    @property
    def is_running(self) -> bool:
        """True si une scene est en cours."""
        return self._state not in (SceneState.IDLE, SceneState.STABLE)

    def _init_phases(self):
        """Initialise les phases (lazy)."""
        if self._phase0 is None:
            self._phase0 = Phase0Detection(self.config_path)
            self._phase1 = Phase1Blackout(self.config_path)
            self._phase2 = Phase2Impact(self.config_path)
            self._phase3 = Phase3Buildup(self.config_path)
            self._phase4 = Phase4Transition(self.config_path)
            self._phase5 = Phase5TTS(self.config_path)

    def trigger(self, text: str) -> bool:
        """
        Verifie si le texte contient un trigger et lance la scene.

        Args:
            text: Texte a analyser (commande vocale ou texte)

        Returns:
            True si la scene a ete lancee, False sinon
        """
        # Ignorer si deja en cours
        if self.is_running:
            logger.debug("Scene deja en cours, trigger ignore")
            return False

        # Init phases
        self._init_phases()

        # Check trigger
        if not self._phase0.is_trigger_detected(text):
            return False

        # Lancer la scene
        logger.info("[IRONMAN] Scene declenchee!")
        self._execute_scene()
        return True

    def _execute_scene(self):
        """Execute la scene complete avec gestion des erreurs."""
        self._scene_start_time = time.perf_counter()
        self._phase_results = {}

        try:
            # Phase 0: Validation
            if not self._run_phase(
                SceneState.VALIDATING,
                "Phase 0 - Validation",
                self._execute_phase0
            ):
                # Echec validation = pas de rollback necessaire
                self._state = SceneState.IDLE
                return

            # Phase 1: Blackout
            self._run_phase(
                SceneState.BLACKOUT,
                "Phase 1 - Blackout",
                self._execute_phase1
            )

            # Phase 2: Impact
            self._run_phase(
                SceneState.IMPACT,
                "Phase 2 - Impact",
                self._execute_phase2
            )

            # Phase 3: Buildup
            self._run_phase(
                SceneState.BUILDUP,
                "Phase 3 - Buildup",
                self._execute_phase3
            )

            # Phase 4: Transition
            self._run_phase(
                SceneState.TRANSITION,
                "Phase 4 - Transition",
                self._execute_phase4
            )

            # Phase 5: TTS
            self._run_phase(
                SceneState.TTS,
                "Phase 5 - TTS",
                self._execute_phase5
            )

            # Succes!
            self._state = SceneState.STABLE
            total_duration = time.perf_counter() - self._scene_start_time
            logger.info(f"[IRONMAN] Scene terminee avec succes! (duree: {total_duration:.1f}s)")

        except Exception as e:
            logger.error(f"[IRONMAN] Erreur scene: {e}")
            logger.error(traceback.format_exc())
            self._rollback()

    def _run_phase(self, state: SceneState, name: str, func: Callable) -> bool:
        """
        Execute une phase avec logging et timing.

        Args:
            state: Etat de la state machine
            name: Nom de la phase pour les logs
            func: Fonction a executer

        Returns:
            True si succes, False sinon

        Raises:
            Exception: Propage les exceptions pour rollback
        """
        self._state = state
        phase_start = time.perf_counter()
        logger.info(f"[IRONMAN] {name} started")

        try:
            result = func()
            duration = time.perf_counter() - phase_start

            # Sauvegarder le resultat
            phase_key = state.name.lower()
            self._phase_results[phase_key] = result

            if result.get("success", True):
                logger.info(f"[IRONMAN] {name} completed (duration: {duration:.2f}s)")
                return True
            else:
                logger.warning(f"[IRONMAN] {name} failed: {result}")
                if state == SceneState.VALIDATING:
                    return False
                raise Exception(f"{name} failed")

        except Exception as e:
            duration = time.perf_counter() - phase_start
            logger.error(f"[IRONMAN] {name} failed after {duration:.2f}s: {e}")
            raise

    def _execute_phase0(self) -> dict:
        """Execute Phase 0 et sauvegarde l'etat."""
        success, message, saved_state = self._phase0.validate_and_prepare()
        self._saved_state = saved_state
        return {"success": success, "message": message}

    def _execute_phase1(self) -> dict:
        """Execute Phase 1 - Blackout."""
        return self._phase1.execute()

    def _execute_phase2(self) -> dict:
        """Execute Phase 2 - Impact."""
        result = self._phase2.execute()
        # Sauvegarder le timestamp de lancement YouTube pour Phase 3
        self._youtube_launch_time = result.get("youtube_launch_time")
        return result

    def _execute_phase3(self) -> dict:
        """Execute Phase 3 - Buildup avec hue_beat audio-reactif."""
        # Lancer hue_beat avant la phase (Entertainment API DTLS)
        self._start_hue_beat()

        # Calculer le délai avant que la vidéo commence vraiment
        video_start_delay = 0.0
        if self._youtube_launch_time is not None:
            time_since_launch = time.perf_counter() - self._youtube_launch_time
            YOUTUBE_LOAD_TIME = 2.5  # secondes pour charger
            video_start_delay = max(0.0, YOUTUBE_LOAD_TIME - time_since_launch)
            logger.info(f"[IRONMAN] YouTube lancé il y a {time_since_launch:.1f}s, attente vidéo: {video_start_delay:.1f}s")
        return self._phase3.execute(video_start_delay=video_start_delay)

    def _execute_phase4(self) -> dict:
        """Execute Phase 4 - Transition (hue_beat continue)."""
        return self._phase4.execute()

    def _execute_phase5(self) -> dict:
        """Execute Phase 5 - TTS, puis arret hue_beat."""
        result = self._phase5.execute()
        self._stop_hue_beat()
        return result

    def _rollback(self):
        """
        Restaure l'etat initial apres une erreur.

        Utilise l'etat sauvegarde par Phase 0.
        """
        logger.info("[IRONMAN] Rollback started")
        self._state = SceneState.ROLLBACK

        # Arreter hue_beat si actif
        self._stop_hue_beat()

        # Charger l'etat sauvegarde
        state = self._saved_state or load_rollback_state()
        if not state:
            logger.warning("[IRONMAN] Pas d'etat de rollback disponible")
            self._state = SceneState.IDLE
            return

        try:
            # Restaurer Hue
            self._restore_hue(state.get("hue", {}))

            # Restaurer TV
            self._restore_tv(state.get("tv", {}))

            logger.info("[IRONMAN] Rollback completed")

        except Exception as e:
            logger.error(f"[IRONMAN] Rollback failed: {e}")

        finally:
            self._state = SceneState.IDLE

    def _restore_hue(self, hue_state: dict):
        """Restaure l'etat des lumieres Hue."""
        bridge_ip = self.config.get("hue", {}).get("bridge_ip", "192.168.1.51")
        username = self.config.get("hue", {}).get("username", "")

        if not username:
            return

        lights = hue_state.get("lights", {})
        for light_id, light_state in lights.items():
            try:
                url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
                payload = {
                    "on": light_state.get("on", False),
                }
                if light_state.get("on"):
                    payload["bri"] = light_state.get("brightness", 254)
                    if light_state.get("xy"):
                        payload["xy"] = light_state.get("xy")

                requests.put(url, json=payload, timeout=2)
                logger.debug(f"Lumiere {light_id} restauree")

            except Exception as e:
                logger.warning(f"Restauration lumiere {light_id} echouee: {e}")

    def _restore_tv(self, tv_state: dict):
        """Restaure l'etat de la TV."""
        tv_config = self.config.get("tv", {})
        host = tv_config.get("host", "192.168.1.50")
        user = tv_config.get("user", "")
        password = tv_config.get("pass", "")
        auth = HTTPDigestAuth(user, password) if user and password else None

        try:
            # Restaurer power state
            power = tv_state.get("power", "unknown")
            if power == "On":
                url = f"https://{host}:1926/6/powerstate"
                requests.post(url, json={"powerstate": "On"}, auth=auth, timeout=3, verify=False)

            # Restaurer volume
            volume = tv_state.get("volume", 0)
            if volume > 0:
                url = f"https://{host}:1926/6/audio/volume"
                requests.post(url, json={"current": volume, "muted": False}, auth=auth, timeout=3, verify=False)

            # Restaurer ambilight
            ambilight = tv_state.get("ambilight")
            if ambilight:
                url = f"https://{host}:1926/6/ambilight/currentconfiguration"
                requests.post(url, json=ambilight, auth=auth, timeout=3, verify=False)

            logger.debug("TV restauree")

        except Exception as e:
            logger.warning(f"Restauration TV echouee: {e}")

    def cancel(self):
        """
        Annule la scene en cours.

        Peut etre appele par une commande vocale "stop" ou "annule".
        """
        if self._state == SceneState.IDLE:
            logger.debug("Pas de scene en cours a annuler")
            return

        logger.info("[IRONMAN] Annulation manuelle")
        self._rollback()

    def get_status(self) -> dict:
        """Retourne le statut actuel de l'orchestrateur."""
        return {
            "state": self._state.name,
            "is_running": self.is_running,
            "phase_results": self._phase_results,
        }
