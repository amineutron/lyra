"""
Lyra HESTIA - Executor.

Module Python pur pour l'execution MCP.
Wrap le MCPManager existant avec logging optionnel.
"""

import sys
import time
import subprocess
import json
import os
import signal
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Import du MCPManager existant
sys.path.insert(0, str(__file__).replace("/lyra/hestia/executor.py", ""))
from modules.mcp import MCPManager, MCPResult

from .metrics import MetricsCollector
from .notion_logger import NotionLogger
from .tracking_client import TrackingClient


# Operations longues executees en arriere-plan
ASYNC_TOOLS = {
    "vm_clone": {
        "estimated_time": "1-2 minutes",
        "description": "Clonage de VM"
    },
    "vm_clone_system": {
        "estimated_time": "10-30 minutes",
        "description": "Clonage du systeme complet"
    },
    "backup_create": {
        "estimated_time": "2-5 minutes",
        "description": "Creation de backup"
    },
    "backup_restore": {
        "estimated_time": "2-5 minutes",
        "description": "Restauration de backup"
    },
    "vm_export": {
        "estimated_time": "10-20 minutes",
        "description": "Export et sanitarisation de VM"
    },
    "vm_import": {
        "estimated_time": "5-10 minutes",
        "description": "Import de VM depuis archive"
    },
}


@dataclass
class ExecutionContext:
    """Contexte d'execution."""
    user_query: str
    tool_name: str
    arguments: dict
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResult:
    """Resultat d'execution enrichi."""
    success: bool
    content: str
    error: Optional[str] = None
    duration_ms: float = 0.0
    logged_to_notion: bool = False


