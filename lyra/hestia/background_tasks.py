"""
Background Task Manager for HESTIA.

Gere l'execution des operations longues en arriere-plan.
"""

import subprocess
import time
import json
import os
import signal
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .tracking_client import TrackingClient


REGISTRY_PATH = Path.home() / ".lyra" / "active_tasks.json"


@dataclass
class BackgroundTask:
    """Tache en arriere-plan."""
    task_id: str
    tool_name: str
    arguments: dict
    started_at: datetime
    description: str
    estimated_time: str
    process: Optional[subprocess.Popen] = None
    completed: bool = False
    success: Optional[bool] = None
    result: Optional[str] = None
    error: Optional[str] = None
    pid_file: Optional[str] = None   # chemin vers /tmp/lyra_task_{task_id}.pid
    tracking_id: Optional[str] = None  # session_id MCP tracking

    def get_pid(self) -> Optional[int]:
        """Retourne le PID du process depuis le pid_file."""
        if not self.pid_file or not os.path.exists(self.pid_file):
            return None
        try:
            return int(Path(self.pid_file).read_text().strip())
        except Exception:
            return None

    def is_alive(self) -> bool:
        """Verifie si le process est encore en vie (par PID ou Popen)."""
        if self.process is not None:
            return self.process.poll() is None
        pid = self.get_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


