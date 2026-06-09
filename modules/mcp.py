"""
Lyra V1 - Client MCP

Gere la communication avec les serveurs MCP (fedora-agents, pylips, hue, etc.).

Phase 5 ajoute le MCPManager pour gerer plusieurs serveurs MCP avec prefixage.
Phase 5.4 ajoute MCPSessionClient pour les serveurs MCP async (Python).
"""

import json
import subprocess
import os
import sys
import threading
import queue
import time
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPTool:
    """Definition d'un outil MCP."""
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    server: Optional[str] = None  # Serveur source (Phase 5)


@dataclass
class MCPResult:
    """Resultat d'un appel MCP."""
    success: bool
    content: str
    error: Optional[str] = None


class MCPClient:
    """Client pour communiquer avec les serveurs MCP via stdio."""

    def __init__(
        self,
        server_path: str = "/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/dist/index.js",
        timeout: int = 120  # 2 minutes pour les commandes lentes (backup_status)
    ):
        self.server_path = Path(server_path)
        self.timeout = timeout
        self._tools_cache: Optional[list[MCPTool]] = None

    def _call_mcp(self, method: str, params: dict) -> dict:
        """Appelle le serveur MCP via stdio."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }

        try:
            # Le MCP server attend un newline apres le JSON
            result = subprocess.run(
                ["node", str(self.server_path)],
                input=json.dumps(request) + "\n",
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            # Le MCP server peut envoyer des logs dans stderr, on les ignore
            stdout = result.stdout.strip()

            if not stdout:
                return {"error": result.stderr or "MCP server returned empty response"}

            # Chercher la ligne JSON (ignorer les lignes de log)
            for line in stdout.split('\n'):
                line = line.strip()
                if line.startswith('{') and 'jsonrpc' in line:
                    response = json.loads(line)
                    return response

            # Si pas de ligne JSON valide, essayer de parser tout le stdout
            response = json.loads(stdout)
            return response

        except subprocess.TimeoutExpired:
            return {"error": f"Timeout apres {self.timeout}s"}
        except json.JSONDecodeError as e:
            return {"error": f"Reponse MCP invalide: {e}"}
        except Exception as e:
            return {"error": f"Erreur MCP: {e}"}

    def list_tools(self) -> list[MCPTool]:
        """Liste les outils disponibles."""
        if self._tools_cache:
            return self._tools_cache

        response = self._call_mcp("tools/list", {})

        if "error" in response:
            return []

        tools = []
        for tool_data in response.get("result", {}).get("tools", []):
            tools.append(MCPTool(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                parameters=tool_data.get("inputSchema", {})
            ))

        self._tools_cache = tools
        return tools

    def get_tools_for_llm(self) -> list[dict]:
        """Retourne les tools au format attendu par le LLM."""
        tools = self.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in tools
        ]

    def call_tool(self, name: str, arguments: dict) -> MCPResult:
        """Execute un outil MCP."""
        response = self._call_mcp("tools/call", {
            "name": name,
            "arguments": arguments
        })

        if "error" in response:
            return MCPResult(
                success=False,
                content="",
                error=response["error"]
            )

        result = response.get("result", {})

        if result.get("isError"):
            error_content = ""
            for item in result.get("content", []):
                if item.get("type") == "text":
                    error_content += item.get("text", "")
            return MCPResult(
                success=False,
                content="",
                error=error_content or "Erreur inconnue"
            )

        # Extraire le contenu textuel
        content_parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                content_parts.append(item.get("text", ""))

        return MCPResult(
            success=True,
            content="\n".join(content_parts)
        )

    def get_tool_by_name(self, name: str) -> Optional[MCPTool]:
        """Recupere un outil par son nom."""
        for tool in self.list_tools():
            if tool.name == name:
                return tool
        return None


class MCPManager:
    """Gestionnaire multi-serveurs MCP (Phase 5).

    Gere plusieurs serveurs MCP avec prefixage automatique des outils.
    Exemple: tv.power_on -> pylips-mcp, hue.set_brightness -> hue-mcp

    Phase 5.4: Support des differents types de serveurs MCP:
    - Node.js (fedora-agents): MCPClient one-shot
    - Python script (pylips-mcp): MCPScriptClient avec session
    - Python module (hue-mcp): MCPModuleClient avec session
    """

    def __init__(self, config: dict, verbose: bool = True):
        """Initialise le manager avec la configuration.

        Args:
            config: Configuration des serveurs depuis config.yaml
            verbose: Afficher les details de connexion (defaut: True)
        """
        self.clients: dict = {}  # MCPClient | MCPSessionClient
        self.server_configs: dict[str, dict] = {}
        self._tools_cache: Optional[list[dict]] = None
        self._verbose = verbose

        servers_config = config.get("mcp", {}).get("servers", {})

        for name, srv_cfg in servers_config.items():
            if not srv_cfg.get("enabled", True):
                continue

            self.server_configs[name] = srv_cfg

            # Creer le client MCP selon le type de serveur
            command = srv_cfg.get("command", "")
            args = srv_cfg.get("args", [])
            timeout = srv_cfg.get("timeout", 60)
            env = srv_cfg.get("env", {})

            if not command:
                continue

            try:
                # Executable direct (ex: screen-manager-mcp) - session mode
                if command.startswith("/") or command.startswith("~"):
                    full_cmd = [command] + list(args)
                    self.clients[name] = MCPSessionClient(
                        command=full_cmd,
                        env=env,
                        timeout=timeout,
                        name=name
                    )
                    if self._verbose:
                        print(f"  [{name}] MCPSessionClient (exec) -> {command}", file=sys.stderr)

                # Node.js server (fedora-agents) - one-shot mode
                elif command == "node":
                    server_path = args[0] if args else ""
                    self.clients[name] = MCPClient(
                        server_path=server_path,
                        timeout=timeout
                    )
                    if self._verbose:
                        print(f"  [{name}] MCPClient (node) -> {server_path}", file=sys.stderr)

                # Python module avec -m (hue-mcp) - session mode
                elif command in ("python", "python3") and args and args[0] == "-m":
                    module = args[1] if len(args) > 1 else ""
                    self.clients[name] = MCPModuleClient(
                        module=module,
                        env=env,
                        timeout=timeout
                    )
                    if self._verbose:
                        print(f"  [{name}] MCPModuleClient -> {module}", file=sys.stderr)

                # Python script (pylips-mcp) - session mode
                elif command in ("python", "python3"):
                    script_path = args[0] if args else ""
                    self.clients[name] = MCPScriptClient(
                        script_path=script_path,
                        env=env,
                        timeout=timeout
                    )
                    if self._verbose:
                        print(f"  [{name}] MCPScriptClient -> {script_path}", file=sys.stderr)

                else:
                    print(f"  [{name}] Type de serveur non supporte: {command}", file=sys.stderr)

            except Exception as e:
                print(f"  [{name}] Erreur creation client: {e}", file=sys.stderr)

    def get_all_tools(self) -> list[dict]:
        """Retourne tous les outils de tous les serveurs avec prefixes.

        Returns:
            Liste des outils avec noms prefixes (ex: "tv.power_on")
        """
        if self._tools_cache:
            return self._tools_cache

        tools = []
        for server_name, client in self.clients.items():
            try:
                server_tools = client.list_tools()
                for tool in server_tools:
                    tools.append({
                        "name": f"{server_name}.{tool.name}",
                        "description": tool.description,
                        "parameters": tool.parameters,
                        "_server": server_name
                    })
            except Exception as e:
                print(f"Warning: Could not list tools from {server_name}: {e}")

        self._tools_cache = tools
        return tools

    def call_tool(self, full_name: str, arguments: dict) -> MCPResult:
        """Execute un outil sur le bon serveur.

        Args:
            full_name: Nom complet avec prefixe (ex: "tv.power_on")
            arguments: Arguments de l'outil

        Returns:
            Resultat de l'execution
        """
        # NORMALISATION : vm.xxx → vm_xxx, backup.xxx → backup_xxx
        # Le LLM peut confondre avec le pattern tv.xxx / hue.xxx
        if full_name.startswith("vm."):
            full_name = "vm_" + full_name[3:]
        elif full_name.startswith("backup."):
            full_name = "backup_" + full_name[7:]

        # Parser le nom pour extraire serveur et outil
        if "." in full_name:
            server_name, tool_name = full_name.split(".", 1)
        else:
            # Pas de prefixe: chercher dans tous les serveurs (compatibilite)
            return self._call_without_prefix(full_name, arguments)

        if server_name not in self.clients:
            return MCPResult(
                success=False,
                content="",
                error=f"Serveur MCP '{server_name}' non trouve"
            )

        result = self.clients[server_name].call_tool(tool_name, arguments)

        # Retry unique si erreur de session/connexion (le process redémarre automatiquement)
        if not result.success and result.error and \
                any(kw in result.error.lower() for kw in
                    ("session", "process", "broken pipe", "eof", "termine", "connexion")):
            time.sleep(0.5)
            result = self.clients[server_name].call_tool(tool_name, arguments)

        return result

    def _call_without_prefix(self, tool_name: str, arguments: dict) -> MCPResult:
        """Recherche et execute un outil sans prefixe (compatibilite).

        Cherche l'outil dans tous les serveurs et execute sur le premier trouve.
        """
        for server_name, client in self.clients.items():
            try:
                tool = client.get_tool_by_name(tool_name)
                if tool:
                    return client.call_tool(tool_name, arguments)
            except:
                continue

        return MCPResult(
            success=False,
            content="",
            error=f"Outil '{tool_name}' non trouve dans aucun serveur MCP"
        )

    def get_server_names(self) -> list[str]:
        """Retourne la liste des serveurs disponibles."""
        return list(self.clients.keys())

    def is_server_available(self, server_name: str) -> bool:
        """Verifie si un serveur est disponible."""
        return server_name in self.clients

    def clear_cache(self):
        """Efface le cache des outils."""
        self._tools_cache = None
        for client in self.clients.values():
            client._tools_cache = None

    def close(self):
        """Ferme toutes les sessions MCP."""
        for name, client in self.clients.items():
            try:
                if hasattr(client, 'close'):
                    client.close()
            except Exception as e:
                print(f"Warning: Could not close {name}: {e}", file=sys.stderr)

    def __del__(self):
        """Cleanup a la destruction."""
        self.close()


class MCPSessionClient:
    """Client MCP avec session persistante pour serveurs async (Python).

    Les serveurs MCP Python (pylips-mcp, hue-mcp) utilisent le protocole
    MCP complet avec handshake et session persistante.

    Phase 5.4: Support des serveurs MCP async.
    """

    def __init__(
        self,
        command: list[str],
        env: dict = None,
        timeout: int = 30,
        name: str = "mcp"
    ):
        """Initialise le client session.

        Args:
            command: Commande a executer (ex: ["python", "server.py"])
            env: Variables d'environnement supplementaires
            timeout: Timeout en secondes pour chaque requete
            name: Nom du serveur (pour logs)
        """
        self.command = command
        self.extra_env = env or {}
        self.timeout = timeout
        self.name = name

        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._tools_cache: Optional[list[MCPTool]] = None
        self._initialized = False
        self._lock = threading.Lock()

    def _start_process(self):
        """Demarre le processus MCP si pas deja actif."""
        if self._process and self._process.poll() is None:
            return  # Deja en cours

        env = os.environ.copy()
        env.update(self.extra_env)

        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1  # Line buffered
        )
        self._initialized = False

    def _send_request(self, method: str, params: dict) -> dict:
        """Envoie une requete JSON-RPC et attend la reponse."""
        with self._lock:
            try:
                self._start_process()

                # Initialize handshake si premiere requete
                if not self._initialized:
                    init_result = self._do_initialize()
                    if "error" in init_result:
                        return init_result

                self._request_id += 1
                request = {
                    "jsonrpc": "2.0",
                    "id": self._request_id,
                    "method": method,
                    "params": params
                }

                # Envoyer la requete
                self._process.stdin.write(json.dumps(request) + "\n")
                self._process.stdin.flush()

                # Lire la reponse (avec timeout)
                return self._read_response(self._request_id)

            except Exception as e:
                self._stop_process()
                return {"error": f"Erreur session MCP: {e}"}

    def _do_initialize(self) -> dict:
        """Effectue le handshake MCP initialize."""
        self._request_id += 1
        init_request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "lyra",
                    "version": "1.0"
                }
            }
        }

        self._process.stdin.write(json.dumps(init_request) + "\n")
        self._process.stdin.flush()

        # Attendre la reponse initialize
        response = self._read_response(self._request_id)
        if "error" in response:
            return response

        # Envoyer notifications/initialized (pas de reponse attendue)
        notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self._process.stdin.write(json.dumps(notif) + "\n")
        self._process.stdin.flush()

        self._initialized = True
        return {"status": "initialized"}

    def _read_response(self, expected_id: int) -> dict:
        """Lit une reponse JSON-RPC avec timeout global."""
        import select

        deadline = time.monotonic() + self.timeout

        # Lire les lignes jusqu'a trouver la reponse, avec deadline globale
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"error": f"Timeout apres {self.timeout}s"}

            # Utiliser select pour un timeout par lecture (Unix only)
            if hasattr(select, 'select'):
                ready, _, _ = select.select([self._process.stdout], [], [], min(remaining, 2.0))
                if not ready:
                    continue  # Verifier la deadline et recommencer

            line = self._process.stdout.readline()
            if not line:
                # Process termine
                stderr = self._process.stderr.read() if self._process.stderr else ""
                return {"error": f"Process termine: {stderr[:200]}"}

            line = line.strip()
            if not line:
                continue

            # Ignorer les logs (lignes ne commencant pas par {)
            if not line.startswith('{'):
                continue

            try:
                response = json.loads(line)
                if response.get("id") == expected_id:
                    return response
                # Notification ou reponse hors-sequence : continuer jusqu'a la deadline
            except json.JSONDecodeError:
                continue

        return {"error": "Pas de reponse valide"}

    def _stop_process(self):
        """Arrete le processus MCP."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except:
                self._process.kill()
            self._process = None
            self._initialized = False

    def list_tools(self) -> list[MCPTool]:
        """Liste les outils disponibles."""
        if self._tools_cache:
            return self._tools_cache

        response = self._send_request("tools/list", {})

        if "error" in response:
            print(f"Warning [{self.name}]: {response['error']}", file=sys.stderr)
            return []

        tools = []
        for tool_data in response.get("result", {}).get("tools", []):
            tools.append(MCPTool(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                parameters=tool_data.get("inputSchema", {}),
                server=self.name
            ))

        self._tools_cache = tools
        return tools

    def call_tool(self, name: str, arguments: dict) -> MCPResult:
        """Execute un outil MCP."""
        response = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })

        if "error" in response:
            return MCPResult(
                success=False,
                content="",
                error=response["error"]
            )

        result = response.get("result", {})

        if result.get("isError"):
            error_content = ""
            for item in result.get("content", []):
                if item.get("type") == "text":
                    error_content += item.get("text", "")
            return MCPResult(
                success=False,
                content="",
                error=error_content or "Erreur inconnue"
            )

        # Extraire le contenu textuel
        content_parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                content_parts.append(item.get("text", ""))

        return MCPResult(
            success=True,
            content="\n".join(content_parts)
        )

    def get_tool_by_name(self, name: str) -> Optional[MCPTool]:
        """Recupere un outil par son nom."""
        for tool in self.list_tools():
            if tool.name == name:
                return tool
        return None

    def close(self):
        """Ferme la session MCP."""
        self._stop_process()

    def __del__(self):
        """Cleanup a la destruction."""
        self.close()


