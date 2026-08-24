"""
Lyra Daemon - Serveur socket UNIX.

Processus resident : pipeline RAG chaud, sessions MCP ouvertes, taches async.
Les clients (CLI, REPL, vocal) se connectent sur ~/.lyra/lyra.sock.

Modele : socketserver.ThreadingUnixStreamServer (stdlib), un thread par
connexion, UNE requete pipeline active a la fois (lock global — le LLM et
les MCP ne sont pas concus pour le parallelisme).
"""

from __future__ import annotations

import logging
import os
import signal
import socketserver
import threading
import time
import traceback
from pathlib import Path

from . import state as daemon_state
from .actions import run_request
from .protocol import SOCKET_PATH, ChannelClosed, LineChannel
from .remote_ui import RemoteUI, RequestCancelled

logger = logging.getLogger("lyra.daemon")

INIT_WAIT_TIMEOUT = 180.0   # attente max d'un client pendant l'init
HEARTBEAT_INTERVAL = 15.0


class LyraDaemon:
    """Etat global du demon : pipeline, taches, verrous."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.pipeline = None
        self.task_manager = None
        self.webhook_url = ""
        self.started_at = time.time()
        self.status = daemon_state.STARTING
        self._init_done = threading.Event()
        self._init_error: list = [None]
        self._busy = threading.Lock()
        self._busy_with: str = ""  # requete en cours (pour le message busy)
        self._stop = threading.Event()

    # -- Initialisation ---------------------------------------------------

    def initialize_async(self) -> None:
        threading.Thread(target=self._initialize, daemon=True,
                         name="lyra-init").start()

    def _initialize(self) -> None:
        try:
            import yaml

            from lyra.core.config import RAGConfig
            from lyra.hestia.background_tasks import BackgroundTaskManager
            from lyra.rag_enhanced import EnhancedPipeline
            from lyra.rag_enhanced.config import RAGEnhancedConfig

            config = RAGConfig.from_yaml(self.config_path)
            with open(self.config_path) as f:
                raw = yaml.safe_load(f)
            discord = raw.get("discord", {})
            if discord.get("enabled"):
                self.webhook_url = discord.get("webhook_url", "")

            enhanced_config = RAGEnhancedConfig.from_dict(raw.get("rag_enhanced", {}))
            self.pipeline = EnhancedPipeline(
                config=config,
                enhanced_config=enhanced_config,
                enabled=enhanced_config.enabled,
                tts_mode=False,
            )
            self.pipeline.initialize()
            self.pipeline.preload_models()

            self.task_manager = BackgroundTaskManager()
            restored = self.task_manager.restore_from_registry()
            if restored:
                logger.info("taches restaurees: %d", restored)
            # Surveillance des taches async : sans elle, la fin d'une tache
            # n'est detectee que si un client REPL poll tasks_snapshot — via
            # le chat neutroncore, les sessions tracking restaient "running"
            # pour toujours (regression 2026-08-14).
            threading.Thread(target=self._watch_tasks, daemon=True,
                             name="lyra-task-watch").start()

            self.status = daemon_state.READY
            daemon_state.write_state(daemon_state.READY)
            logger.info("demon pret en %.1fs", time.time() - self.started_at)
        except Exception as e:  # noqa: BLE001 - remonte aux clients
            self._init_error[0] = e
            logger.error("echec init: %s\n%s", e, traceback.format_exc())
            daemon_state.write_state(daemon_state.STARTING,
                                    reason=f"echec init: {e}")
        finally:
            self._init_done.set()

    def _watch_tasks(self) -> None:
        """Poll les taches async : check_task detecte les fins et notifie le
        tracking (complete/error) + les notifications de completion."""
        while not self._stop.wait(5.0):
            manager = self.task_manager
            if manager is None:
                continue
            try:
                manager.get_active_tasks()
            except Exception as e:  # noqa: BLE001 - la boucle doit survivre
                logger.warning("watch_tasks: %s", e)

    def wait_ready(self, timeout: float = INIT_WAIT_TIMEOUT) -> None:
        """Bloque jusqu'a la fin de l'init ; leve si elle a echoue."""
        if not self._init_done.wait(timeout):
            raise RuntimeError("initialisation trop longue")
        if self._init_error[0] is not None:
            raise RuntimeError(f"initialisation echouee: {self._init_error[0]}")

    # -- Infos ------------------------------------------------------------

    def health(self) -> dict:
        data = {
            "status": self.status,
            "pid": os.getpid(),
            "uptime_s": round(time.time() - self.started_at, 1),
        }
        if self.pipeline is not None and self._init_done.is_set() and \
                self._init_error[0] is None:
            try:
                v2 = self.pipeline._pipeline_v2
                data["mcp_servers"] = list(v2._hestia.mcp_manager.clients.keys())
                data["sessions"] = len(v2._sessions)
            except Exception:  # noqa: BLE001 - health ne doit jamais planter
                pass
        if self.task_manager is not None:
            data["active_tasks"] = len(self.task_manager.get_active_tasks())
        return data

    def tasks_snapshot(self) -> dict:
        if self.task_manager is None:
            return {"active": [], "errors": [], "notifications": []}
        manager = self.task_manager

        def _fmt(task):
            return {
                "task_id": task.task_id,
                "tool_name": task.tool_name,
                "description": task.description,
                "started_at": task.started_at.isoformat(),
                "estimated_time": task.estimated_time,
                "progress": manager.get_task_progress(task.task_id),
            }

        return {
            "active": [_fmt(t) for t in manager.get_active_tasks()],
            "errors": [_fmt(t) for t in getattr(manager, "persistent_errors", [])],
            "notifications": [n for n in manager.get_completed_notifications()],
        }

    # -- Traitement d'une requete ----------------------------------------

    def handle_request(self, channel: LineChannel, message: dict,
                       session_id: str) -> None:
        rui = RemoteUI(channel)

        if not self._init_done.is_set():
            rui.info("Je finis de charger mes modeles, un instant...")
        try:
            self.wait_ready()
        except RuntimeError as e:
            rui.error(str(e))
            channel.send({"type": "result", "exit_code": 1, "executed": False})
            return

        if not self._busy.acquire(blocking=False):
            what = f" (\u00ab {self._busy_with} \u00bb)" if self._busy_with else ""
            channel.send({"type": "busy",
                          "text": f"Je suis occupee avec une autre requete{what}, "
                                  "je suis a toi juste apres."})
            self._busy.acquire()

        options = message.get("options", {})
        self._busy_with = str(message.get("text", ""))[:60]
        try:
            code = run_request(
                self.pipeline,
                self.task_manager,
                str(message.get("text", "")),
                rui,
                session_id=session_id,
                mode=options.get("mode", "default"),
                yes=bool(options.get("yes", False)),
                interactive=bool(options.get("interactive", False)),
                webhook_url=self.webhook_url,
            )
            channel.send({"type": "result", "exit_code": code, "executed": True})
        except RequestCancelled as e:
            logger.info("requete annulee (%s)", e)
            try:
                channel.send({"type": "result", "exit_code": 2, "executed": False})
            except ChannelClosed:
                pass
        except ChannelClosed:
            logger.info("client parti pendant la requete")
        except Exception as e:  # noqa: BLE001 - jamais tuer le demon
            logger.error("erreur requete: %s\n%s", e, traceback.format_exc())
            try:
                rui.error(f"Erreur interne du demon: {e}")
                channel.send({"type": "result", "exit_code": 1, "executed": False})
            except ChannelClosed:
                pass
        finally:
            self._busy_with = ""
            self._busy.release()


class _ConnectionHandler(socketserver.StreamRequestHandler):
    """Une connexion client : boucle de messages jusqu'a deconnexion."""

    def handle(self) -> None:  # noqa: D102
        daemon: LyraDaemon = self.server.daemon  # type: ignore[attr-defined]
        channel = LineChannel(self.connection)
        session_id = "default"
        try:
            while not daemon._stop.is_set():
                message = channel.recv(timeout=None)
                mtype = message.get("type")
                if mtype == "hello":
                    session_id = str(message.get("session") or "default")
                    channel.send({"type": "ready", "status": daemon.status,
                                  "uptime": round(time.time() - daemon.started_at, 1)})
                elif mtype == "ping":
                    channel.send({"type": "pong"})
                elif mtype == "health":
                    channel.send({"type": "health", "data": daemon.health()})
                elif mtype == "tasks_poll":
                    channel.send({"type": "tasks", **daemon.tasks_snapshot()})
                elif mtype == "request":
                    daemon.handle_request(channel, message, session_id)
                elif mtype in ("cancel", "answer"):
                    # Message d'annulation/reponse arrive apres la fin de la
                    # requete (client qui a annule tardivement) : ignorer.
                    pass
                else:
                    channel.send({"type": "error",
                                  "text": f"type de message inconnu: {mtype}"})
        except (ChannelClosed, ValueError, TimeoutError):
            pass
        finally:
            channel.close()


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def _socket_in_use(path: Path) -> bool:
    """True si un demon ecoute deja sur ce socket."""
    import socket as socket_mod
    if not path.exists():
        return False
    sock = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect(str(path))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def serve(config_path: str = "config.yaml",
          socket_path: Path = SOCKET_PATH) -> int:
    """Point d'entree du demon. Retourne un code de sortie."""
    if _socket_in_use(socket_path):
        logger.error("un demon Lyra ecoute deja sur %s", socket_path)
        return 1
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)  # socket orphelin d'un crash

    daemon = LyraDaemon(config_path)
    daemon_state.write_state(daemon_state.STARTING)
    daemon.initialize_async()

    server = _Server(str(socket_path), _ConnectionHandler)
    server.daemon = daemon  # type: ignore[attr-defined]
    os.chmod(socket_path, 0o600)

    def _shutdown(signum, _frame):
        logger.info("arret demande (signal %d)", signum)
        daemon._stop.set()
        daemon_state.write_state(daemon_state.STOPPED,
                                reason=f"signal {signum}")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    def _heartbeat():
        while not daemon._stop.wait(HEARTBEAT_INTERVAL):
            daemon_state.write_state(daemon.status)

    threading.Thread(target=_heartbeat, daemon=True,
                     name="lyra-heartbeat").start()

    logger.info("demon Lyra en ecoute sur %s (pid %d)", socket_path, os.getpid())
    try:
        server.serve_forever()
    finally:
        server.server_close()
        socket_path.unlink(missing_ok=True)
    return 0
