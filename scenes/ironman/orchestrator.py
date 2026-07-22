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
import threading
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
from .phases.phase2_impact import YOUTUBE_VIDEO_ID
from .phases.music_anticipator import MusicAnticipator
from .metrics import SceneMetrics

try:
    from lyra.hestia.tracking_client import TrackingClient
except ImportError:
    TrackingClient = None

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

    def __init__(self, config_path: Path = None,
                 pc_auto_wake_s: Optional[int] = None):
        """
        Initialise l'orchestrateur.

        Args:
            config_path: Chemin vers config.yaml
            pc_auto_wake_s: rallumage auto des ecrans PC apres N secondes
                            (tests de sous-scenes uniquement, None en prod)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config.yaml"

        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.pc_auto_wake_s = pc_auto_wake_s

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

        # Telemetrie (metriques locales + tracking dashboard)
        self._metrics: Optional[SceneMetrics] = None
        self._tracking = TrackingClient() if TrackingClient else None
        self._tracking_id: Optional[str] = None

        # Anticipation musique (lancee pendant le blackout)
        self._anticipator: Optional[MusicAnticipator] = None
        self._current_selection: list = []

    def _load_config(self, config_path: Path) -> dict:
        """Charge config.yaml et fusionne secrets.yaml si present."""
        config = {}
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Config load error: {e}")

        secrets_path = config_path.parent / "secrets.yaml"
        if secrets_path.exists():
            try:
                with open(secrets_path) as f:
                    secrets = yaml.safe_load(f) or {}
                for section, values in secrets.items():
                    if section in config and isinstance(config[section], dict):
                        config[section].update(values)
                    else:
                        config[section] = values
            except Exception as e:
                logger.warning(f"secrets.yaml load error: {e}")

        return config

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
        # Source audio configurable (defaut hue_beat: sortie HDMI du PC;
        # inutile quand YouTube joue sur la TV -> beats pilotes en ctrl)
        audio_source = (
            self.config.get("scenes", {}).get("ironman", {})
            .get("hue_beat_source")
        )
        if audio_source:
            env["HUE_MONITOR_SRC"] = audio_source

        if not env["HUE_CLIENTKEY"] or not env["HUE_AREA_ID"]:
            logger.warning("hue_beat: clientkey ou area_id manquant dans secrets.yaml")
            return False

        python_bin = str(LYRA_VENV_PYTHON) if LYRA_VENV_PYTHON.exists() else sys.executable

        # Purger un PID file perime (sinon _wait_hue_beat validerait
        # un process d'un ancien run)
        try:
            HUE_BEAT_PID_FILE.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"[IRONMAN] purge PID file: {e}")

        try:
            subprocess.Popen(
                [python_bin, str(HUE_BEAT_PY),
                 "--mode=pulse", "--palette=ironman", "--bass-only"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # Non bloquant: la disponibilite est verifiee par
            # _wait_hue_beat() (poll du PID file) avant la Phase 3
            logger.info("[IRONMAN] hue_beat lance (pulse/ironman/bass-only)")
            return True
        except Exception as e:
            logger.warning(f"[IRONMAN] hue_beat start failed: {e}")
            return False

    def _wait_hue_beat(self, timeout: float = 2.5) -> bool:
        """
        Attend que hue_beat ait ecrit son PID file (poll 100ms).

        Remplace l'ancien sleep(2.5) fixe: retourne des que le process
        est pret, ou apres timeout.
        """
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if HUE_BEAT_PID_FILE.exists():
                logger.info("[IRONMAN] hue_beat pret")
                return True
            time.sleep(0.1)
        logger.warning(f"[IRONMAN] hue_beat pas pret apres {timeout}s")
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
        finally:
            try:
                HUE_BEAT_PID_FILE.unlink()
            except Exception:
                pass

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
            self._phase1 = Phase1Blackout(
                self.config_path, pc_auto_wake_s=self.pc_auto_wake_s
            )
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

    def _start_telemetry(self, run_type: str, selection: list):
        """Initialise metriques locales + session tracking dashboard."""
        # Kill-switch (tests unitaires: pas de fichier reel ni de session
        # tracking sur le dashboard)
        if os.environ.get("IRONMAN_NO_TELEMETRY"):
            return
        self._metrics = SceneMetrics(run_type, selection)
        if self._tracking is not None:
            try:
                self._tracking_id = self._tracking.create(
                    name="Scene Iron Man" if run_type == "full"
                         else f"Iron Man sous-scene {selection}",
                    template="lyra_task",
                    total=len(selection) or 1,
                    unit="phases",
                    extra={"operation": "ironman_scene",
                           "target": ",".join(str(n) for n in selection)},
                )
            except Exception as e:
                logger.debug(f"[IRONMAN] tracking indisponible: {e}")
                self._tracking_id = None

    def _end_telemetry(self, success: bool):
        """Clot metriques + session tracking (jamais bloquant)."""
        if self._metrics is not None:
            self._metrics.finalize(success=success)
            self._metrics = None
        if self._tracking is not None and self._tracking_id:
            try:
                if success:
                    self._tracking.complete(self._tracking_id, log="Scene terminee")
                else:
                    self._tracking.error(self._tracking_id, "Scene en echec")
            except Exception:
                pass
            self._tracking_id = None

    def _execute_scene(self):
        """Execute la scene complete avec gestion des erreurs."""
        self._scene_start_time = time.perf_counter()
        self._phase_results = {}
        self._current_selection = [0, 1, 2, 3, 4, 5]
        self._start_telemetry("full", self._current_selection)

        # Precharger Piper TTS pendant que la scene se deroule
        threading.Thread(target=self._preload_tts, daemon=True).start()

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
            self._end_telemetry(success=True)

        except Exception as e:
            logger.error(f"[IRONMAN] Erreur scene: {e}")
            logger.error(traceback.format_exc())
            self._rollback()
            self._end_telemetry(success=False)

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
        phase_offset = phase_start - self._scene_start_time
        logger.info(f"[IRONMAN] {name} started")

        try:
            result = func()
            duration = time.perf_counter() - phase_start

            # Sauvegarder le resultat
            phase_key = state.name.lower()
            self._phase_results[phase_key] = result

            # Telemetrie
            if self._metrics is not None:
                self._metrics.record_step(
                    phase_key, duration, result.get("success", True), result
                )
                # Premier effet visible = extinction lumieres en Phase 1
                if state == SceneState.BLACKOUT and result.get("lights_off"):
                    latency_s = result.get("latency_ms", 0) / 1000.0
                    self._metrics.mark_at(
                        "first_visible_effect", phase_offset + latency_s
                    )
            if self._tracking is not None and self._tracking_id:
                try:
                    self._tracking.update(
                        self._tracking_id,
                        log=f"{name} ({duration:.1f}s)",
                        extra={"phase": name},
                    )
                except Exception:
                    pass

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

    def _anticipation_enabled(self) -> bool:
        """Anticipation musique activee via config (opt-in)."""
        return bool(
            self.config.get("scenes", {})
            .get("ironman", {})
            .get("anticipate_music", False)
        )

    def _preload_tts(self):
        """Precharge Piper TTS en arriere-plan (evite 1-3s en Phase 5)."""
        try:
            self._phase5._get_tts()
            logger.info("[IRONMAN] TTS precharge")
        except Exception as e:
            logger.debug(f"[IRONMAN] preload TTS: {e}")

    def _execute_phase1(self) -> dict:
        """
        Execute Phase 1 - Blackout.

        Si l'anticipation musique est activee, un thread prepare la TV
        (screensaver ou power-on) et lance YouTube pendant le noir --
        la musique demarre alors ~au flash de la Phase 2.
        """
        self._anticipator = None
        # Anticiper seulement si la Phase 2 va suivre (sinon on
        # lancerait une musique orpheline pendant un test de blackout)
        if self._anticipation_enabled() and 2 in self._current_selection:
            tv_cfg = self.config.get("tv", {})
            user, password = tv_cfg.get("user", ""), tv_cfg.get("pass", "")
            auth = HTTPDigestAuth(user, password) if user and password else None
            video_id = (
                self.config.get("scenes", {}).get("ironman", {})
                .get("youtube_video_id", YOUTUBE_VIDEO_ID)
            )
            tv_power = (self._saved_state or {}).get("tv", {}).get("power", "unknown")

            self._anticipator = MusicAnticipator(
                tv_host=tv_cfg.get("host", "192.168.1.50"),
                tv_auth=auth,
                video_id=video_id,
                tv_power=tv_power,
            )
            self._anticipator.start()
            # La TV est geree par l'anticipateur: pas de standby en Phase 1
            return self._phase1.execute(skip_tv=True)

        return self._phase1.execute()

    def _execute_phase2(self) -> dict:
        """Execute Phase 2 - Impact (puis lance hue_beat en avance)."""
        anticipator = self._anticipator
        if anticipator is not None:
            # L'anticipation se termine ~T+2s du blackout: deja finie ici
            anticipator.done.wait(timeout=4)

        result = self._phase2.execute(anticipator=anticipator)

        # Timestamp de lancement YouTube pour la sync Phase 3
        if anticipator is not None and anticipator.music_started:
            self._youtube_launch_time = anticipator.launch_time
        else:
            self._youtube_launch_time = result.get("youtube_launch_time")

        # Lancer hue_beat des maintenant (non bloquant): il demarre
        # pendant la fin de l'impact, la Phase 3 le poll au lieu de dormir
        self._start_hue_beat()
        return result

    def _execute_phase3(self) -> dict:
        """Execute Phase 3 - Buildup avec hue_beat audio-reactif."""
        # hue_beat a ete lance en fin de Phase 2: attendre qu'il soit
        # pret (poll PID, max 2.5s) au lieu de l'ancien sleep(2.5) fixe
        self._wait_hue_beat(timeout=2.5)

        # Calculer le délai avant que la vidéo commence vraiment
        video_start_delay = 0.0
        if self._youtube_launch_time is not None:
            time_since_launch = time.perf_counter() - self._youtube_launch_time
            YOUTUBE_LOAD_TIME = 2.5  # secondes pour charger
            video_start_delay = max(0.0, YOUTUBE_LOAD_TIME - time_since_launch)
            logger.info(f"[IRONMAN] YouTube lancé il y a {time_since_launch:.1f}s, attente vidéo: {video_start_delay:.1f}s")

        result = self._phase3.execute(video_start_delay=video_start_delay)

        # En mode pulses pilotes, la scene (et non hue_beat) decide de
        # l'arret: on coupe des la fin de la Phase 3 pour rendre la main
        # au REST des Phases 4-5 (fondu + pulse TTS redeviennent visibles,
        # le stream Entertainment ecrasait tout en le laissant tourner)
        if result.get("mode") == "hue_beat_ctrl":
            self._stop_hue_beat()

        return result

    def _execute_phase4(self) -> dict:
        """Execute Phase 4 - Transition (hue_beat continue)."""
        return self._phase4.execute()

    def _execute_phase5(self) -> dict:
        """Execute Phase 5 - TTS, puis arret hue_beat."""
        result = self._phase5.execute()
        self._stop_hue_beat()
        return result

    def _rollback(self, wake_pc: bool = True):
        """
        Restaure l'etat initial apres une erreur.

        Utilise l'etat sauvegarde par Phase 0.

        Args:
            wake_pc: rallume les ecrans PC (True sur erreur; False pour
                     la restauration de fin de sous-scene, ou la sortie
                     clavier / l'auto-wake s'en chargent)
        """
        logger.info("[IRONMAN] Rollback started")
        self._state = SceneState.ROLLBACK

        # Arreter hue_beat si actif
        self._stop_hue_beat()

        # Rallumer les ecrans PC (erreur => on ne laisse pas l'utilisateur
        # dans le noir)
        if wake_pc and self._phase1 is not None:
            self._phase1.pc_screens.wake()

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

        def _restore_light(light_id: str, light_state: dict):
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

        lights = hue_state.get("lights", {})
        if not lights:
            return
        # Restauration en parallele: fidele par lumiere, sans payer
        # 5 aller-retours sequentiels
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(lights)) as pool:
            for light_id, light_state in lights.items():
                pool.submit(_restore_light, light_id, light_state)

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

            # Restaurer ambilight (power On d'abord: la Phase 1 l'a coupe)
            ambilight = tv_state.get("ambilight")
            if ambilight:
                url = f"https://{host}:1926/6/ambilight/power"
                requests.post(url, json={"power": "On"}, auth=auth, timeout=3, verify=False)
                url = f"https://{host}:1926/6/ambilight/currentconfiguration"
                requests.post(url, json=ambilight, auth=auth, timeout=3, verify=False)

            logger.debug("TV restauree")

        except Exception as e:
            logger.warning(f"Restauration TV echouee: {e}")

    def run_phases(self, selection: list, rollback: bool = True,
                   validate_first: bool = True) -> dict:
        """
        Execute une selection de phases (sous-scene independante).

        Permet de tester une partie de la scene sans tout lancer:
            orchestrator.run_phases([1])        # blackout seul
            orchestrator.run_phases([2, 3, 4])  # impact -> transition

        Args:
            selection: numeros de phases a executer, dans l'ordre (0-5)
            rollback: restaurer l'etat initial (Hue/TV) a la fin
            validate_first: prefixer la Phase 0 si absente de la selection
                            (necessaire pour capturer l'etat de rollback)

        Returns:
            dict {success, phases_run, phase_results}
        """
        self._init_phases()

        steps = {
            0: (SceneState.VALIDATING, "Phase 0 - Validation", self._execute_phase0),
            1: (SceneState.BLACKOUT, "Phase 1 - Blackout", self._execute_phase1),
            2: (SceneState.IMPACT, "Phase 2 - Impact", self._execute_phase2),
            3: (SceneState.BUILDUP, "Phase 3 - Buildup", self._execute_phase3),
            4: (SceneState.TRANSITION, "Phase 4 - Transition", self._execute_phase4),
            5: (SceneState.TTS, "Phase 5 - TTS", self._execute_phase5),
        }

        invalid = [n for n in selection if n not in steps]
        if invalid:
            return {"success": False, "error": f"Phases invalides: {invalid}",
                    "phases_run": [], "phase_results": {}}

        to_run = list(selection)
        if validate_first and 0 not in to_run:
            to_run.insert(0, 0)

        self._scene_start_time = time.perf_counter()
        self._phase_results = {}
        self._current_selection = to_run
        self._start_telemetry("sub-scene", to_run)
        phases_run = []
        success = True

        if 5 in to_run:
            threading.Thread(target=self._preload_tts, daemon=True).start()

        try:
            for n in to_run:
                state, name, func = steps[n]
                if not self._run_phase(state, name, func):
                    # Seule la Phase 0 retourne False sans lever (validation)
                    success = False
                    break
                phases_run.append(n)

            self._state = SceneState.STABLE if success else SceneState.IDLE

        except Exception as e:
            logger.error(f"[IRONMAN] Sous-scene erreur: {e}")
            success = False
            self._rollback(wake_pc=True)
            self._end_telemetry(success=False)
            return {"success": False, "phases_run": phases_run,
                    "phase_results": self._phase_results}

        finally:
            # hue_beat ne doit jamais survivre a une sous-scene sans Phase 5
            if 3 in phases_run and 5 not in to_run:
                self._stop_hue_beat()

        if rollback and phases_run and phases_run != [0]:
            # Restauration de fin de sous-scene: les ecrans PC restent
            # eteints (sortie clavier ou auto-wake du watcher)
            self._rollback(wake_pc=False)

        self._end_telemetry(success=success)
        return {"success": success, "phases_run": phases_run,
                "phase_results": self._phase_results}

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