class MCPModuleClient(MCPSessionClient):
    """Client MCP pour modules Python (ex: hue_mcp).

    Utilise 'python -m module_name' avec session persistante.
    """

    def __init__(self, module: str, env: dict = None, timeout: int = 30):
        """Initialise le client module.

        Args:
            module: Nom du module Python (ex: "hue_mcp")
            env: Variables d'environnement supplementaires
            timeout: Timeout en secondes
        """
        super().__init__(
            command=["python3", "-m", module],
            env=env,
            timeout=timeout,
            name=module
        )
        self.module = module


class MCPScriptClient(MCPSessionClient):
    """Client MCP pour scripts Python (ex: pylips-mcp/server.py).

    Utilise 'python script.py' avec session persistante.
    """

    def __init__(self, script_path: str, env: dict = None, timeout: int = 30):
        """Initialise le client script.

        Args:
            script_path: Chemin vers le script Python
            env: Variables d'environnement supplementaires
            timeout: Timeout en secondes
        """
        super().__init__(
            command=["python3", script_path],
            env=env,
            timeout=timeout,
            name=Path(script_path).stem
        )
        self.script_path = script_path


# Tools pre-definis pour eviter l'appel tools/list si le serveur ne le supporte pas
FEDORA_AGENTS_TOOLS = [
    MCPTool(
        name="vm_status",
        description="Affiche le status et les informations d'une VM (IP, SSH, ressources). Sans vm_name, liste toutes les VMs.",
        parameters={
            "type": "object",
            "properties": {
                "vm_name": {"type": "string", "description": "Nom de la VM (optionnel)"},
                "detailed": {"type": "string", "description": "Afficher les details"},
                "json": {"type": "string", "description": "Format JSON"}
            }
        }
    ),
    MCPTool(
        name="vm_start",
        description="Demarre une VM KVM et attend optionnellement que SSH soit accessible",
        parameters={
            "type": "object",
            "properties": {
                "vm_name": {"type": "string", "description": "Nom de la VM"},
                "wait_ssh": {"type": "boolean", "description": "Attendre SSH"},
                "wait_ip": {"type": "boolean", "description": "Attendre IP"},
                "timeout": {"type": "number", "description": "Timeout en secondes"}
            },
            "required": ["vm_name"]
        }
    ),
    MCPTool(
        name="vm_stop",
        description="Arrete une VM KVM proprement (ou force l'arret avec force=true)",
        parameters={
            "type": "object",
            "properties": {
                "vm_name": {"type": "string", "description": "Nom de la VM"},
                "force": {"type": "boolean", "description": "Forcer l'arret"},
                "wait": {"type": "boolean", "description": "Attendre l'arret"}
            },
            "required": ["vm_name"]
        }
    ),
    MCPTool(
        name="vm_snapshot",
        description="Gere les snapshots d'une VM (create, list, restore, delete)",
        parameters={
            "type": "object",
            "properties": {
                "vm_name": {"type": "string", "description": "Nom de la VM"},
                "action": {"type": "string", "description": "Action: create, list, restore, delete"},
                "snapshot_name": {"type": "string", "description": "Nom du snapshot"}
            }
        }
    ),
    MCPTool(
        name="vm_exec",
        description="Execute une commande dans une VM via SSH",
        parameters={
            "type": "object",
            "properties": {
                "vm_name": {"type": "string", "description": "Nom de la VM"},
                "command": {"type": "string", "description": "Commande a executer"},
                "user": {"type": "string", "description": "Utilisateur SSH"},
                "sudo": {"type": "boolean", "description": "Executer avec sudo"}
            },
            "required": ["vm_name", "command"]
        }
    ),
    MCPTool(
        name="backup_status",
        description="Affiche le dashboard global des backups (status, espace, alertes)",
        parameters={
            "type": "object",
            "properties": {
                "compact": {"type": "boolean", "description": "Mode compact"}
            }
        }
    ),
    MCPTool(
        name="backup_list",
        description="Liste tous les backups disponibles (par type ou tous)",
        parameters={
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Type: timeshift, borg, vm-snapshot, manual"},
                "all": {"type": "boolean", "description": "Lister tous les types"},
                "detailed": {"type": "boolean", "description": "Afficher les details"}
            }
        }
    ),
    MCPTool(
        name="backup_create",
        description="Cree un backup (timeshift, borg, vm-snapshot, ou manual)",
        parameters={
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Type de backup"},
                "comment": {"type": "string", "description": "Commentaire"},
                "verify": {"type": "boolean", "description": "Verifier apres creation"}
            }
        }
    ),
    MCPTool(
        name="backup_verify",
        description="Verifie l'integrite des backups",
        parameters={
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Type: timeshift, borg, vm, all"},
                "backup_id": {"type": "string", "description": "ID du backup"},
                "deep": {"type": "boolean", "description": "Verification approfondie"}
            }
        }
    ),
    MCPTool(
        name="help",
        description="Liste tous les outils disponibles avec leurs descriptions",
        parameters={"type": "object", "properties": {}}
    ),
]


