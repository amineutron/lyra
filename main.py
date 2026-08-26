#!/usr/bin/env python3
"""
Lyra V1 - Assistant Vocal DevOps Local

Pipeline: User Input -> LLM -> Tool Confirmation -> MCP Execution -> Response

Usage:
    python main.py              # Mode texte (defaut)
    python main.py --vocal      # Mode vocal (STT/TTS)
    python main.py --model qwen2.5-coder:14b
"""

import sys
import os
import re

# Configurer LD_LIBRARY_PATH pour les libs CUDA (faster-whisper)
# Doit etre fait AVANT l'import de faster_whisper
def _setup_cuda_libs():
    """Configure le chemin des bibliotheques CUDA pour faster-whisper."""
    venv_path = os.path.dirname(os.path.dirname(sys.executable))
    cuda_paths = [
        os.path.join(venv_path, "lib/python3.12/site-packages/nvidia/cublas/lib"),
        os.path.join(venv_path, "lib/python3.12/site-packages/nvidia/cudnn/lib"),
        os.path.join(venv_path, "lib64/python3.12/site-packages/nvidia/cublas/lib"),
        os.path.join(venv_path, "lib64/python3.12/site-packages/nvidia/cudnn/lib"),
    ]
    existing_paths = [p for p in cuda_paths if os.path.exists(p)]
    if existing_paths:
        current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        new_paths = ":".join(existing_paths)
        os.environ["LD_LIBRARY_PATH"] = f"{new_paths}:{current_ld_path}" if current_ld_path else new_paths

_setup_cuda_libs()
import time
import argparse
import subprocess
from pathlib import Path
from typing import Optional

# Ajouter le dossier modules au path
sys.path.insert(0, str(Path(__file__).parent))

from modules.llm import OllamaClient, LLMResponse
from lyra.core.paths import backup_manager_dir, kvm_dir
from modules.mcp import MCPClient, MCPManager, get_default_tools, get_all_default_tools
from modules.n8n import N8nClient, N8nConfig, should_use_async, get_async_workflow, get_async_executor, send_discord_notification
from modules import ui
from modules.ui import setup_readline


_VM_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')
_BACKUP_TYPE_RE = re.compile(r'^(timeshift|borg|rsync)$')


def _validate_vm_name(name: str) -> bool:
    """Valide un nom de VM pour eviter les injections shell."""
    return bool(name and _VM_NAME_RE.match(name))


def _validate_backup_type(btype: str) -> bool:
    """Valide un type de backup pour eviter les injections shell."""
    return bool(btype and _BACKUP_TYPE_RE.match(btype))


# =============================================================================
# Phase 5: Mode Performance - Outils sans confirmation
# =============================================================================

# Outils executables sans confirmation en mode performance
PERFORMANCE_TOOLS = {
    # TV Philips
    "tv.power_on", "tv.power_off",
    "tv.volume_up", "tv.volume_down", "tv.volume_set", "tv.mute",
    "tv.ambilight_on", "tv.ambilight_off", "tv.ambilight_mode",
    "tv.list_apps", "tv.launch_app", "tv.youtube_video", "tv.send_key",
    # Lumieres Hue - individuelles
    "hue.turn_on_light", "hue.turn_off_light",
    "hue.set_brightness", "hue.set_color_rgb", "hue.set_color_temperature",
    "hue.set_color_preset",
    # Lumieres Hue - groupes
    "hue.turn_on_group", "hue.turn_off_group",
    "hue.set_group_brightness", "hue.set_group_color_rgb", "hue.set_group_color_preset",
    "hue.set_scene", "hue.activate_scene_by_name",
}

# Outils TOUJOURS avec confirmation (meme en mode performance)
ALWAYS_CONFIRM_TOOLS = {
    "vm_destroy", "fedora.vm_destroy",
    "vm_stop", "fedora.vm_stop",
    "backup_restore", "fedora.backup_restore",
    "backup_clean", "fedora.backup_clean",
    "vm_clone_system", "fedora.vm_clone_system",
}

# Outils en lecture seule (pas de confirmation en mode performance)
QUICK_READ_TOOLS = {
    "tv.get_state",
    "hue.get_all_lights",
}


def load_system_prompt() -> str:
    """Charge le system prompt depuis le fichier externe."""
    prompt_path = Path(__file__).parent / "prompts" / "system_prompt.txt"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        ui.print_warning(f"System prompt non trouve: {prompt_path}")
        return "Tu es Lyra, un assistant DevOps. Reponds en francais."


# Charger le system prompt au demarrage
SYSTEM_PROMPT = load_system_prompt()

# Outils necessitant un Read-First (verification d'etat avant action)
READ_FIRST_TOOLS = {
    "vm_start", "vm.start",
    "vm_stop", "vm.stop",
    "vm_destroy", "vm.destroy",
    "vm_snapshot", "vm.snapshot",
    "vm_clone", "vm.clone",
}

# Outils de lecture (pas besoin de Read-First)
READ_ONLY_TOOLS = {
    "vm_status",
    "backup_status",
    "backup_list",
    "backup_verify",
    "help",
}


