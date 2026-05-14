"""
Lyra V1 - Integration n8n pour operations asynchrones

Permet de declencher des workflows n8n pour les operations longues
(clone VM, backup create/restore) sans bloquer Lyra.

Si n8n n'est pas disponible ou les webhooks ne sont pas actifs,
utilise un fallback subprocess pour executer en arriere-plan.
"""

import os
import json
import subprocess
import threading
import time
from typing import Optional, Callable
from dataclasses import dataclass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False


def send_discord_notification(
    webhook_url: str,
    title: str,
    description: str = "",
    fields: list = None,
    color: int = 3066993,  # Green by default
    footer: str = "Lyra DevOps Assistant - Mode Fallback"
) -> bool:
    """Envoie une notification Discord via webhook.

    Args:
        webhook_url: URL du webhook Discord
        title: Titre de l'embed
        description: Description (peut contenir du code avec ```)
        fields: Liste de {"name": str, "value": str, "inline": bool}
        color: Couleur de l'embed (3066993=vert, 15158332=rouge)
        footer: Texte du footer

    Returns:
        True si envoi reussi
    """
    if not webhook_url:
        return False

    embed = {
        "title": title,
        "color": color,
        "footer": {"text": footer}
    }

    if description:
        embed["description"] = description

    if fields:
        embed["fields"] = fields

    payload = {"embeds": [embed]}

    try:
        # Utiliser requests si disponible (plus fiable que urllib)
        if HAS_REQUESTS:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            return response.status_code in (200, 204)
        else:
            # Fallback urllib
            payload_json = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=payload_json,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status in (200, 204)
    except Exception as e:
        print(f"[Discord] Erreur envoi: {e}")
        return False


@dataclass
class N8nConfig:
    """Configuration n8n."""
    base_url: str = "http://localhost:5678"
    api_key: Optional[str] = None
    enabled: bool = False

    # Webhooks pour les operations async
    webhooks: dict = None

    def __post_init__(self):
        if self.webhooks is None:
            self.webhooks = {
                "clone-vm": "/webhook/lyra-clone-vm",
                "backup-create": "/webhook/lyra-backup-create",
                "backup-restore": "/webhook/lyra-backup-restore",
            }


@dataclass
class N8nResult:
    """Resultat d'un appel n8n."""
    success: bool
    message: str
    workflow_id: Optional[str] = None
    execution_id: Optional[str] = None
    error: Optional[str] = None


class N8nClient:
    """Client pour interagir avec n8n."""

    def __init__(self, config: Optional[N8nConfig] = None):
        self.config = config or N8nConfig()

    def is_available(self) -> bool:
        """Verifie si n8n est accessible."""
        try:
            req = urllib.request.Request(
                f"{self.config.base_url}/healthz",
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                return data.get("status") == "ok"
        except Exception:
            return False

    def trigger_workflow(self, workflow: str, data: dict = None) -> N8nResult:
        """Declenche un workflow n8n via webhook.

        Args:
            workflow: Nom du workflow (clone-vm, backup-create, backup-restore)
            data: Donnees a passer au workflow

        Returns:
            N8nResult avec le status
        """
        if not self.config.enabled:
            return N8nResult(
                success=False,
                message="n8n est desactive dans la configuration",
                error="N8N_DISABLED"
            )

        webhook_path = self.config.webhooks.get(workflow)
        if not webhook_path:
            return N8nResult(
                success=False,
                message=f"Workflow inconnu: {workflow}",
                error="UNKNOWN_WORKFLOW"
            )

        url = f"{self.config.base_url}{webhook_path}"
        payload = json.dumps(data or {}).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode())

                return N8nResult(
                    success=True,
                    message=f"Workflow '{workflow}' declenche",
                    workflow_id=result.get("workflowId"),
                    execution_id=result.get("executionId")
                )

        except urllib.error.HTTPError as e:
            return N8nResult(
                success=False,
                message=f"Erreur HTTP {e.code}",
                error=str(e)
            )
        except urllib.error.URLError as e:
            return N8nResult(
                success=False,
                message="n8n non accessible",
                error=str(e)
            )
        except Exception as e:
            return N8nResult(
                success=False,
                message=f"Erreur: {e}",
                error=str(e)
            )

    def get_executions(self, limit: int = 5, workflow_id: str = None) -> list:
        """Recupere les dernieres executions n8n.

        Args:
            limit: Nombre max d'executions a retourner
            workflow_id: Filtrer par workflow (optionnel)

        Returns:
            Liste des executions
        """
        try:
            url = f"{self.config.base_url}/api/v1/executions?limit={limit}"
            if workflow_id:
                url += f"&workflowId={workflow_id}"

            headers = {}
            if self.config.api_key:
                headers["X-N8N-API-KEY"] = self.config.api_key

            req = urllib.request.Request(url, headers=headers, method="GET")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return data.get("data", [])

        except Exception as e:
            return []

    def format_executions(self, executions: list) -> str:
        """Formate les executions pour affichage."""
        if not executions:
            return "Aucune execution recente."

        lines = ["Dernieres executions n8n:", ""]

        for exec in executions[:5]:
            status = exec.get("status", "unknown")
            workflow = exec.get("workflowData", {}).get("name", "?")
            finished = exec.get("stoppedAt", "en cours")

            status_icon = {
                "success": "[OK]",
                "error": "[X]",
                "running": "[...]",
                "waiting": "[~]"
            }.get(status, "[?]")

            lines.append(f"  {status_icon} {workflow} - {status} ({finished})")

        return "\n".join(lines)