# Outils TV Philips pre-definis (Phase 5.1)
TV_TOOLS = [
    MCPTool(
        name="power_on",
        description="Allume la TV Philips",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="power_off",
        description="Eteint la TV Philips (standby)",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="volume_up",
        description="Augmente le volume de la TV",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="volume_down",
        description="Baisse le volume de la TV",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="volume_set",
        description="Regle le volume a un niveau specifique (0-60)",
        parameters={
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Niveau de volume (0-60)"}
            },
            "required": ["level"]
        }
    ),
    MCPTool(
        name="mute",
        description="Coupe ou remet le son de la TV",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="ambilight_on",
        description="Active l'Ambilight",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="ambilight_off",
        description="Desactive l'Ambilight",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="ambilight_mode",
        description="Change le mode Ambilight (follow_video, follow_audio, lounge_light)",
        parameters={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "description": "Mode Ambilight"}
            },
            "required": ["mode"]
        }
    ),
    MCPTool(
        name="list_apps",
        description="Liste les applications disponibles sur la TV",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="launch_app",
        description="Lance une application (netflix, youtube, plex, disney, prime)",
        parameters={
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Nom de l'app"}
            },
            "required": ["app"]
        }
    ),
    MCPTool(
        name="youtube_video",
        description="Lance YouTube sur une video avec compte Premium (ADB, sans pubs)",
        parameters={
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "URL youtube ou ID video (11 car)"}
            },
            "required": ["video"]
        }
    ),
    MCPTool(
        name="get_state",
        description="Retourne l'etat de la TV",
        parameters={"type": "object", "properties": {}}
    ),
]