class Lyra:
    """Assistant DevOps avec Human-in-the-Loop."""

    def __init__(self, model: str = "qwen2.5-coder:14b", vocal: bool = False, performance_mode: bool = False):
        self.llm = OllamaClient(model=model)
        self.mcp = MCPClient()  # Client legacy (fedora-agents)
        self.mcp_manager: Optional[MCPManager] = None  # Multi-MCP (Phase 5)
        self.tools = get_all_default_tools()  # Tous les outils (VM + TV + Hue)
        self._last_ctrl_c = 0  # Timestamp du dernier Ctrl+C
        self.vocal = vocal
        self.voice: Optional["VoiceInterface"] = None
        self.n8n: Optional[N8nClient] = None
        self.discord_webhook_url: Optional[str] = None

        # Configuration et modes (Phase 5)
        self.config: dict = {}
        self.active_mode: str = "default"

        # Charger la config
        self._load_config()

        # Override mode si argument --performance
        if performance_mode:
            self.active_mode = "performance"

        if vocal:
            self._init_voice()

    def _load_config(self):
        """Charge la configuration depuis config.yaml."""
        try:
            import yaml
            config_path = Path(__file__).parent / "config.yaml"
            with open(config_path) as f:
                self.config = yaml.safe_load(f)

            # Mode actif (Phase 5)
            self.active_mode = self.config.get("active_mode", "default")

            # Config n8n
            n8n_cfg = self.config.get("n8n", {})
            if n8n_cfg.get("enabled", False):
                self.n8n = N8nClient(N8nConfig(
                    base_url=n8n_cfg.get("base_url", "http://localhost:5678"),
                    enabled=True,
                    webhooks=n8n_cfg.get("webhooks", {})
                ))
                if self.n8n.is_available():
                    ui.print_success("n8n connecte (operations async disponibles)")
                else:
                    ui.print_warning("n8n configure mais non accessible")
                    self.n8n = None

            # Config Discord (pour notifications fallback)
            discord_cfg = self.config.get("discord", {})
            if discord_cfg.get("enabled", False):
                webhook_url = discord_cfg.get("webhook_url", "")
                # Resoudre les variables d'environnement
                if webhook_url.startswith("${") and webhook_url.endswith("}"):
                    env_var = webhook_url[2:-1]
                    self.discord_webhook_url = os.environ.get(env_var)
                else:
                    self.discord_webhook_url = webhook_url
                if self.discord_webhook_url:
                    ui.print_info("Discord notifications activees")

            # Initialiser MCPManager si serveurs configures (Phase 5)
            servers_cfg = self.config.get("mcp", {}).get("servers", {})
            enabled_servers = [k for k, v in servers_cfg.items() if v.get("enabled", True)]
            if enabled_servers:
                try:
                    self.mcp_manager = MCPManager(self.config)
                    ui.print_info(f"MCPManager: {len(enabled_servers)} serveurs ({', '.join(enabled_servers)})")
                except Exception as e:
                    ui.print_warning(f"MCPManager init error: {e}")

        except Exception as e:
            ui.print_warning(f"Erreur chargement config: {e}")

    def _init_voice(self):
        """Initialise l'interface vocale."""
        try:
            import yaml
            from modules.audio import VoiceInterface, AudioConfig

            # Charger la config depuis config.yaml
            config_path = Path(__file__).parent / "config.yaml"
            with open(config_path) as f:
                cfg = yaml.safe_load(f)

            audio_cfg = cfg.get("audio", {})
            stt_cfg = cfg.get("stt", {})
            tts_cfg = cfg.get("tts", {})

            config = AudioConfig(
                sample_rate=audio_cfg.get("sample_rate", 16000),
                channels=audio_cfg.get("channels", 1),
                silence_threshold=audio_cfg.get("silence_threshold", 0.01),
                silence_duration=audio_cfg.get("silence_duration", 1.0),
                input_device=audio_cfg.get("input_device"),
                output_device=audio_cfg.get("output_device")
            )

            ui.print_info("Chargement du modele STT (Whisper)...")
            self.voice = VoiceInterface(
                stt_model=stt_cfg.get("model", "base"),
                tts_model=f"models/{tts_cfg.get('model', 'fr_FR-upmc-medium')}.onnx",
                language=stt_cfg.get("language", "fr"),
                device=stt_cfg.get("device", "cuda"),
                audio_config=config
            )
            ui.print_success(f"Interface vocale prete (device: {config.input_device})")
        except Exception as e:
            ui.print_error(f"Erreur initialisation vocale: {e}")
            ui.print_warning("Basculement en mode texte")
            self.vocal = False
            self.voice = None

    def _should_skip_confirmation(self, tool_name: str) -> bool:
        """Determine si on peut skip la confirmation (mode performance).

        Args:
            tool_name: Nom de l'outil (avec ou sans prefixe)

        Returns:
            True si on peut executer sans confirmation
        """
        # Toujours confirmer les outils dangereux
        if tool_name in ALWAYS_CONFIRM_TOOLS:
            return False

        # Mode performance: skip pour les outils autorises
        if self.active_mode == "performance":
            if tool_name in PERFORMANCE_TOOLS or tool_name in QUICK_READ_TOOLS:
                return True

        # Mode default: toujours confirmer
        return False

    def _get_mode_config(self) -> dict:
        """Retourne la configuration du mode actif."""
        modes = self.config.get("modes", {})
        return modes.get(self.active_mode, modes.get("default", {}))

    def set_mode(self, mode: str) -> bool:
        """Change le mode actif.

        Args:
            mode: "default" ou "performance"

        Returns:
            True si le mode a change
        """
        if mode in ("default", "performance"):
            self.active_mode = mode
            return True
        return False

    def process_input(self, user_input: str) -> Optional[str]:
        """Traite une entree utilisateur.

        Returns:
            La reponse textuelle (pour le mode vocal) ou None
        """
        response_text = None

        # Commandes speciales
        if user_input.lower() in ("help", "?", "aide"):
            ui.print_help()
            return "Voici l'aide." if self.vocal else None

        if user_input.lower() in ("clear", "cls", "reset"):
            self.llm.clear_history()
            ui.print_success("Historique efface.")
            return "Historique efface." if self.vocal else None

        if user_input.lower() in ("clearscreen", "clr"):
            ui.clear_screen()
            return None

        # Commandes de mode (Phase 5)
        if user_input.lower() == "mode":
            ui.print_mode_status(self.active_mode, len(PERFORMANCE_TOOLS))
            return f"Mode actuel: {self.active_mode}" if self.vocal else None

        if user_input.lower() == "mode performance":
            self.set_mode("performance")
            ui.print_success("Mode performance active - execution instantanee")
            return "Mode performance active" if self.vocal else None

        if user_input.lower() in ("mode default", "mode normal"):
            self.set_mode("default")
            ui.print_success("Mode default active - confirmations actives")
            return "Mode normal active" if self.vocal else None

        if user_input.lower() in ("quit", "exit", "q", "bye", "stop", "arrete"):
            ui.print_info("Au revoir !")
            if self.vocal and self.voice:
                self.voice.speak("Au revoir !")
            sys.exit(0)

        # Envoyer au LLM
        ui.print_thinking()

        try:
            response = self.llm.chat(
                message=user_input,
                tools=self.tools,
                system_prompt=SYSTEM_PROMPT
            )
        except Exception as e:
            ui.clear_thinking()
            ui.print_error(f"Erreur LLM: {e}")
            return f"Erreur: {e}" if self.vocal else None

        ui.clear_thinking()

        # Si c'est un ou plusieurs tool calls
        if response.is_tool_call and response.tool_calls:
            if len(response.tool_calls) > 1:
                response_text = self._handle_multiple_tool_calls(response.tool_calls)
            else:
                response_text = self._handle_tool_call(response)
        else:
            # Reponse normale
            ui.print_assistant(response.content)
            response_text = response.content

        return response_text

    def _handle_tool_call(self, response: LLMResponse) -> Optional[str]:
        """Gere un appel d'outil avec confirmation.

        Returns:
            La reponse textuelle (resume LLM) ou None
        """
        tool_call = response.tool_call
        mode_config = self._get_mode_config()

        # Mode performance: execution rapide si autorise
        if self._should_skip_confirmation(tool_call.name):
            return self._execute_quick(tool_call.name, tool_call.arguments)

        # Read-First: pour les actions sur VM, verifier l'etat d'abord
        vm_state = None
        if mode_config.get("read_first", True) and tool_call.name in READ_FIRST_TOOLS:
            vm_name = tool_call.arguments.get("vm_name") or tool_call.arguments.get("source_vm") or tool_call.arguments.get("source_vm_name")
            if vm_name:
                vm_state = self._read_first_check(vm_name)

        # Verification intelligente: vm_clone necessite que la VM soit arretee
        if tool_call.name in ("vm_clone", "vm.clone") and vm_state and vm_state.get("running"):
            return self._handle_clone_running_vm(tool_call, vm_state)

        # Afficher l'action proposee (avec l'etat VM si disponible)
        ui.print_tool_call(tool_call.name, tool_call.arguments, vm_state=vm_state)

        # En mode vocal, annoncer l'action de maniere plus naturelle
        if self.vocal and self.voice and mode_config.get("tts_response", True):
            action_desc = self._describe_action(tool_call.name, tool_call.arguments, vm_state)
            self.voice.speak(action_desc)

        # Demander confirmation (vocale ou clavier selon le mode)
        confirmed = ui.confirm_action(
            tool_call.name,
            tool_call.arguments,
            vocal_mode=self.vocal,
            voice=self.voice
        )

        if not confirmed:
            ui.print_warning("Action annulee.")
            return "Action annulee." if self.vocal else None

        # Verifier si c'est une operation async (n8n)
        if self.n8n and should_use_async(tool_call.name, tool_call.arguments):
            # Normaliser les arguments avant l'execution async
            normalized_args = self._normalize_arguments(tool_call.name, tool_call.arguments)
            return self._handle_async_operation(tool_call.name, normalized_args)

        # Executer l'outil MCP (synchrone)
        ui.print_info(f"Execution de {tool_call.name}...")

        try:
            result = self._call_mcp_tool(tool_call.name, tool_call.arguments)
        except Exception as e:
            ui.print_error(f"Erreur MCP: {e}")
            return f"Erreur lors de l'execution: {e}" if self.vocal else None

        # Afficher le resultat
        if result.success:
            ui.print_tool_result(result.content, success=True)

            # Demander au LLM de resumer (si mode verbose)
            if mode_config.get("verbose", True):
                self.llm.add_tool_result(tool_call.name, result.content)

                try:
                    summary = self.llm.chat(
                        message="",  # Le message est deja dans l'historique
                        tools=None,  # Pas de tools pour le resume
                        system_prompt=None
                    )
                    ui.print_assistant(summary.content)
                    return summary.content
                except Exception:
                    pass

            return result.content if self.vocal else None
        else:
            error_msg = result.error or "Erreur inconnue"
            ui.print_tool_result(error_msg, success=False)
            return f"Erreur: {error_msg}" if self.vocal else None

    def _execute_quick(self, tool_name: str, arguments: dict) -> Optional[str]:
        """Execute un outil en mode rapide (performance mode).

        Args:
            tool_name: Nom de l'outil
            arguments: Arguments

        Returns:
            Resultat minimal ou None
        """
        try:
            result = self._call_mcp_tool(tool_name, arguments)

            if result.success:
                ui.print_quick_result(tool_name, success=True, use_beep=True)
                return "OK" if self.vocal else None
            else:
                ui.print_quick_result(tool_name, success=False, use_beep=True)
                return f"Erreur: {result.error}" if self.vocal else None

        except Exception as e:
            ui.print_error(f"Erreur: {e}")
            return f"Erreur: {e}" if self.vocal else None

    def _normalize_arguments(self, tool_name: str, arguments: dict) -> dict:
        """Normalise les arguments pour corriger les variations du LLM.

        Le LLM peut generer des noms de parametres legerement differents.
        Cette fonction les corrige pour correspondre a l'API MCP.

        Args:
            tool_name: Nom de l'outil (normalise, ex: vm_clone)
            arguments: Arguments originaux

        Returns:
            Arguments normalises
        """
        args = arguments.copy()

        # vm_clone: normaliser les variations de noms de parametres
        if tool_name in ("vm_clone", "vm.clone"):
            # source_vm_name -> source_vm
            if "source_vm_name" in args and "source_vm" not in args:
                args["source_vm"] = args.pop("source_vm_name")
            # target_vm_name / target_vm / clone_name / name -> new_vm_name
            if "new_vm_name" not in args:
                for alt in ("target_vm_name", "target_vm", "clone_name", "name", "new_name"):
                    if alt in args:
                        args["new_vm_name"] = args.pop(alt)
                        break

        # vm_copy: src -> source, dst -> dest
        if tool_name in ("vm_copy", "vm.copy"):
            if "src" in args and "source" not in args:
                args["source"] = args.pop("src")
            if "dst" in args and "dest" not in args:
                args["dest"] = args.pop("dst")

        return args

    def _call_mcp_tool(self, tool_name: str, arguments: dict):
        """Appelle un outil MCP via le client approprie.

        Utilise MCPManager si disponible (multi-serveurs),
        sinon fallback sur le client legacy.

        Args:
            tool_name: Nom de l'outil (avec ou sans prefixe)
            arguments: Arguments de l'outil

        Returns:
            MCPResult
        """
        # Normaliser les arguments (corriger variations LLM)
        arguments = self._normalize_arguments(tool_name, arguments)

        # Si l'outil a un prefixe et MCPManager est disponible
        if self.mcp_manager and "." in tool_name:
            return self.mcp_manager.call_tool(tool_name, arguments)

        # Sinon utiliser le client legacy
        # Retirer le prefixe "fedora." si present
        clean_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
        return self.mcp.call_tool(clean_name, arguments)

    def _read_first_check(self, vm_name: str) -> Optional[dict]:
        """Verifie l'etat d'une VM avant une action (Read-First).

        Returns:
            Dict avec l'etat de la VM ou None si erreur
        """
        try:
            ui.print_info(f"Verification de l'etat de {vm_name}...")
            result = self.mcp.call_tool("vm_status", {"vm_name": vm_name})
            if result.success:
                # Parser le resultat pour extraire l'etat
                content = result.content
                state = {
                    "vm_name": vm_name,
                    "raw": content,
                    "running": "running" in content.lower() or "en cours" in content.lower(),
                    "ip": self._extract_ip(content),
                }
                return state
        except Exception as e:
            ui.print_warning(f"Read-First: impossible de verifier {vm_name}: {e}")
        return None

    def _extract_ip(self, content: str) -> Optional[str]:
        """Extrait une adresse IP du contenu."""
        import re
        match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', content)
        return match.group(1) if match else None

    def _handle_clone_running_vm(self, tool_call, vm_state: dict) -> Optional[str]:
        """Gere le cas ou l'utilisateur veut cloner une VM en cours d'execution.

        Propose d'arreter la VM, de la cloner, puis de la redemarrer.

        Args:
            tool_call: ToolCall original (vm_clone)
            vm_state: Etat actuel de la VM

        Returns:
            Resume des actions ou None
        """
        source_vm = tool_call.arguments.get("source_vm") or tool_call.arguments.get("source_vm_name") or ""
        new_vm = tool_call.arguments.get("new_vm_name") or tool_call.arguments.get("target_vm_name") or ""

        # Afficher l'avertissement
        print()
        ui.print_warning(f"La VM '{source_vm}' est en cours d'execution!")
        print()
        print("  Pour cloner une VM, elle doit etre arretee.")
        print()
        print("  Je propose d'executer ces actions:")
        print(f"    1. Arreter {source_vm}")
        print(f"    2. Cloner {source_vm} -> {new_vm}")
        print(f"    3. Redemarrer {source_vm}")
        print()

        # Demander confirmation
        try:
            choice = input("  Executer ? [O/n/s] (O=oui, n=non, s=sans redemarrer) : ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            ui.print_warning("Action annulee.")
            return "Action annulee." if self.vocal else None

        if choice in ("n", "non"):
            ui.print_warning("Action annulee.")
            return "Action annulee." if self.vocal else None

        restart_after = choice not in ("s", "sans")

        # 1. Arreter la VM
        ui.print_info(f"Arret de {source_vm}...")
        stop_result = self.mcp.call_tool("vm_stop", {"vm_name": source_vm, "wait": True})
        if not stop_result.success:
            ui.print_error(f"Echec de l'arret: {stop_result.error}")
            return f"Erreur: {stop_result.error}" if self.vocal else None
        ui.print_success(f"{source_vm} arretee.")

        # 2. Cloner la VM (normaliser les arguments)
        clone_args = self._normalize_arguments("vm_clone", tool_call.arguments)
        ui.print_info(f"Clonage de {source_vm} vers {new_vm}...")

        # Verifier si c'est async
        if self.n8n and should_use_async("vm_clone", clone_args):
            result = self._handle_async_operation("vm_clone", clone_args)
            if restart_after:
                ui.print_info(f"Note: {source_vm} sera redemarre une fois le clone termine.")
            return result

        clone_result = self.mcp.call_tool("vm_clone", clone_args)
        if not clone_result.success:
            ui.print_error(f"Echec du clonage: {clone_result.error}")
            # Redemarrer quand meme la VM source en cas d'echec
            if restart_after:
                ui.print_info(f"Redemarrage de {source_vm}...")
                self.mcp.call_tool("vm_start", {"vm_name": source_vm})
            return f"Erreur: {clone_result.error}" if self.vocal else None
        ui.print_success(f"Clone {new_vm} cree.")

        # 3. Redemarrer la VM source (si demande)
        if restart_after:
            ui.print_info(f"Redemarrage de {source_vm}...")
            start_result = self.mcp.call_tool("vm_start", {"vm_name": source_vm, "wait_ssh": True})
            if start_result.success:
                ui.print_success(f"{source_vm} redemarre.")
            else:
                ui.print_warning(f"Echec du redemarrage: {start_result.error}")

        summary = f"VM {source_vm} clonee vers {new_vm}"
        if restart_after:
            summary += f", {source_vm} redemarre"
        ui.print_success(summary)
        return summary if self.vocal else None

    def _describe_action(self, tool_name: str, arguments: dict, vm_state: Optional[dict]) -> str:
        """Genere une description vocale de l'action proposee."""
        vm_name = arguments.get("vm_name") or arguments.get("source_vm") or arguments.get("source_vm_name") or ""
        source_vm = arguments.get("source_vm") or arguments.get("source_vm_name") or ""
        new_vm = arguments.get("new_vm_name") or arguments.get("target_vm_name") or arguments.get("target_vm") or arguments.get("clone_name") or ""

        descriptions = {
            "vm_start": f"Je vais demarrer la VM {vm_name}",
            "vm_stop": f"Je vais arreter la VM {vm_name}",
            "vm_destroy": f"Attention, je vais supprimer definitivement la VM {vm_name}",
            "vm_snapshot": f"Je vais gerer un snapshot de {vm_name}",
            "vm_exec": f"Je vais executer une commande sur {vm_name}",
            "vm_clone": f"Je vais cloner la VM {source_vm} vers {new_vm}",
            "backup_create": "Je vais creer une sauvegarde",
            "backup_restore": "Attention, je vais restaurer une sauvegarde, cela ecrasera les donnees actuelles",
            "backup_clean": "Je vais nettoyer les anciennes sauvegardes",
        }

        desc = descriptions.get(tool_name, f"Je vais executer {tool_name}")

        # Ajouter l'etat actuel si disponible
        if vm_state:
            status = "en cours d'execution" if vm_state["running"] else "arretee"
            if vm_state.get("ip"):
                desc += f". Elle est actuellement {status} avec l'IP {vm_state['ip']}"
            else:
                desc += f". Elle est actuellement {status}"

        desc += ". Confirmes-tu?"
        return desc

    def _handle_multiple_tool_calls(self, tool_calls: list) -> Optional[str]:
        """Gere plusieurs tool calls comme une todo list.

        Args:
            tool_calls: Liste de ToolCall a executer

        Returns:
            Resume des actions executees
        """
        from modules.llm import ToolCall

        # Afficher la todo list
        print()
        ui.print_info(f"Todo list: {len(tool_calls)} actions proposees")
        print("=" * 50)
        for i, tc in enumerate(tool_calls, 1):
            vm_name = tc.arguments.get("vm_name") or tc.arguments.get("source_vm") or tc.arguments.get("source_vm_name") or "?"
            print(f"  [{i}] {tc.name} -> {vm_name}")
        print("=" * 50)
        print()

        # Demander confirmation globale
        try:
            choice = input("Executer ? [T]out / [1] par 1 / [n]on : ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            ui.print_warning("Annule.")
            return "Actions annulees." if self.vocal else None

        if choice in ("n", "non", "no"):
            ui.print_warning("Actions annulees.")
            return "Actions annulees." if self.vocal else None

        execute_all = choice in ("t", "tout", "all", "o", "oui", "")
        results = []

        for i, tc in enumerate(tool_calls, 1):
            vm_name = tc.arguments.get("vm_name") or tc.arguments.get("source_vm") or tc.arguments.get("source_vm_name") or "?"
            print()
            ui.print_info(f"[{i}/{len(tool_calls)}] {tc.name} -> {vm_name}")

            if not execute_all:
                # Demander confirmation pour chaque action
                try:
                    confirm = input("  Executer ? [o/n] : ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print()
                    ui.print_warning("Arret de la todo list.")
                    break

                if confirm not in ("o", "oui", "y", "yes", ""):
                    ui.print_warning(f"  -> {tc.name} ignore")
                    results.append(f"{vm_name}: ignore")
                    continue

            # Executer l'action
            try:
                # Verifier si c'est une operation async
                if self.n8n and should_use_async(tc.name, tc.arguments):
                    result_msg = self._handle_async_operation(tc.name, tc.arguments)
                    results.append(f"{vm_name}: lance en arriere-plan")
                else:
                    # Utiliser _call_mcp_tool pour router vers le bon serveur (Phase 5.4)
                    result = self._call_mcp_tool(tc.name, tc.arguments)
                    if result.success:
                        ui.print_success(f"  -> OK")
                        results.append(f"{vm_name}: OK")
                    else:
                        ui.print_error(f"  -> Erreur: {result.error}")
                        results.append(f"{vm_name}: erreur")
            except Exception as e:
                ui.print_error(f"  -> Exception: {e}")
                results.append(f"{vm_name}: exception")

        # Resume
        print()
        summary = f"Todo list terminee: {len(results)}/{len(tool_calls)} actions"
        ui.print_success(summary)

        return summary if self.vocal else None

    def _handle_async_operation(self, tool_name: str, arguments: dict) -> Optional[str]:
        """Gere une operation longue via n8n (async) ou fallback subprocess.

        Args:
            tool_name: Nom de l'outil MCP
            arguments: Arguments de l'outil

        Returns:
            Message de confirmation
        """
        workflow = get_async_workflow(tool_name)
        if not workflow:
            ui.print_error(f"Pas de workflow pour {tool_name}")
            return None

        ui.print_info(f"Lancement async via n8n ({workflow})...")

        # Preparer les donnees pour le webhook
        data = dict(arguments)
        data["tool"] = tool_name
        data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

        result = self.n8n.trigger_workflow(workflow, data)

        if result.success:
            msg = f"Operation lancee en arriere-plan via n8n. Tu recevras une notification Discord."
            ui.print_success(msg)

            if self.vocal and self.voice:
                self.voice.speak("C'est lance. Tu recevras une notification Discord.")

            return msg
        else:
            # Fallback: execution en arriere-plan via subprocess
            # Afficher la raison de l'echec n8n pour debug
            ui.print_warning(f"n8n: {result.message}")
            if result.error and result.error != result.message:
                ui.print_warning(f"  Detail: {result.error}")
            ui.print_info("Lancement en arriere-plan (subprocess)...")

            # Capturer discord_webhook_url pour le callback
            discord_url = self.discord_webhook_url

            def on_complete(name, args, success, stdout, stderr):
                """Callback quand l'operation est terminee."""
                # Effacer la ligne courante et revenir au debut
                print("\r\033[K", end="", flush=True)
                if success:
                    ui.print_success(f"[ASYNC] Operation {name} terminee avec succes!")
                else:
                    ui.print_error(f"[ASYNC] Operation {name} echouee: {stderr[:100] if stderr else 'erreur inconnue'}")
                # Reafficher le prompt
                print("\nToi: ", end="", flush=True)

                # Envoyer notification Discord si configure
                if discord_url:
                    footer = "Lyra DevOps Assistant - Mode Fallback (n8n indisponible)"
                    verify_output = ""
                    verify_success = False

                    # Executer verification deep selon le type d'operation
                    if name in ("vm_clone", "vm.clone") and success:
                        # Pour vm_clone: attendre IP, verifier, eteindre
                        # Note: la VM est deja demarree par le script clone (--start)
                        new_vm = args.get("new_vm_name") or args.get("target_vm_name", "")
                        if not new_vm:
                            verify_output = f"Erreur: new_vm_name/target_vm_name non trouve dans args: {args}"
                            verify_success = False
                        elif not _validate_vm_name(new_vm):
                            verify_output = f"Nom de VM invalide: {new_vm!r}"
                            verify_success = False
                        else:
                            try:
                                # 1. Attendre que la VM ait une IP (max 120s)
                                # La VM est deja demarree par le script clone
                                ip_found = False
                                vm_ip = ""
                                for attempt in range(40):  # 40 tentatives x 3s = 120s max
                                    time.sleep(3)
                                    # Utiliser virsh domifaddr pour obtenir l'IP
                                    ip_check = subprocess.run(
                                        ["virsh", "domifaddr", new_vm],
                                        capture_output=True, text=True
                                    )
                                    # Chercher une IP dans la sortie (format: vnet0 52:54:00:xx:xx:xx ipv4 192.168.122.xxx/24)
                                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', ip_check.stdout)
                                    if ip_match:
                                        vm_ip = ip_match.group(1)
                                        ip_found = True
                                        break

                                if ip_found:
                                    # 2. Attendre que SSH soit disponible (host key accept)
                                    ssh_ready = False
                                    for ssh_attempt in range(20):  # 60s max
                                        ssh_check = subprocess.run(
                                            ["ssh", "-o", "StrictHostKeyChecking=accept-new",
                                             "-o", "ConnectTimeout=3",
                                             f"amineutron@{vm_ip}", "echo OK"],
                                            capture_output=True, text=True, timeout=10
                                        )
                                        if "OK" in ssh_check.stdout:
                                            ssh_ready = True
                                            break
                                        time.sleep(3)

                                    if ssh_ready:
                                        # 3. Lancer verify-vm-clone.sh --verbose
                                        verify_result = subprocess.run(
                                            [str(kvm_dir() / "verify-vm-clone.sh"),
                                             "--vm", new_vm, "--verbose"],
                                            capture_output=True, text=True, timeout=180
                                        )
                                        verify_output = verify_result.stdout
                                        if verify_result.stderr:
                                            verify_output += f"\n{verify_result.stderr}"
                                        # Nettoyer codes ANSI pour verifier le status
                                        clean_check = re.sub(r'\x1b\[[0-9;]*m', '', verify_output)
                                        # Le script retourne 1 pour warnings, on considere OK si output contient "PRET"
                                        verify_success = "PRET" in clean_check or "PRÊT" in clean_check or verify_result.returncode == 0
                                    else:
                                        verify_output = f"SSH non disponible apres 60s (IP: {vm_ip})"
                                        verify_success = False
                                else:
                                    # Verifier l'etat de la VM pour debug
                                    vm_state = subprocess.run(["virsh", "domstate", new_vm], capture_output=True, text=True)
                                    verify_output = f"Timeout: la VM {new_vm} n'a pas obtenu d'IP apres 120s\nEtat VM: {vm_state.stdout.strip()}"
                                    verify_success = False

                                # 3. Eteindre la VM
                                subprocess.run(["virsh", "shutdown", new_vm], capture_output=True, timeout=30)

                            except Exception as e:
                                verify_output = f"Erreur verification: {e}"
                                verify_success = False
                                # Tenter d'eteindre la VM en cas d'erreur
                                subprocess.run(["virsh", "destroy", new_vm], capture_output=True)

                    elif name in ("backup_create", "backup.create") and success:
                        # Lancer backup verify --deep
                        backup_type = args.get("type", "timeshift")
                        if not _validate_backup_type(backup_type):
                            verify_output = f"Type de backup invalide: {backup_type!r}"
                            verify_success = False
                        else:
                            try:
                                verify_result = subprocess.run(
                                    [str(backup_manager_dir() / "backup-verify.sh"),
                                     backup_type, "--deep"],
                                    capture_output=True, text=True, timeout=300
                                )
                                verify_output = verify_result.stdout
                                verify_success = verify_result.returncode == 0
                            except Exception as e:
                                verify_output = f"Erreur verification: {e}"
                                verify_success = False

                    elif name in ("backup_restore", "backup.restore") and success:
                        # Lancer backup verify --deep apres restauration
                        backup_type = args.get("type", "timeshift")
                        if not _validate_backup_type(backup_type):
                            verify_output = f"Type de backup invalide: {backup_type!r}"
                            verify_success = False
                        else:
                            try:
                                verify_result = subprocess.run(
                                    [str(backup_manager_dir() / "backup-verify.sh"),
                                     backup_type, "--deep"],
                                    capture_output=True, text=True, timeout=300
                                )
                                verify_output = verify_result.stdout
                                verify_success = verify_result.returncode == 0
                            except Exception as e:
                                verify_output = f"Erreur verification: {e}"
                                verify_success = False

                    # Couleur finale basee sur operation + verification
                    final_success = success and (verify_success if verify_output else True)
                    color = 3066993 if final_success else 15158332  # Vert ou Rouge

                    # Premier message: Verification Deep (si disponible)
                    if verify_output and len(verify_output.strip()) > 0:
                        # Nettoyer les codes ANSI et messages comm pour Discord
                        import re
                        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', verify_output)
                        # Filtrer les lignes d'erreur comm (tri de fichiers)
                        clean_output = '\n'.join(line for line in clean_output.split('\n') if not line.startswith('comm:'))
                        output_text = clean_output[:3500] if len(clean_output) > 3500 else clean_output
                        verify_title = {
                            "vm_clone": "Verification VM Clone",
                            "vm.clone": "Verification VM Clone",
                            "backup_create": "Verification Backup",
                            "backup.create": "Verification Backup",
                            "backup_restore": "Verification Restauration",
                            "backup.restore": "Verification Restauration",
                        }.get(name, f"Verification {name}")

                        send_discord_notification(
                            discord_url,
                            title=verify_title,
                            description=f"```\n{output_text}\n```",
                            color=color,
                            footer=footer
                        )
                        # Attendre pour eviter rate limit Discord
                        time.sleep(2)

                    # Deuxieme message: Resume synthetise
                    if name in ("vm_clone", "vm.clone"):
                        title = "Clone VM - Resume"

                        # Extraire les scores du rapport de verification
                        func_score = "N/A"
                        ident_score = "N/A"
                        if verify_output:
                            import re
                            # Nettoyer les codes ANSI avant extraction
                            clean_verify = re.sub(r'\x1b\[[0-9;]*m', '', verify_output)
                            # Format: "FONCTIONNEL:      96/100  (27/28)"
                            func_match = re.search(r'FONCTIONNEL:\s+(\d+)/100', clean_verify)
                            if func_match:
                                func_score = f"{func_match.group(1)}/100"
                            # Format: "IDENTITÉ:         95/100  (21/22)"
                            ident_match = re.search(r'IDENTIT[EÉ]:\s+(\d+)/100', clean_verify)
                            if ident_match:
                                ident_score = f"{ident_match.group(1)}/100"

                        fields = [
                            {"name": "Source", "value": args.get("source_vm") or args.get("source_vm_name", "?"), "inline": True},
                            {"name": "Clone", "value": args.get("new_vm_name") or args.get("target_vm_name", "?"), "inline": True},
                            {"name": "Clonage", "value": "OK" if success else "ECHEC", "inline": True},
                            {"name": "Fonctionnel", "value": func_score, "inline": True},
                            {"name": "Conformite Hote", "value": ident_score, "inline": True},
                            {"name": "Status Final", "value": "PRET" if final_success else "ERREUR", "inline": False},
                        ]
                    elif name in ("backup_create", "backup.create"):
                        title = "Backup Create - Resume"
                        fields = [
                            {"name": "Type", "value": args.get("type", "timeshift"), "inline": True},
                            {"name": "Creation", "value": "OK" if success else "ECHEC", "inline": True},
                            {"name": "Verification", "value": "OK" if verify_success else ("ECHEC" if verify_output else "N/A"), "inline": True},
                            {"name": "Status Final", "value": "TOUT EST OK" if final_success else "ERREUR", "inline": False},
                        ]
                    elif name in ("backup_restore", "backup.restore"):
                        title = "Backup Restore - Resume"
                        fields = [
                            {"name": "Type", "value": args.get("type", "timeshift"), "inline": True},
                            {"name": "Identifier", "value": args.get("identifier", "?"), "inline": True},
                            {"name": "Restauration", "value": "OK" if success else "ECHEC", "inline": True},
                            {"name": "Verification", "value": "OK" if verify_success else ("ECHEC" if verify_output else "N/A"), "inline": True},
                            {"name": "Status Final", "value": "TOUT EST OK" if final_success else "ERREUR", "inline": False},
                        ]
                    else:
                        title = f"Operation {name} - Resume"
                        fields = [
                            {"name": "Status", "value": "OK" if success else "ERREUR", "inline": True}
                        ]

                    send_discord_notification(
                        discord_url,
                        title=title,
                        fields=fields,
                        color=color,
                        footer=footer
                    )

            executor = get_async_executor(on_complete)
            fallback_result = executor.execute_async(tool_name, arguments)

            if fallback_result.success:
                msg = "Operation lancee en arriere-plan (mode local). Tu seras notifie dans le terminal."
                ui.print_success(msg)

                if self.vocal and self.voice:
                    self.voice.speak("C'est lance en arriere-plan.")

                return msg
            else:
                ui.print_error(f"Erreur fallback: {fallback_result.message}")
                return None

    def run(self) -> None:
        """Boucle principale."""

        # Configurer readline (Ctrl+L pour clear)
        setup_readline()

        ui.print_banner()

        if self.vocal:
            ui.print_info("Mode VOCAL actif - Parlez apres le bip")
            ui.print_info("Dites 'stop' ou 'arrete' pour quitter")
        else:
            ui.print_info("Tapez 'help' pour l'aide, 'quit' pour quitter.")

        ui.print_info(f"Modele: {self.llm.model}")

        # Afficher le mode actif (Phase 5)
        if self.active_mode == "performance":
            ui.print_mode_status("performance", len(PERFORMANCE_TOOLS))

        # Verifier la connexion MCP
        try:
            tools = self.mcp.list_tools()
            if tools:
                ui.print_success(f"MCP connecte: {len(tools)} outils disponibles")
            else:
                ui.print_warning("MCP: utilisation des outils par defaut")
        except Exception as e:
            ui.print_warning(f"MCP: {e} - utilisation des outils par defaut")

        print()

        # Choisir la boucle appropriee
        if self.vocal and self.voice:
            self._run_vocal_loop()
        else:
            self._run_text_loop()

    def _run_text_loop(self) -> None:
        """Boucle principale en mode texte."""
        while True:
            try:
                user_input = ui.get_user_input()

                if not user_input:
                    continue

                self.process_input(user_input)

            except KeyboardInterrupt:
                now = time.time()
                # Double Ctrl+C en moins de 1.5 secondes = quitter
                if now - self._last_ctrl_c < 1.5:
                    print()
                    ui.print_info("Au revoir !")
                    sys.exit(0)
                else:
                    self._last_ctrl_c = now
                    print()
                    ui.print_info("Ctrl+C again to quit, Ctrl+L to clear.")

            except Exception as e:
                ui.print_error(f"Erreur: {e}")

    def _run_vocal_loop(self) -> None:
        """Boucle principale en mode vocal."""
        # Annoncer le demarrage
        self.voice.speak("Lyra est prete.")
        print()
        ui.print_info("Parle apres le bip. La barre indique le niveau audio.")
        print()

        while True:
            try:
                # Ecouter (avec bip) - l'indicateur de niveau s'affiche pendant l'ecoute
                user_input = self.voice.listen(with_beep=True)

                if not user_input:
                    print("  (silence - pas de parole detectee)")
                    continue

                # Afficher ce qui a ete compris
                print(f"  Toi: \"{user_input}\"")

                # Traiter et obtenir la reponse
                response = self.process_input(user_input)

                # Prononcer la reponse
                if response and self.voice:
                    self.voice.speak(response)

                print()  # Ligne vide avant la prochaine ecoute

            except KeyboardInterrupt:
                now = time.time()
                if now - self._last_ctrl_c < 1.5:
                    print()
                    ui.print_info("Au revoir !")
                    try:
                        if self.voice:
                            self.voice.speak("Au revoir !")
                    except KeyboardInterrupt:
                        pass  # Ignorer si interrompu pendant le TTS
                    sys.exit(0)
                else:
                    self._last_ctrl_c = now
                    print()
                    ui.print_info("Ctrl+C again to quit")

            except Exception as e:
                ui.print_error(f"Erreur: {e}")
                if self.voice:
                    self.voice.speak(f"Une erreur s'est produite: {e}")


def main():
    """Point d'entree principal."""

    parser = argparse.ArgumentParser(
        description="Lyra - Assistant DevOps Local avec Human-in-the-Loop"
    )
    parser.add_argument(
        "-m", "--model",
        default="qwen2.5-coder:14b",
        help="Modele Ollama a utiliser (default: qwen2.5-coder:14b)"
    )
    parser.add_argument(
        "-v", "--vocal",
        action="store_true",
        help="Activer le mode vocal (STT/TTS)"
    )
    parser.add_argument(
        "-p", "--performance",
        action="store_true",
        help="Mode performance - execution instantanee pour domotique (Phase 5)"
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Ne pas afficher la banniere"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Lister les peripheriques audio disponibles"
    )

    args = parser.parse_args()

    # Liste des peripheriques audio
    if args.list_devices:
        import sounddevice as sd
        print("Peripheriques audio disponibles:")
        print(sd.query_devices())
        sys.exit(0)

    lyra = Lyra(model=args.model, vocal=args.vocal, performance_mode=args.performance)
    lyra.run()


if __name__ == "__main__":
    main()