class HestiaExecutor:
    """HESTIA - Executeur MCP.

    Wrap le MCPManager existant pour:
    - Execution des outils MCP
    - Collecte de metriques
    - Logging optionnel vers Notion

    Nom: HESTIA, deesse du foyer, gardienne de la maison.
    Elle execute les taches domestiques (MCP) avec soin.
    """

    def __init__(
        self,
        config: dict,
        notion_enabled: bool = False,
        notion_config: Optional[dict] = None,
        verbose: bool = False
    ):
        """Initialise HESTIA.

        Args:
            config: Configuration complete (avec section mcp)
            notion_enabled: Activer le logging Notion
            notion_config: Configuration Notion optionnelle
            verbose: Afficher les details MCP (defaut: False)
        """
        # MCPManager existant
        self.mcp_manager = MCPManager(config, verbose=verbose)

        # Client tracking HTTP
        tracking_cfg = config.get("tracking", {})
        self._tracking = TrackingClient(
            api_url=tracking_cfg.get("api_url", "http://127.0.0.1:8765"),
            server_script=tracking_cfg.get("server_script", "/home/amineutron/dev/MCP/tracking/server.py"),
            venv_python=tracking_cfg.get("venv_python", "/home/amineutron/dev/MCP/tracking/.venv/bin/python"),
        )

        # Metriques
        self.metrics = MetricsCollector()

        # Notion logger (optionnel)
        self.notion: Optional[NotionLogger] = None
        if notion_enabled and notion_config:
            try:
                self.notion = NotionLogger(
                    token=notion_config.get("token"),
                    database_id=notion_config.get("database_id")
                )
            except Exception as e:
                print(f"[HESTIA] Notion logger disabled: {e}", file=sys.stderr)

    def execute(
        self,
        tool_name: str,
        arguments: dict,
        context: Optional[ExecutionContext] = None
    ) -> ExecutionResult:
        """Execute un outil MCP.

        Args:
            tool_name: Nom de l'outil (avec ou sans prefixe)
            arguments: Arguments de l'outil
            context: Contexte d'execution optionnel

        Returns:
            ExecutionResult avec le resultat
        """
        start_time = time.time()

        # Intercepter les outils tracking (HTTP local, pas MCP fedora)
        tool_short = tool_name.split(".")[-1] if "." in tool_name else tool_name
        if tool_name.startswith("tracking.") or tool_name == "open_tracking_ui":
            return self._execute_tracking(tool_short, arguments)

        # Intercepter la scene Iron Man (script local, pas MCP)
        if tool_name.startswith("ironman."):
            return self._execute_ironman()

        # Log debut (Notion)
        if self.notion and context:
            self.notion.log_start(context)

        # Execution via MCPManager
        try:
            result = self.mcp_manager.call_tool(tool_name, arguments)
        except Exception as e:
            result = MCPResult(
                success=False,
                content="",
                error=str(e)
            )

        duration_ms = (time.time() - start_time) * 1000

        # Metriques
        self.metrics.record_execution(
            tool_name=tool_name,
            success=result.success,
            duration_ms=duration_ms
        )

        # Log fin (Notion)
        logged = False
        if self.notion and context:
            logged = self.notion.log_end(
                context=context,
                success=result.success,
                result=result.content if result.success else result.error,
                duration_ms=duration_ms
            )

        return ExecutionResult(
            success=result.success,
            content=result.content,
            error=result.error,
            duration_ms=duration_ms,
            logged_to_notion=logged
        )

    def _execute_tracking(self, action: str, arguments: dict) -> "ExecutionResult":
        """Execute une action tracking via l'API HTTP locale."""
        try:
            if action == "list":
                sessions = self._tracking.list_all()
                if not sessions:
                    content = "Aucune session de tracking en cours."
                else:
                    template_filter = arguments.get("template")
                    status_filter = arguments.get("status")
                    filtered = [
                        s for s in sessions
                        if (not template_filter or s.get("template") == template_filter)
                        and (not status_filter or s.get("status") == status_filter)
                    ]
                    if not filtered:
                        content = "Aucune session correspondant aux filtres."
                    else:
                        lines = []
                        for s in filtered:
                            pct = round(s.get("processed", 0) / max(s.get("total", 100), 1) * 100)
                            extra = s.get("extra", {})
                            phase = extra.get("phase", "")
                            eta = extra.get("eta", "")
                            line = f"  [{s['id']}] {s['name']} — {s['status']} {pct}%"
                            if phase:
                                line += f" | {phase}"
                            if eta:
                                line += f" | eta: {eta}"
                            lines.append(line)
                        content = "\n".join(lines)

            elif action == "get":
                sid = arguments.get("session_id", "")
                s = self._tracking.get(sid)
                if not s:
                    content = f"Session '{sid}' introuvable."
                else:
                    pct = round(s.get("processed", 0) / max(s.get("total", 100), 1) * 100)
                    extra = s.get("extra", {})
                    logs = s.get("logs", [])[-3:]
                    log_lines = "\n".join(f"    {e.get('message','')}" for e in logs)
                    content = (
                        f"[{s['id']}] {s['name']}\n"
                        f"  statut: {s['status']} | {pct}%\n"
                        f"  operation: {extra.get('operation','')} | cible: {extra.get('target','')}\n"
                        f"  phase: {extra.get('phase','')} | eta: {extra.get('eta','')}\n"
                        + (f"  logs:\n{log_lines}" if log_lines else "")
                    )

            elif action == "delete":
                sid = arguments.get("session_id", "")
                self._tracking.delete(sid)
                content = f"Session '{sid}' supprimee."

            elif action == "open_ui":
                self._tracking.open_ui(filter_template=arguments.get("filter_template"))
                content = "Dashboard tracking ouvert."

            elif action == "kill_task":
                content = self._kill_background_task(arguments.get("identifier", ""))

            else:
                content = f"Action tracking inconnue: {action}"

            return ExecutionResult(success=True, content=content)

        except Exception as e:
            return ExecutionResult(success=False, content="", error=str(e))

    def _kill_background_task(self, identifier: str) -> str:
        """Tue une tache en arriere-plan par tracking_id, task_id (partiel) ou nom.

        Args:
            identifier: tracking_id, task_id (ou suffixe), ou mot-cle du nom

        Returns:
            Message resultat
        """
        registry_path = Path.home() / ".lyra" / "active_tasks.json"
        if not registry_path.exists():
            return "Aucune tache active trouvee."

        try:
            tasks = json.loads(registry_path.read_text())
        except Exception:
            return "Impossible de lire le registre des taches."

        if not tasks:
            return "Aucune tache active en cours."

        identifier = identifier.strip().lower()

        # Chercher par tracking_id, task_id (complet ou suffixe), ou nom (substring)
        matched = None
        for task in tasks:
            tid = task.get("tracking_id", "").lower()
            task_id = task.get("task_id", "").lower()
            name = task.get("description", "").lower()
            if (identifier == tid
                    or identifier == task_id
                    or task_id.endswith(identifier)
                    or identifier in name):
                matched = task
                break

        if not matched:
            candidates = [f"  [{t.get('tracking_id','?')}] {t.get('description','?')}" for t in tasks]
            return (
                f"Tache '{identifier}' introuvable.\n"
                f"Taches actives:\n" + "\n".join(candidates)
            )

        task_id = matched.get("task_id", "")
        tracking_id = matched.get("tracking_id", "")
        pid_file = matched.get("pid_file", "")
        description = matched.get("description", task_id)

        # Tuer le process group via pid_file
        killed = False
        if pid_file and os.path.exists(pid_file):
            try:
                pid = int(Path(pid_file).read_text().strip())
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                killed = True
            except (ProcessLookupError, PermissionError, ValueError, OSError):
                pass

        # Marquer le tracking en erreur
        if tracking_id:
            self._tracking.error(tracking_id, message="Annule par l'utilisateur")

        # Nettoyer le registre
        try:
            remaining = [t for t in tasks if t.get("task_id") != task_id]
            registry_path.write_text(json.dumps(remaining, indent=2))
            # Nettoyer les fichiers temporaires
            for fpath in [pid_file, f"/tmp/lyra_task_{task_id}.progress"]:
                if fpath:
                    Path(fpath).unlink(missing_ok=True)
        except Exception:
            pass

        if killed:
            return f"Tache '{description}' [{tracking_id}] arretee (SIGTERM)."
        else:
            return f"Tache '{description}' [{tracking_id}] marquee comme annulee (process deja termine ou introuvable)."

    def _execute_ironman(self) -> "ExecutionResult":
        """Lance la scene Iron Man via ironman_run.sh en background."""
        script = "/home/amineutron/dev/iron-man/scripts/ironman_run.sh"
        log_file = "/tmp/ironman_lyra.log"
        try:
            with open(log_file, "w") as f:
                subprocess.Popen(
                    ["bash", script],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                )
            return ExecutionResult(
                success=True,
                content="Scene Iron Man lancee. Back in Black arrive dans quelques secondes.",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                content="",
                error=f"Impossible de lancer la scene Iron Man: {e}",
            )

    def get_available_tools(self) -> list[dict]:
        """Retourne la liste des outils disponibles."""
        return self.mcp_manager.get_all_tools()

    def get_servers(self) -> list[str]:
        """Retourne la liste des serveurs MCP."""
        return self.mcp_manager.get_server_names()

    def is_dangerous_tool(self, tool_name: str) -> bool:
        """Verifie si un outil est dangereux.

        Args:
            tool_name: Nom de l'outil

        Returns:
            True si l'outil est dangereux
        """
        dangerous = [
            "vm_destroy",
            "vm_delete",
            "backup_restore",
            "backup_clean",
        ]
        # Normaliser le nom
        base_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
        return base_name in dangerous

    def is_async_tool(self, tool_name: str) -> bool:
        """Verifie si un outil doit etre execute en arriere-plan.

        Args:
            tool_name: Nom de l'outil

        Returns:
            True si l'outil doit etre async
        """
        base_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
        return base_name in ASYNC_TOOLS

    def get_async_info(self, tool_name: str) -> Optional[dict]:
        """Retourne les infos async d'un outil.

        Args:
            tool_name: Nom de l'outil

        Returns:
            Dict avec estimated_time et description, ou None
        """
        base_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
        return ASYNC_TOOLS.get(base_name)

    def get_metrics(self) -> dict:
        """Retourne les metriques collectees."""
        return self.metrics.get_summary()

    def close(self):
        """Ferme les connexions."""
        self.mcp_manager.close()