# Operations async disponibles
ASYNC_OPERATIONS = {
    "clone-vm": {
        "description": "Clone une VM (operation longue ~60s)",
        "params": ["source_vm", "new_vm_name"],
        "workflow": "clone-vm"
    },
    "backup-create": {
        "description": "Cree un backup complet (operation longue ~120s)",
        "params": ["type"],
        "workflow": "backup-create"
    },
    "backup-restore": {
        "description": "Restaure un backup (operation longue ~60s)",
        "params": ["type", "identifier"],
        "workflow": "backup-restore"
    }
}


def should_use_async(tool_name: str, arguments: dict) -> bool:
    """Determine si une operation devrait etre executee en async via n8n.

    Args:
        tool_name: Nom de l'outil MCP
        arguments: Arguments de l'outil

    Returns:
        True si l'operation devrait etre async
    """
    # Mapping outil MCP -> operation async
    # Inclut les variantes avec point (vm.clone) et underscore (vm_clone)
    async_tools = {
        "vm_clone": "clone-vm",
        "vm.clone": "clone-vm",
        "vm_clone_system": "clone-vm",
        "vm.clone_system": "clone-vm",
        "backup_create": "backup-create",
        "backup.create": "backup-create",
        "backup_restore": "backup-restore",
        "backup.restore": "backup-restore",
    }

    return tool_name in async_tools


def get_async_workflow(tool_name: str) -> Optional[str]:
    """Retourne le nom du workflow n8n pour un outil."""
    mapping = {
        "vm_clone": "clone-vm",
        "vm.clone": "clone-vm",
        "vm_clone_system": "clone-vm",
        "vm.clone_system": "clone-vm",
        "backup_create": "backup-create",
        "backup.create": "backup-create",
        "backup_restore": "backup-restore",
        "backup.restore": "backup-restore",
    }
    return mapping.get(tool_name)


# Scripts de fallback pour execution directe sans n8n
# Inclut les variantes avec point et underscore
FALLBACK_COMMANDS = {
    "vm_clone": "/home/amineutron/dev/fedora-setup/scripts/kvm/kvm-clone.sh {source_vm} {new_vm_name} --start",
    "vm.clone": "/home/amineutron/dev/fedora-setup/scripts/kvm/kvm-clone.sh {source_vm} {new_vm_name} --start",
    "vm_clone_system": "/home/amineutron/dev/fedora-setup/scripts/agents/vm-controller/vm-clone-system.sh {name} --memory {memory} --cpus {cpus}",
    "vm.clone_system": "/home/amineutron/dev/fedora-setup/scripts/agents/vm-controller/vm-clone-system.sh {name} --memory {memory} --cpus {cpus}",
    "backup_create": "/home/amineutron/dev/fedora-setup/scripts/agents/backup-manager/backup-manager.sh create --type {type}",
    "backup.create": "/home/amineutron/dev/fedora-setup/scripts/agents/backup-manager/backup-manager.sh create --type {type}",
    "backup_restore": "/home/amineutron/dev/fedora-setup/scripts/agents/backup-manager/backup-manager.sh restore --type {type} --identifier {identifier}",
    "backup.restore": "/home/amineutron/dev/fedora-setup/scripts/agents/backup-manager/backup-manager.sh restore --type {type} --identifier {identifier}",
}


class AsyncExecutor:
    """Executeur async pour operations longues (fallback sans n8n)."""

    def __init__(self, on_complete: Optional[Callable] = None):
        self.on_complete = on_complete
        self._running_tasks = {}

    def execute_async(self, tool_name: str, arguments: dict) -> N8nResult:
        """Execute une commande en arriere-plan.

        Args:
            tool_name: Nom de l'outil MCP
            arguments: Arguments de l'outil

        Returns:
            N8nResult indiquant que la tache a ete lancee
        """
        cmd_template = FALLBACK_COMMANDS.get(tool_name)
        if not cmd_template:
            return N8nResult(
                success=False,
                message=f"Pas de commande fallback pour {tool_name}",
                error="NO_FALLBACK"
            )

        # Substituer les arguments dans la commande
        try:
            # Remplir avec des valeurs par defaut si manquantes
            # Support des variantes de noms (MCP peut envoyer source_vm_name ou source_vm)
            safe_args = {
                "source_vm": arguments.get("source_vm") or arguments.get("source_vm_name", ""),
                "new_vm_name": arguments.get("new_vm_name") or arguments.get("target_vm_name", ""),
                "name": arguments.get("name", ""),
                "memory": arguments.get("memory", 4096),
                "cpus": arguments.get("cpus", 2),
                "type": arguments.get("type", "timeshift"),
                "identifier": arguments.get("identifier", ""),
            }
            cmd = cmd_template.format(**safe_args)
        except KeyError as e:
            return N8nResult(
                success=False,
                message=f"Parametre manquant: {e}",
                error="MISSING_PARAM"
            )

        # Lancer en arriere-plan
        def run_task():
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes max
                )

                success = result.returncode == 0
                if self.on_complete:
                    self.on_complete(tool_name, arguments, success, result.stdout, result.stderr)

            except subprocess.TimeoutExpired:
                if self.on_complete:
                    self.on_complete(tool_name, arguments, False, "", "Timeout apres 10 minutes")
            except Exception as e:
                if self.on_complete:
                    self.on_complete(tool_name, arguments, False, "", str(e))

        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()

        task_id = f"{tool_name}_{id(thread)}"
        self._running_tasks[task_id] = thread

        return N8nResult(
            success=True,
            message=f"Tache lancee en arriere-plan (fallback mode)",
            execution_id=task_id
        )


# Instance globale pour le fallback
_async_executor = None

def get_async_executor(on_complete: Optional[Callable] = None) -> AsyncExecutor:
    """Retourne l'executeur async global."""
    global _async_executor
    if _async_executor is None:
        _async_executor = AsyncExecutor(on_complete)
    return _async_executor