# Outils Hue pre-definis (Phase 5.2) - API reelle hue-mcp
HUE_TOOLS = [
    MCPTool(
        name="turn_on_light",
        description="Allume une lumiere Hue (light_id: 1=Hue, 2=Hue2, 3=HueBack, 4=HuePlayFront, 5=gradient)",
        parameters={
            "type": "object",
            "properties": {
                "light_id": {"type": "integer", "description": "ID de la lumiere (1-5)"}
            },
            "required": ["light_id"]
        }
    ),
    MCPTool(
        name="turn_off_light",
        description="Eteint une lumiere Hue",
        parameters={
            "type": "object",
            "properties": {
                "light_id": {"type": "integer", "description": "ID de la lumiere (1-5)"}
            },
            "required": ["light_id"]
        }
    ),
    MCPTool(
        name="set_brightness",
        description="Regle la luminosite d'une lumiere (0-254)",
        parameters={
            "type": "object",
            "properties": {
                "light_id": {"type": "integer", "description": "ID de la lumiere"},
                "brightness": {"type": "integer", "description": "Luminosite (0-254)"}
            },
            "required": ["light_id", "brightness"]
        }
    ),
    MCPTool(
        name="set_color_rgb",
        description="Change la couleur RGB d'une lumiere",
        parameters={
            "type": "object",
            "properties": {
                "light_id": {"type": "integer", "description": "ID de la lumiere"},
                "red": {"type": "integer", "description": "Rouge (0-255)"},
                "green": {"type": "integer", "description": "Vert (0-255)"},
                "blue": {"type": "integer", "description": "Bleu (0-255)"}
            },
            "required": ["light_id", "red", "green", "blue"]
        }
    ),
    MCPTool(
        name="set_color_preset",
        description="Applique un preset de couleur (warm, cool, daylight, relax, energize, red, green, blue)",
        parameters={
            "type": "object",
            "properties": {
                "light_id": {"type": "integer", "description": "ID de la lumiere"},
                "preset": {"type": "string", "description": "Preset: warm, cool, daylight, relax, energize, red, green, blue"}
            },
            "required": ["light_id", "preset"]
        }
    ),
    MCPTool(
        name="turn_on_group",
        description="Allume toutes les lumieres d'un groupe (81=Chambre, 83=TV, 84=Coin tele)",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {"type": "integer", "description": "ID du groupe (81=Chambre)"}
            },
            "required": ["group_id"]
        }
    ),
    MCPTool(
        name="turn_off_group",
        description="Eteint toutes les lumieres d'un groupe (81=Chambre, 83=TV, 84=Coin tele)",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {"type": "integer", "description": "ID du groupe (81=Chambre)"}
            },
            "required": ["group_id"]
        }
    ),
    MCPTool(
        name="set_group_brightness",
        description="Regle la luminosite de TOUTES les lumieres d'un groupe (81=toutes)",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {"type": "integer", "description": "ID du groupe (81=Chambre/toutes)"},
                "brightness": {"type": "integer", "description": "Luminosite (0-254)"}
            },
            "required": ["group_id", "brightness"]
        }
    ),
    MCPTool(
        name="set_group_color_rgb",
        description="Change la couleur RGB de toutes les lumieres d'un groupe",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {"type": "integer", "description": "ID du groupe (81=Chambre)"},
                "red": {"type": "integer", "description": "Rouge (0-255)"},
                "green": {"type": "integer", "description": "Vert (0-255)"},
                "blue": {"type": "integer", "description": "Bleu (0-255)"}
            },
            "required": ["group_id", "red", "green", "blue"]
        }
    ),
    MCPTool(
        name="set_group_color_preset",
        description="Applique un preset de couleur a un groupe (warm/cool/daylight/relax/energize/red/green/blue)",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {"type": "integer", "description": "ID du groupe (81=Chambre)"},
                "preset": {"type": "string", "description": "Preset: warm, cool, daylight, relax, energize, red, green, blue"}
            },
            "required": ["group_id", "preset"]
        }
    ),
    MCPTool(
        name="get_all_lights",
        description="Liste toutes les lumieres Hue avec leur etat",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="get_all_groups",
        description="Liste tous les groupes de lumieres",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="get_all_scenes",
        description="Liste toutes les scenes disponibles",
        parameters={"type": "object", "properties": {}}
    ),
    MCPTool(
        name="set_scene",
        description="Active une scene par son ID exact",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {"type": "integer", "description": "ID du groupe"},
                "scene_id": {"type": "string", "description": "ID exact de la scene"}
            },
            "required": ["group_id", "scene_id"]
        }
    ),
    MCPTool(
        name="activate_scene_by_name",
        description="Active une scene par son NOM (recherche partielle, prefere cet outil!)",
        parameters={
            "type": "object",
            "properties": {
                "scene_name": {"type": "string", "description": "Nom de la scene (ex: Batman, Detente)"},
                "group_id": {"type": "integer", "description": "ID du groupe (81=toutes)"}
            },
            "required": ["scene_name", "group_id"]
        }
    ),
]


def get_default_tools() -> list[dict]:
    """Retourne les tools par defaut pour le LLM (fedora-agents)."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        }
        for tool in FEDORA_AGENTS_TOOLS
    ]


def get_all_default_tools() -> list[dict]:
    """Retourne TOUS les tools par defaut pour le LLM (avec prefixes)."""
    tools = []

    # Fedora tools (sans prefixe pour compatibilite)
    for tool in FEDORA_AGENTS_TOOLS:
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        })

    # TV tools (avec prefixe tv.)
    for tool in TV_TOOLS:
        tools.append({
            "name": f"tv.{tool.name}",
            "description": f"[TV] {tool.description}",
            "parameters": tool.parameters
        })

    # Hue tools (avec prefixe hue.)
    for tool in HUE_TOOLS:
        tools.append({
            "name": f"hue.{tool.name}",
            "description": f"[Hue] {tool.description}",
            "parameters": tool.parameters
        })

    return tools