class BackgroundTaskManager:
    """Gestionnaire de taches en arriere-plan.

    Permet de lancer des operations MCP longues en subprocess
    et de tracker leur progression.
    """

    def __init__(self, tracking_client: Optional[TrackingClient] = None):
        """Initialise le manager."""
        self.tasks: Dict[str, BackgroundTask] = {}
        self._counter = 0
        self.completed_notifications: List[dict] = []  # Notifications de taches terminees
        self.persistent_errors: List[BackgroundTask] = []  # Taches echouees, gardees dans le bandeau
        self._tracking = tracking_client or TrackingClient()

    def _generate_task_id(self) -> str:
        """Genere un ID unique pour une tache."""
        self._counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"task_{timestamp}_{self._counter:03d}"

    def launch_task(
        self,
        tool_name: str,
        arguments: dict,
        description: str,
        estimated_time: str,
        webhook_url: Optional[str] = None
    ) -> str:
        """Lance une tache en arriere-plan.

        Args:
            tool_name: Nom de l'outil MCP
            arguments: Arguments de l'outil
            description: Description human-friendly
            estimated_time: Temps estime (ex: "1-2 minutes")
            webhook_url: URL webhook Discord pour notification

        Returns:
            L'ID de la tache lancee
        """
        task_id = self._generate_task_id()

        # Creer la session MCP tracking avant le Popen
        tool_short = tool_name.split(".")[-1]
        target = (arguments.get("vm_name")
                  or arguments.get("source_vm")
                  or arguments.get("new_vm_name")
                  or "")
        tracking_id = self._tracking.create(
            name=description,
            template="lyra_task",
            extra={"operation": tool_short, "target": target, "eta": estimated_time},
        )

        # Construire la commande subprocess
        cmd = self._build_command(task_id, tool_name, arguments, webhook_url)

        # Preparer l'env avec LYRA_TRACKING_ID pour que le wrapper puisse
        # mettre a jour la progression en temps reel
        env = os.environ.copy()
        env["LYRA_TRACKING_ID"] = tracking_id or ""

        # Rediriger stdout/stderr vers un fichier log (evite deadlock pipe buffer >64 Ko)
        log_file_path = f"/tmp/lyra_task_{task_id}.log"
        log_file = open(log_file_path, "w")

        # Lancer le subprocess
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
            env=env,
        )
        log_file.close()  # le process herite du fd, on peut fermer notre cote

        # Ecrire le PID dans un fichier pour persistance cross-session
        pid_file = f"/tmp/lyra_task_{task_id}.pid"
        Path(pid_file).write_text(str(process.pid))

        # Creer la tache
        task = BackgroundTask(
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            started_at=datetime.now(),
            description=description,
            estimated_time=estimated_time,
            process=process,
            pid_file=pid_file,
            tracking_id=tracking_id,
        )

        self.tasks[task_id] = task
        self._save_registry()
        return task_id

    def _build_command(
        self,
        task_id: str,
        tool_name: str,
        arguments: dict,
        webhook_url: Optional[str]
    ) -> List[str]:
        """Construit la commande subprocess.

        Args:
            task_id: ID de la tache (pour le fichier de progression)
            tool_name: Nom de l'outil
            arguments: Arguments
            webhook_url: URL webhook Discord

        Returns:
            Liste de commande pour subprocess
        """
        # Construire la commande Python pour appeler le MCP
        # On utilise un script wrapper qui:
        # 1. Execute l'outil MCP
        # 2. Envoie la notification Discord

        script = Path(__file__).parent.parent.parent / "scripts" / "async_mcp_wrapper.py"

        cmd = [
            "python3",
            str(script),
            "--tool", tool_name,
            "--arguments", json.dumps(arguments),
            "--task-id", task_id,
        ]

        if webhook_url:
            cmd.extend(["--webhook", webhook_url])

        return cmd

    def check_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Verifie l'etat d'une tache.

        Args:
            task_id: ID de la tache

        Returns:
            La tache mise a jour, ou None si inexistante
        """
        task = self.tasks.get(task_id)
        if not task or not (task.process or task.pid_file):
            return task

        if task.completed:
            return task

        if task.process is not None:
            # Cas normal : on a un objet Popen
            poll = task.process.poll()
            if poll is not None:
                was_running = not task.completed
                task.completed = True
                task.success = (poll == 0)
                # Lire les dernieres lignes du fichier log (pas de deadlock pipe)
                log_file_path = f"/tmp/lyra_task_{task.task_id}.log"
                log_tail = self._read_log_tail(log_file_path)
                if task.success:
                    task.result = log_tail
                else:
                    task.error = log_tail
                if was_running:
                    self._notify_tracking_completion(task)
                    self._create_completion_notification(task)
                    self._cleanup_task_files(task)
                    self._save_registry()
        else:
            # Cas restaure depuis registre : verifier par PID
            if not task.is_alive():
                was_running = not task.completed
                task.completed = True
                # Lire le code de retour depuis le fichier done (ecrit par async_mcp_wrapper)
                done_file = f"/tmp/lyra_task_{task.task_id}.done"
                if os.path.exists(done_file):
                    try:
                        task.success = (Path(done_file).read_text().strip() == "0")
                    except Exception:
                        task.success = False
                else:
                    # Pas de done_file = interrompu (SIGTERM, crash)
                    task.success = False
                log_file_path = f"/tmp/lyra_task_{task.task_id}.log"
                log_tail = self._read_log_tail(log_file_path)
                if task.success:
                    task.result = log_tail
                else:
                    task.error = log_tail or "Operation interrompue ou echec sans details"
                if was_running:
                    self._notify_tracking_completion(task)
                    self._create_completion_notification(task)
                    self._cleanup_task_files(task)
                    self._save_registry()

        return task

    def _notify_tracking_completion(self, task: BackgroundTask) -> None:
        """Met a jour la session MCP tracking a la fin d'une tache."""
        if not task.tracking_id:
            return
        if task.success:
            self._tracking.complete(
                task.tracking_id,
                log=task.result[:200] if task.result else "Termine avec succes"
            )
        else:
            self._tracking.error(
                task.tracking_id,
                message=task.error[:200] if task.error else "Echec (code retour non nul)"
            )

    def _read_log_tail(self, log_path: str, max_lines: int = 20) -> str:
        """Lit les dernieres lignes du fichier log d'une tache."""
        try:
            if not os.path.exists(log_path):
                return ""
            with open(log_path) as f:
                lines = f.readlines()
            # Garder seulement les lignes significatives (erreurs/resultats)
            tail = "".join(lines[-max_lines:]).strip()
            return tail[:500] if tail else ""
        except Exception:
            return ""

    def _cleanup_task_files(self, task: BackgroundTask):
        """Supprime les fichiers temporaires d'une tache terminee."""
        for path in [
            task.pid_file,
            f"/tmp/lyra_task_{task.task_id}.progress",
            f"/tmp/lyra_task_{task.task_id}.done",
            f"/tmp/lyra_task_{task.task_id}.log",
        ]:
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _save_registry(self):
        """Sauvegarde les taches actives dans le registre persistant."""
        try:
            REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for task in self.tasks.values():
                if not task.completed:
                    data.append({
                        "task_id": task.task_id,
                        "tool_name": task.tool_name,
                        "arguments": task.arguments,
                        "started_at": task.started_at.isoformat(),
                        "description": task.description,
                        "estimated_time": task.estimated_time,
                        "pid_file": task.pid_file or "",
                        "tracking_id": task.tracking_id or "",
                    })
            REGISTRY_PATH.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def restore_from_registry(self) -> int:
        """Charge les taches persistees et verifie si elles tournent encore.

        Appele au demarrage de Lyra. Retourne le nombre de taches restaurees.
        """
        if not REGISTRY_PATH.exists():
            return 0
        try:
            data = json.loads(REGISTRY_PATH.read_text())
        except Exception:
            return 0

        restored = 0
        for entry in data:
            task_id = entry.get("task_id", "")
            if not task_id or task_id in self.tasks:
                continue

            try:
                started_at = datetime.fromisoformat(entry["started_at"])
            except Exception:
                continue

            pid_file = entry.get("pid_file") or None

            task = BackgroundTask(
                task_id=task_id,
                tool_name=entry.get("tool_name", ""),
                arguments=entry.get("arguments", {}),
                started_at=started_at,
                description=entry.get("description", "Operation en cours"),
                estimated_time=entry.get("estimated_time", "?"),
                process=None,  # pas d'objet Popen cross-session
                pid_file=pid_file,
                tracking_id=entry.get("tracking_id") or None,
            )

            if task.is_alive():
                self.tasks[task_id] = task
                restored += 1
            else:
                # Process mort : determiner succes/echec et notifier
                task.completed = True
                done_file = f"/tmp/lyra_task_{task.task_id}.done"
                if os.path.exists(done_file):
                    try:
                        task.success = (Path(done_file).read_text().strip() == "0")
                    except Exception:
                        task.success = False
                else:
                    # Pas de done_file = interrompu (SIGTERM, crash, redemarrage)
                    task.success = False
                    task.error = "Operation interrompue (Lyra redemarree ou process tue)"

                log_file_path = f"/tmp/lyra_task_{task.task_id}.log"
                log_tail = self._read_log_tail(log_file_path)
                if task.success:
                    task.result = log_tail
                elif not task.error:
                    task.error = log_tail or "Echec (aucun detail disponible)"

                # Notifier tracking + UI
                self._notify_tracking_completion(task)
                self._create_completion_notification(task)
                self._cleanup_task_files(task)

        # Reecrire le registre avec seulement les taches vivantes
        self._save_registry()
        return restored

    def stop_task(self, task_id: str) -> bool:
        """Arrete une tache en cours (SIGTERM sur le process group).

        Retourne True si le signal a ete envoye.
        """
        task = self.tasks.get(task_id)
        if not task or task.completed:
            return False

        pid = task.get_pid()
        if pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                return True
            except Exception:
                pass

        if task.process:
            try:
                task.process.terminate()
                return True
            except Exception:
                pass

        return False

    def get_displayable_tasks(self) -> List[BackgroundTask]:
        """Retourne les taches a afficher : actives + erreurs persistantes.

        Returns:
            Liste combinee des taches actives et des erreurs en attente de nettoyage
        """
        return self.get_active_tasks() + self.persistent_errors

    def clear_errors(self):
        """Supprime les taches en erreur du bandeau."""
        self.persistent_errors.clear()

    def _create_completion_notification(self, task: BackgroundTask):
        """Cree une notification de fin de tache.

        Args:
            task: Tache terminee
        """
        duration = (datetime.now() - task.started_at).total_seconds()
        duration_str = f"{int(duration//60)}m {int(duration%60)}s"

        # Construire resume des arguments
        args_summary = []
        for key, value in task.arguments.items():
            if key not in ("start", "verbose", "_default_snapshot_name"):
                args_summary.append(f"{key}: {value}")

        notif = {
            "task_id": task.task_id,
            "description": task.description,
            "success": task.success,
            "duration": duration_str,
            "args_summary": " | ".join(args_summary) if args_summary else "",
            "result": task.result if task.success else task.error
        }

        self.completed_notifications.append(notif)

        # Garder les taches en erreur dans le bandeau jusqu'a nettoyage explicite
        if not task.success:
            self.persistent_errors.append(task)

    def get_active_tasks(self) -> List[BackgroundTask]:
        """Retourne les taches actives (non terminees).

        Returns:
            Liste des taches en cours
        """
        active = []
        for task_id in list(self.tasks.keys()):
            task = self.check_task(task_id)
            if task and not task.completed:
                active.append(task)
        return active

    def get_all_tasks(self) -> List[BackgroundTask]:
        """Retourne toutes les taches.

        Returns:
            Liste de toutes les taches
        """
        return list(self.tasks.values())

    def get_vm_in_use(self, vm_name: str) -> Optional[BackgroundTask]:
        """Verifie si une VM est utilisee par une tache en cours.

        Args:
            vm_name: Nom de la VM

        Returns:
            La tache utilisant cette VM, ou None
        """
        for task in self.get_active_tasks():
            # Verifier dans les arguments
            args = task.arguments
            if args.get("vm_name") == vm_name:
                return task
            if args.get("source_vm") == vm_name:
                return task

        return None

    def get_task_progress(self, task_id: str) -> Optional[dict]:
        """Lit la progression d'une tache depuis son fichier.

        Args:
            task_id: ID de la tache

        Returns:
            {"percentage": 65, "message": "38GB/58GB", "timestamp": ...} ou None
        """
        progress_file = f"/tmp/lyra_task_{task_id}.progress"

        if not os.path.exists(progress_file):
            return None

        try:
            with open(progress_file) as f:
                data = json.load(f)
                return data
        except:
            return None

    def get_completed_notifications(self) -> List[dict]:
        """Retourne les notifications de taches completees.

        Returns:
            Liste des notifications non lues
        """
        return self.completed_notifications

    def clear_notifications(self):
        """Efface les notifications completees."""
        self.completed_notifications.clear()

    def cleanup_completed(self, max_age_seconds: int = 300):
        """Nettoie les taches completees anciennes.

        Args:
            max_age_seconds: Age maximum en secondes (defaut: 5min)
        """
        now = datetime.now()
        to_remove = []

        for task_id, task in self.tasks.items():
            if task.completed:
                age = (now - task.started_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self.tasks[task_id]
