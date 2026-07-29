#!/usr/bin/env python3
from __future__ import annotations
"""
Lyra RAG - Point d'entree principal.

Version 2.0 avec architecture RAG hybride et dual models.

Usage:
    python main_rag.py                          # Mode interactif
    python main_rag.py --vocal                  # Mode vocal
    python main_rag.py -p                       # Mode performance
    python main_rag.py "demarre preprod-09"     # One-shot
    python main_rag.py "status des VMs" -v      # One-shot verbose
    python main_rag.py -y "allume la lumiere"   # One-shot auto-confirme

Architecture:
    USER INPUT -> RAG -> EPHAISTOS -> [clarification?] -> LYRA -> HESTIA -> LYRA -> OUTPUT
"""

import sys
import threading
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ajouter le package lyra au path
sys.path.insert(0, str(Path(__file__).parent))

from lyra.core.config import RAGConfig
from lyra.core.constants import DANGEROUS_TOOLS, PERFORMANCE_TOOLS, VALID_TRACKING_FILTERS
# QueryType et PipelineResult importes depuis types.py (pas de torch/sentence_transformers)
# Pipeline importe dans main() apres le banner pour ne pas bloquer le demarrage
from lyra.core.types import QueryType, PipelineResult
from lyra.core.workflows.context import UIContext, ExecContext
from lyra.core.workflows.vm_clone_exec import handle_vm_clone_with_stop
from lyra.core.workflows.vm_snapshot_exec import handle_snapshot_restore_with_safety
from lyra.models.model_manager import ModelManager
from lyra.rag.session_memory import SessionMemory
from lyra.hestia.background_tasks import BackgroundTaskManager
from lyra.utils.error_log import (
    ERROR_LOG_DIR,
    write_error_log,
    lyra_error_message as _lyra_error_message_fn,
    is_execution_error as _is_execution_error_fn,
)

# Import du module UI existant pour la compatibilite
from modules import ui
from modules.n8n import send_discord_notification
import yaml


def _lyra_error_message(log_path: Path) -> str:
    return _lyra_error_message_fn(log_path)


def _is_execution_error(exec_result) -> bool:
    return _is_execution_error_fn(exec_result)


def _handle_error_log(tool_name: str, arguments: dict, exec_result, vocal: bool = False, voice=None) -> None:
    """Ecrit le log d'erreur et affiche le message LYRA friendly."""
    log_path = write_error_log(tool_name, arguments, exec_result)
    err_msg = _lyra_error_message(log_path)
    print(f"\n{ui.Colors.RED}{err_msg}{ui.Colors.RESET}")
    if vocal and voice:
        voice.speak("ca a pas marche, j'ai logué l'erreur.")


# Helper pour accéder au pipeline réel (V2 ou Enhanced)
def get_actual_pipeline(pipeline):
    """Retourne le pipeline V2 sous-jacent si EnhancedPipeline, sinon le pipeline lui-même."""
    return pipeline._pipeline_v2 if hasattr(pipeline, '_pipeline_v2') else pipeline


# Mapping nom symbolique -> code ANSI pour UIContext.colored
_COLOR_MAP: dict[str, str] = {
    "yellow": ui.Colors.YELLOW,
    "cyan": ui.Colors.CYAN,
    "green": ui.Colors.GREEN,
    "red": ui.Colors.RED,
    "magenta": ui.Colors.MAGENTA,
    "blue": ui.Colors.BLUE,
    "bold": ui.Colors.BOLD,
    "dim": ui.Colors.DIM,
    "white": ui.Colors.WHITE,
}


def _colored_by_name(text: str, color: str) -> str:
    """Wrapper ui.colored acceptant les noms symboliques ('yellow') ou les codes ANSI directs."""
    return ui.colored(text, _COLOR_MAP.get(color.lower(), color))


def _try_fast_path_rules(query: str):
    """Tente de matcher la query via regles statiques SANS initialiser le RAG.

    Applique la normalisation slang (pure Python, <1ms) puis teste les regles.
    Si un match est trouve, retourne l'EphaistosAnalysis directement —
    ce qui permet d'utiliser initialize_fast() et de skipper SentenceTransformer,
    ChromaDB, IntentClassifier LLM et EPHAISTOS LLM.

    Returns:
        EphaistosAnalysis si regle matchee, None sinon
    """
    try:
        from lyra.rules import detect
        from lyra.core.formatters import enrich_optional_args

        # Normalisation slang (pure Python, aucune dep lourde)
        normalized = query
        try:
            from lyra.rag_enhanced.slang_normalizer import get_default_normalizer
            normalized = get_default_normalizer().normalize(query)
        except ImportError:
            pass  # Module optionnel absent, continuer avec la query originale
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("slang_normalizer failed: %s", e)

        # Tester query normalisee d'abord, puis originale si differente
        candidates = [normalized, query] if normalized != query else [query]
        for q in candidates:
            analysis = detect(q)
            if analysis is not None:
                return enrich_optional_args(q, analysis)
        return None
    except ImportError:
        pass  # Module rules absent, fallback sur le pipeline complet
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("fast_path_rules failed: %s", e)
    return None


# DANGEROUS_TOOLS et PERFORMANCE_TOOLS importes depuis lyra.core.constants

# Outils avec operations async (longues) qui necessitent notification Discord
ASYNC_TOOLS = [
    "vm_clone", "vm_clone_system",
    "backup_create", "backup_restore",
    "vm_snapshot",  # Restauration snapshot
    "vm_export",    # Export + virt-sysprep (10-20 min)
    "vm_import",    # Import + copie disque (5-10 min)
]

# Variable globale pour webhook Discord
DISCORD_WEBHOOK_URL = None


def load_config(config_path: str = "config.yaml") -> RAGConfig:
    """Charge la configuration."""
    path = Path(config_path)
    if not path.exists():
        ui.print_error(f"Config file not found: {config_path}")
        sys.exit(1)

    return RAGConfig.from_yaml(path)


def check_models(config: RAGConfig) -> bool:
    """Verifie que les modeles sont disponibles."""
    ui.print_info("Verification des modeles Ollama...")

    manager = ModelManager(config)
    available = manager.check_models_available()

    if not available.get("ephaistos"):
        ui.print_error(f"Modele EPHAISTOS non trouve: {config.models.ephaistos.name}")
        print(f"    Installez-le avec: ollama pull {config.models.ephaistos.name}")
        return False

    if not available.get("lyra"):
        ui.print_error(f"Modele LYRA non trouve: {config.models.lyra.name}")
        print(f"    Installez-le avec: ollama pull {config.models.lyra.name}")
        return False

    ui.print_success(f"EPHAISTOS: {config.models.ephaistos.name}")
    ui.print_success(f"LYRA: {config.models.lyra.name}")
    return True


def check_devices(cfg: dict) -> None:
    """Ping rapide des peripheriques domotiques au demarrage (non-bloquant).

    Affiche un avertissement si un device est injoignable, mais ne bloque pas.
    """
    import socket
    import urllib.request

    devices: list[tuple[str, str]] = []  # (label, check_type:address)

    tv_host = cfg.get("tv", {}).get("host")
    if tv_host:
        devices.append((f"TV  [{tv_host}]", f"http:{tv_host}:1925"))

    hue_ip = cfg.get("hue", {}).get("bridge_ip")
    if hue_ip:
        devices.append((f"Hue [{hue_ip}]", f"http:{hue_ip}:80"))

    denon_host = cfg.get("denon", {}).get("host")
    denon_port = cfg.get("denon", {}).get("port", 23)
    if denon_host:
        devices.append((f"Denon [{denon_host}]", f"tcp:{denon_host}:{denon_port}"))

    if not devices:
        return

    for label, check in devices:
        try:
            proto, host, port_str = check.split(":")
            port = int(port_str)
            if proto == "tcp":
                s = socket.create_connection((host, port), timeout=1.5)
                s.close()
            else:
                urllib.request.urlopen(f"http://{host}:{port}/", timeout=1.5)
            ui.print_success(f"  {label}")
        except Exception:
            ui.print_warning(f"  {label}  (injoignable)")


def print_banner(mode="v2", ephaistos_model="Qwen", lyra_model="Llama"):
    """Affiche la banniere avec le mode actif et les vrais noms de modeles.

    Args:
        mode: "enhanced" (RAG Enhanced), "legacy" (V1), ou "v2" (standard)
        ephaistos_model: Nom du modele EPHAISTOS (depuis config)
        lyra_model: Nom du modele LYRA (depuis config)
    """
    if mode == "enhanced":
        title = "LYRA RAG ENHANCED"
        subtitle = "3-Tier RAG + Slang + Context + Feedback"
    elif mode == "legacy":
        title = "LYRA Legacy"
        subtitle = "Assistant DevOps Classique"
    else:  # v2
        title = "LYRA RAG"
        subtitle = "Assistant DevOps avec RAG + Dual Models"

    def _model_line(prefix: str, model: str, role: str) -> str:
        """Construit une ligne modele qui tient en 49 chars."""
        full = f"{prefix}{model} - {role}"
        if len(full) <= 49:
            return full
        # Essayer sans le role
        short = f"{prefix}{model}"
        if len(short) <= 49:
            return short
        # Tronquer le nom du modele
        max_model = 49 - len(prefix)
        return f"{prefix}{model[:max_model - 1]}~"

    eph_line = _model_line("EPHAISTOS: ", ephaistos_model, "Analyse & Validation")
    lyra_line = _model_line("LYRA: ", lyra_model, "Dialogue & Personnalite")

    banner = f"""
    ╔═══════════════════════════════════════════════════╗
    ║  {title:^49s}  ║
    ║  {subtitle:^49s}  ║
    ╠═══════════════════════════════════════════════════╣
    ║  {eph_line:<49s}  ║
    ║  {lyra_line:<49s}  ║
    ║  HESTIA - Execution MCP                           ║
    ╚═══════════════════════════════════════════════════╝
    """
    print(ui.colored(banner, ui.Colors.CYAN))


def should_skip_confirmation(tool_name: str, mode: str) -> bool:
    """Determine si on peut skip la confirmation.

    Args:
        tool_name: Nom de l'outil
        mode: Mode actif (default ou performance)

    Returns:
        True si on peut executer sans confirmation
    """
    # Toujours confirmer les outils dangereux
    if tool_name in DANGEROUS_TOOLS:
        return False

    # Mode performance: skip pour les outils domotique
    if mode == "performance" and tool_name in PERFORMANCE_TOOLS:
        return True

    return False


def _get_lyra_rag_step_message(step: str, data: dict) -> Optional[str]:
    """Genere un message LYRA pour une etape du RAG 3-tier (M1 verbose).

    Delegue a LyraVoice.get_rag_step_message() qui gere les templates.

    Args:
        step: Nom de l'etape
        data: Donnees de l'etape (score, server, tool, ...)

    Returns:
        Message a afficher ou None
    """
    try:
        from lyra.models.lyra_voice import LyraVoice
        return LyraVoice.get_rag_step_message(step, data)
    except Exception:
        return None


def _handle_correction_intelligente(
    pipeline,
    tool_name: str,
    arguments: dict,
    rag_results: list = None
) -> Optional[tuple]:
    """Gere la correction intelligente quand l'user dit que la reponse est mauvaise (M3).

    Demande a l'user ce qui ne va pas (serveur / outil / params),
    affiche les alternatives disponibles, et retourne le nouveau choix.

    Args:
        pipeline: Pipeline RAG
        tool_name: Nom de l'outil propose
        arguments: Arguments proposes
        rag_results: Resultats RAG pour afficher les alternatives

    Returns:
        (new_tool_name, new_arguments) ou None si annule
    """
    actual_pipeline = get_actual_pipeline(pipeline)
    server_prefix = tool_name.split(".")[0] if "." in tool_name else ""
    short_tool = tool_name.split(".")[-1] if "." in tool_name else tool_name

    ui.print_lyra_tag("c'est quoi qui va pas ?")
    print()
    print("  1. Le serveur MCP  (ex: FEDORA au lieu de HUE)")
    print("  2. L'outil         (ex: vm_start au lieu de vm_clone)")
    print("  3. Les parametres  (ex: mauvais nom de VM)")
    print()

    choice = input("  [1/2/3] ou [n] pour annuler : ").strip().lower()

    if choice in ("n", "non", ""):
        return None

    if choice == "1":
        # Afficher les serveurs disponibles
        try:
            servers = list(actual_pipeline._hestia.mcp_manager.clients.keys())
        except Exception:
            servers = ["FEDORA", "HUE", "TV", "CATT", "DENON"]

        print()
        print(ui.colored("Serveurs disponibles :", ui.Colors.YELLOW))
        for i, s in enumerate(servers, 1):
            marker = " <-- actuel" if s.lower() == server_prefix.lower() else ""
            print(f"  {i}. {s}{marker}")
        print()

        srv_choice = input("  Numero du bon serveur (ou nom) : ").strip()
        if srv_choice.isdigit() and 1 <= int(srv_choice) <= len(servers):
            new_server = servers[int(srv_choice) - 1]
        elif srv_choice:
            new_server = srv_choice.upper()
        else:
            return None

        # Relancer le pipeline avec le serveur force
        ui.print_lyra_tag(f"ok je cherche dans {new_server}...")
        # Retourner None pour relancer via l'input utilisateur avec contexte
        return None

    elif choice == "2":
        # Afficher les outils du meme serveur
        print()
        print(ui.colored(f"Outils disponibles sur {server_prefix or 'tous serveurs'} :", ui.Colors.YELLOW))

        try:
            # Recuperer les outils du serveur depuis HESTIA
            all_tools = []
            mcp_mgr = actual_pipeline._hestia.mcp_manager
            for srv_name, client in mcp_mgr.clients.items():
                if not server_prefix or srv_name.lower() == server_prefix.lower():
                    if hasattr(client, 'tools') and client.tools:
                        for t in client.tools:
                            all_tools.append((srv_name, t.get('name', '')))

            if not all_tools:
                # Fallback: afficher les outils du resultat RAG si disponible
                print("  (liste non disponible)")
                return None

            # Afficher au max 12 outils pour lisibilite
            display_tools = all_tools[:12]
            for i, (srv, t) in enumerate(display_tools, 1):
                short = t.split(".")[-1] if "." in t else t
                marker = " <-- actuel" if t == tool_name or short == short_tool else ""
                print(f"  {i:2}. {short}{marker}")

            if len(all_tools) > 12:
                print(f"  ... et {len(all_tools) - 12} autres")

        except Exception:
            print("  (liste non disponible, tape le nom directement)")

        print()
        tool_choice = input("  Numero ou nom de l'outil : ").strip()

        new_tool = None
        if tool_choice.isdigit():
            idx = int(tool_choice) - 1
            if 0 <= idx < len(all_tools):
                srv, new_tool = all_tools[idx]
                new_tool = f"{srv}.{new_tool}" if "." not in new_tool else new_tool
        elif tool_choice:
            new_tool = tool_choice

        if new_tool:
            ui.print_lyra_tag(f"ok, je garde les memes params pour {new_tool}. On y va ?")
            confirm = input("  [O/n] : ").strip().lower()
            if confirm not in ("n", "non"):
                return (new_tool, arguments)

        return None

    elif choice == "3":
        # Afficher les params de l'outil actuel
        print()
        print(ui.colored(f"Parametres de {short_tool} :", ui.Colors.YELLOW))

        # Params actuels
        print()
        print("  Valeurs actuelles :")
        for key, value in arguments.items():
            print(f"    {key} = {value}")

        # Essayer de recuperer les params depuis les specs RAG
        print()
        print("  Modifie les valeurs (entree vide = garder) :")
        new_arguments = {}
        for key, value in arguments.items():
            new_val = input(f"    {key} [{value}] : ").strip()
            new_arguments[key] = new_val if new_val else value

        ui.print_lyra_tag(f"ok, {short_tool} avec les nouveaux params. On y va ?")
        for k, v in new_arguments.items():
            print(f"  {k} = {v}")
        print()
        confirm = input("  [O/n] : ").strip().lower()
        if confirm not in ("n", "non"):
            return (tool_name, new_arguments)

        return None

    return None


def _generate_context_confirmation_message(result, tool_name: str, arguments: dict) -> str:
    """Génère un message de confirmation expliquant le contexte injecté.

    Args:
        result: Résultat du pipeline avec contexte injecté
        tool_name: Nom de l'outil MCP
        arguments: Arguments de l'outil

    Returns:
        str: Message de confirmation LYRA friendly
    """
    # Extraire contexte du enriched_query
    # Format: "[ctx: last_mcp=fedora.vm_start, last_server=FEDORA, last_vm=preprod-09]"
    enriched_query = result.enriched_query or ""
    context_parts = {}

    if "[ctx:" in enriched_query:
        # Extraire la partie contexte
        ctx_str = enriched_query.split("[ctx:")[1].split("]")[0]

        # Parser les paires key=value
        for part in ctx_str.split(","):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                context_parts[key] = value

    # Construire message selon contexte
    last_mcp = context_parts.get("last_mcp", "")
    last_server = context_parts.get("last_server", "")
    last_vm = context_parts.get("last_vm", "")

    # Action formatée
    action_desc = tool_name.split(".")[-1].replace("_", " ")

    # Construire message contextuel
    msg_parts = []

    if last_vm:
        msg_parts.append(f"sur la VM **{last_vm}**")

    if last_mcp:
        last_action = last_mcp.split(".")[-1].replace("_", " ")
        msg_parts.append(f"(dernier outil: {last_action})")

    if msg_parts:
        context_desc = " ".join(msg_parts)
        message = (
            f"J'ai détecté une ambiguïté. "
            f"D'après le contexte {context_desc}, "
            f"je vais exécuter : **{action_desc}**. "
            f"C'est bien ça ?"
        )
    else:
        # Fallback si pas de contexte clair
        message = (
            f"J'ai détecté une ambiguïté. "
            f"Je propose d'exécuter : **{action_desc}**. "
            f"Confirmes-tu ?"
        )

    return message


def handle_action(
    pipeline: Pipeline,
    result: PipelineResult,
    mode: str,
    vocal: bool = False,
    voice=None,
    task_manager: Optional[BackgroundTaskManager] = None,
    webhook_url: Optional[str] = None
) -> str:
    """Gere une action avec confirmation adaptee au niveau de confiance (M2/M3).

    Args:
        pipeline: Instance du pipeline RAG
        result: Resultat du pipeline avec tool_call
        mode: Mode actif
        vocal: Mode vocal actif
        voice: Instance VoiceInterface
        task_manager: Gestionnaire de taches en arriere-plan (optionnel)
        webhook_url: URL webhook Discord (optionnel)

    Returns:
        Message de reponse
    """
    tool_name = result.tool_call["name"]
    arguments = result.tool_call["arguments"]

    # Cas special: clone avec arret de VM / restauration de snapshot
    if tool_name == "vm_clone_with_stop" or (
        "vm_snapshot" in tool_name and arguments.get("action") == "revert"
    ):
        actual = get_actual_pipeline(pipeline)
        exec_ctx = ExecContext(
            ui=UIContext(
                print_info=ui.print_info,
                print_success=ui.print_success,
                print_error=ui.print_error,
                print_warning=ui.print_warning,
                print_tool_result=ui.print_tool_result,
                colored=_colored_by_name,
                confirm_action=ui.confirm_action,
                ask_input=input,
                println=print,
            ),
            execute_action=actual.execute_action,
            hestia_execute=actual._hestia.execute,
            vocal=vocal,
            voice=voice,
            notify_discord=_send_discord_if_async,
        )
        if tool_name == "vm_clone_with_stop":
            return handle_vm_clone_with_stop(arguments, exec_ctx)
        return handle_snapshot_restore_with_safety(arguments, exec_ctx)

    # Context Injector: Confirmation explicite si contexte injecte (ambiguite detectee)
    context_injected = hasattr(result, 'context_injected') and result.context_injected
    requires_confirmation = hasattr(result, 'requires_confirmation') and result.requires_confirmation

    if context_injected and hasattr(result, 'enriched_query'):
        context_msg = _generate_context_confirmation_message(result, tool_name, arguments)
        print(f"\n{ui.Colors.YELLOW}[Context Injector]{ui.Colors.RESET}")
        print(f"{context_msg}\n")
        if vocal and voice:
            voice.speak(context_msg)

    # Mode performance: execution rapide si autorise ET pas de contexte injecte
    if should_skip_confirmation(tool_name, mode) and not requires_confirmation:
        ui.print_info(f"Execution rapide: {tool_name}")
        exec_result = get_actual_pipeline(pipeline).execute_action(tool_name, arguments)

        has_error = _is_execution_error(exec_result)
        if has_error:
            _handle_error_log(tool_name, arguments, exec_result, vocal, voice)
        ui.print_quick_result(tool_name, success=not has_error, use_beep=True)
        _send_discord_if_async(tool_name, arguments, exec_result)
        return exec_result.response

    # --- M2 : Confirmation adaptee selon niveau de confiance ---
    confidence_level = getattr(result, 'confidence_level', 'high') or 'high'
    short_tool = tool_name.split(".")[-1].replace("_", " ") if tool_name else "?"
    target = arguments.get("vm_name") or arguments.get("source_vm") or ""

    # Afficher l'action proposee (toujours)
    ui.print_tool_call(tool_name, arguments)

    if confidence_level == "high":
        # HIGH (80-100%): confirmation courte et directe
        if target:
            prompt_msg = f"{short_tool} sur {target}. C'est bon ?"
        else:
            prompt_msg = f"je vais {short_tool}. C'est bon ?"
        ui.print_lyra_tag(prompt_msg)
        if vocal and voice:
            voice.speak(prompt_msg)

    elif confidence_level == "medium":
        # MEDIUM (50-80%): verif etat MCP + confirmation du bon serveur
        server_prefix = tool_name.split(".")[0].upper() if "." in tool_name else "?"
        if target:
            status_hint = ""
            # Tentative de recuperation de l'etat si VM
            if "vm" in tool_name.lower() and target:
                try:
                    actual_pl = get_actual_pipeline(pipeline)
                    status_result = actual_pl.execute_action("fedora.vm_status", {"vm_name": target})
                    if status_result.execution_result and status_result.execution_result.success:
                        raw = status_result.execution_result.result or ""
                        # Extraire etat court depuis le resultat
                        if "running" in raw.lower() or "en cours" in raw.lower():
                            status_hint = " [etat: demarre]"
                        elif "shut off" in raw.lower() or "arret" in raw.lower():
                            status_hint = " [etat: arretee]"
                        else:
                            status_hint = ""
                except Exception:
                    status_hint = ""
            prompt_msg = (
                f"je pense {short_tool} sur {target}{status_hint}. "
                f"C'est bien via {server_prefix} ? Confirme ?"
            )
        else:
            prompt_msg = f"je pense {short_tool} via {server_prefix}. C'est bien ca ?"
        ui.print_lyra_tag(prompt_msg)
        if vocal and voice:
            voice.speak(prompt_msg)

    else:
        # LOW (0-50%): LYRA exprime son incertitude
        rag_results = getattr(result, '_rag_candidates', [])
        if rag_results and len(rag_results) >= 2:
            opt1 = rag_results[0].get('metadata', {}).get('tool_name', short_tool) if rag_results else short_tool
            opt2 = rag_results[1].get('metadata', {}).get('tool_name', '?') if len(rag_results) > 1 else '?'
            opt1 = opt1.split(".")[-1].replace("_", " ")
            opt2 = opt2.split(".")[-1].replace("_", " ")
            prompt_msg = (
                f"franchement je suis pas super sure... "
                f"tu parles de {opt1} ou de {opt2} ? "
                f"Je propose {short_tool} mais dis-moi si c'est pas ca."
            )
        else:
            prompt_msg = (
                f"je suis pas certaine, j'ai propose {short_tool} "
                f"mais ca me semble ambigu. Tu confirmes ?"
            )
        ui.print_lyra_tag(prompt_msg)
        if vocal and voice:
            voice.speak(prompt_msg)

    # Demander confirmation standard
    confirmed = ui.confirm_action(
        tool_name,
        arguments,
        vocal_mode=vocal,
        voice=voice
    )

    # --- M3 : Correction intelligente si "modifier" ---
    if confirmed == "modify":
        correction = _handle_correction_intelligente(pipeline, tool_name, arguments)

        if correction is None:
            ui.print_warning("Action annulee.")
            return "Action annulee."

        new_tool_name, new_arguments = correction
        tool_name = new_tool_name
        arguments = new_arguments

        # Re-confirmer avec les nouvelles valeurs
        ui.print_tool_call(tool_name, arguments)
        confirmed = ui.confirm_action(
            tool_name,
            arguments,
            vocal_mode=vocal,
            voice=voice
        )
        if not confirmed or confirmed == "modify":
            ui.print_warning("Action annulee.")
            return "Action annulee."

    # Cas: Utilisateur annule
    if not confirmed:
        ui.print_warning("Action annulee.")
        return "Action annulee."

    # Verifier si operation async (longue)
    # EnhancedPipeline wrappe Pipeline V2, accéder via _pipeline_v2
    hestia = pipeline._pipeline_v2._hestia if hasattr(pipeline, '_pipeline_v2') else pipeline._hestia

    if task_manager and hestia.is_async_tool(tool_name):
        async_info = hestia.get_async_info(tool_name)

        # Validation concurrence: verifier si VM deja utilisee
        vm_name = arguments.get("vm_name") or arguments.get("source_vm")
        if vm_name:
            existing_task = task_manager.get_vm_in_use(vm_name)

            if existing_task:
                # Afficher warning
                from datetime import datetime
                print()
                print(ui.colored(f"⚠️  La VM {vm_name} est deja utilisee par:", ui.Colors.YELLOW + ui.Colors.BOLD))
                print(f"    - Tache: {existing_task.description}")

                elapsed = (datetime.now() - existing_task.started_at).total_seconds()
                print(f"    - En cours depuis: {int(elapsed)}s")
                print()

                # Demander confirmation
                print("Options:")
                print("  1. Continuer quand meme (risque de conflit)")
                print("  2. Annuler")
                print()

                choice = input("Choix ? [1/2] ").strip()

                if choice != "1":
                    ui.print_warning("Operation annulee.")
                    return "Operation annulee (VM en cours d'utilisation)."

                # Utilisateur prend le risque
                print()
                ui.print_warning("⚠️  Attention: Operations concurrentes sur la meme VM!")
                print()

        # Generer message friendly de LYRA
        lyra_inst = pipeline._pipeline_v2._lyra if hasattr(pipeline, '_pipeline_v2') else pipeline._lyra
        friendly_msg = lyra_inst.generate_async_message(
            tool_name=tool_name,
            estimated_time=async_info["estimated_time"],
            description=async_info["description"]
        )

        print()
        print(friendly_msg)
        print()

        # Lancer en subprocess
        task_id = task_manager.launch_task(
            tool_name=tool_name,
            arguments=arguments,
            description=async_info["description"],
            estimated_time=async_info["estimated_time"],
            webhook_url=webhook_url
        )

        msg = f"Operation lancee en arriere-plan (task: {task_id[-6:]})"
        ui.print_success(msg)

        return msg

    # Executer via HESTIA (synchrone)
    ui.print_info(f"Execution de {tool_name}...")
    exec_result = get_actual_pipeline(pipeline).execute_action(tool_name, arguments)

    has_error = _is_execution_error(exec_result)
    if exec_result.executed:
        ui.print_tool_result(exec_result.response, success=not has_error)
    else:
        ui.print_tool_result(exec_result.response, success=False)
        has_error = True

    if has_error:
        _handle_error_log(tool_name, arguments, exec_result, vocal, voice)

    # Envoyer notification Discord si operation async
    _send_discord_if_async(tool_name, arguments, exec_result)

    return exec_result.response


def _send_discord_if_async(tool_name: str, arguments: dict, exec_result) -> bool:
    """Envoie une notification Discord si l'outil est async.

    Args:
        tool_name: Nom de l'outil execute
        arguments: Arguments de l'outil
        exec_result: Resultat d'execution

    Returns:
        True si notification envoyee
    """
    global DISCORD_WEBHOOK_URL

    # Extraire le nom court (sans prefixe serveur)
    short_name = tool_name.split(".")[-1] if "." in tool_name else tool_name

    # Verifier si outil async
    if short_name not in ASYNC_TOOLS or not DISCORD_WEBHOOK_URL:
        return False

    # Exception: vm_snapshot list n'est pas async (opération rapide de lecture)
    if short_name == "vm_snapshot" and arguments.get("action") == "list":
        return False

    # Construire le titre et les fields
    title_map = {
        "vm_clone": "🔄 Clone VM",
        "vm_clone_system": "🔄 Clone System VM",
        "backup_create": "💾 Backup Create",
        "backup_restore": "📦 Backup Restore",
        "vm_snapshot": "📸 Snapshot VM"
    }

    title = title_map.get(short_name, f"✨ {short_name}")
    is_success = exec_result.execution_result and exec_result.execution_result.success if hasattr(exec_result, 'execution_result') else False
    color = 3066993 if is_success else 15158332  # Vert ou rouge

    fields = [
        {"name": "Outil", "value": short_name, "inline": True},
        {"name": "Status", "value": "✅ OK" if is_success else "❌ ERREUR", "inline": True},
    ]

    # Ajouter les arguments pertinents
    for key, value in arguments.items():
        if value and key not in ("start", "verbose"):  # Ignorer les flags
            fields.append({"name": key, "value": str(value), "inline": True})

    # Description (resultat ou erreur)
    if is_success:
        # Tronquer le resultat si trop long
        description = exec_result.response[:500]
        if len(exec_result.response) > 500:
            description += "..."
    else:
        description = f"❌ {exec_result.error or 'Erreur inconnue'}"

    # Envoyer
    return send_discord_notification(
        webhook_url=DISCORD_WEBHOOK_URL,
        title=title,
        description=f"```\n{description}\n```" if is_success else description,
        fields=fields,
        color=color,
        footer="Lyra RAG v2.0 - DevOps Assistant"
    )


def run_one_shot(
    request: str,
    pipeline,
    mode: str,
    verbose: bool = False,
    yes: bool = False,
    task_manager=None,
    webhook_url: str = "",
    fast_analysis=None,
) -> int:
    """Execute une requete en mode one-shot et retourne le code de sortie.

    Args:
        request: La requete utilisateur
        pipeline: Instance du pipeline RAG
        mode: Mode actif (default ou performance)
        verbose: Afficher les etapes intermediaires du pipeline
        yes: Auto-confirmer les actions (sauf outils dangereux)
        task_manager: Gestionnaire de taches en arriere-plan
        webhook_url: URL webhook Discord

    Returns:
        Code de sortie: 0=ok, 1=erreur, 2=annule, 3=args manquants
    """
    def on_rag_step_verbose(step: str, data: dict):
        score = data.get("score", 0.0)
        if score > 0.80:
            color = ui.Colors.GREEN
        elif score >= 0.50:
            color = ui.Colors.YELLOW
        else:
            color = ui.Colors.RED
        if step == "before_llm":
            level = data.get("confidence_level", "medium")
            tool = data.get("tool", "?").split(".")[-1].replace("_", " ")
            score_str = f"{score:.2f}" if score else "?"
            print(f"  {color}[rag] {tool} score={score_str} ({level}){ui.Colors.RESET}", flush=True)
        else:
            tool = data.get("tool", "") or data.get("server", "")
            if tool:
                score_str = f"{score:.2f}" if score else "?"
                print(f"  {color}[rag] {step}: {tool} score={score_str}{ui.Colors.RESET}", flush=True)

    def on_progress_verbose(step: str, message: str):
        if step == "acknowledgement":
            print(f"  {ui.Colors.CYAN}[lyra] {message}{ui.Colors.RESET}", flush=True)

    # Traiter la requete via le pipeline
    # Fast path : analyse pre-calculee par regles, skip IntentClassifier + RAG + EPHAISTOS
    if fast_analysis is not None and hasattr(pipeline, 'process_precomputed'):
        result = pipeline.process_precomputed(request, fast_analysis)
    else:
        # rag_step_callback seulement pour EnhancedPipeline (Pipeline V2 ne l'accepte pas)
        process_kwargs = {"callback": on_progress_verbose if verbose else None}
        if hasattr(pipeline, '_pipeline_v2'):
            process_kwargs["rag_step_callback"] = on_rag_step_verbose if verbose else None
        result = pipeline.process(request, **process_kwargs)

    # Afficher le type d'intention si verbose
    if verbose:
        qtype = result.query_type.value if hasattr(result.query_type, 'value') else str(result.query_type)
        print(f"  {ui.Colors.CYAN}[intent] {qtype}{ui.Colors.RESET}")

    # Cas 1: Question de connaissance -> reponse directe
    if result.query_type == QueryType.KNOWLEDGE:
        ui.print_lyra(result.response)
        return 0

    # Cas 2: Args manquants -> impossible en one-shot
    if result.pending_args:
        ui.print_lyra_tag(result.response)
        ui.print_warning(f"One-shot: arguments manquants ({', '.join(result.pending_args)})")
        ui.print_warning("Relancez avec la requete complete ou utilisez le mode interactif.")
        return 3

    # Cas 3: Action prete -> confirmation et execution
    if result.tool_call:
        tool_name = result.tool_call["name"]
        arguments = result.tool_call["arguments"]

        if verbose:
            print(f"  {ui.Colors.CYAN}[action] {tool_name}({arguments}){ui.Colors.RESET}")

        # Afficher la reponse de LYRA
        ui.print_lyra(result.response)

        # Determiner si confirmation necessaire
        is_dangerous = tool_name in DANGEROUS_TOOLS
        skip_confirm = should_skip_confirmation(tool_name, mode)

        if not skip_confirm and not (yes and not is_dangerous):
            # Afficher l'action et demander confirmation
            ui.print_tool_call(tool_name, arguments)
            if is_dangerous:
                print(
                    f"\n{ui.Colors.RED}ATTENTION action dangereuse: {tool_name}. "
                    f"Confirmer ? [o/N]{ui.Colors.RESET} ",
                    end="", flush=True
                )
            else:
                short = tool_name.split(".")[-1].replace("_", " ")
                tag = f'{ui.Colors.BG_ORANGE}{ui.Colors.FG_DARK} Lyra {ui.Colors.RESET}'
                print(f'\n{tag} {short}. C\'est bon ? [O/n] ', end="", flush=True)
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                ui.print_warning("Annule.")
                return 2

            confirmed = answer in ("o", "oui") if is_dangerous else answer in ("", "o", "oui")
            if not confirmed:
                ui.print_warning("Action annulee.")
                return 2
        elif verbose:
            ui.print_info(f"Execution auto: {tool_name}")

        # Verifier si operation async (longue)
        hestia = pipeline._pipeline_v2._hestia if hasattr(pipeline, '_pipeline_v2') else pipeline._hestia
        if task_manager and hestia.is_async_tool(tool_name):
            async_info = hestia.get_async_info(tool_name)
            task_id = task_manager.launch_task(
                tool_name=tool_name,
                arguments=arguments,
                description=async_info["description"],
                estimated_time=async_info["estimated_time"],
                webhook_url=webhook_url,
            )
            ui.print_success(f"Operation lancee en arriere-plan (task: {task_id[-6:]})")
            return 0

        # Executer via HESTIA (synchrone)
        # skip_lyra_format=True en fast path : evite l'appel LLM format_result
        if verbose:
            ui.print_info(f"Execution: {tool_name}...")
        exec_result = get_actual_pipeline(pipeline).execute_action(
            tool_name, arguments,
            skip_lyra_format=(fast_analysis is not None)
        )

        has_error = _is_execution_error(exec_result)
        if exec_result.executed:
            ui.print_tool_result(exec_result.response, success=not has_error)
        else:
            ui.print_tool_result(exec_result.response, success=False)
            has_error = True

        if has_error:
            _handle_error_log(tool_name, arguments, exec_result)
            return 1

        _send_discord_if_async(tool_name, arguments, exec_result)
        return 0

    # Cas 4: Pas de match -> reponse directe
    ui.print_lyra(result.response)
    return 0


def main():
    """Point d'entree principal."""
    global DISCORD_WEBHOOK_URL

    parser = argparse.ArgumentParser(
        description="Lyra RAG - Assistant DevOps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples:\n"
            "  python main_rag.py                         # Mode interactif\n"
            "  python main_rag.py \"demarre preprod-09\"    # One-shot\n"
            "  python main_rag.py \"status des VMs\" -v     # One-shot verbose\n"
            "  python main_rag.py -y \"allume la lumiere\"  # One-shot auto-confirme\n"
            "  python main_rag.py -p \"status vms\" -v      # Performance + verbose\n"
        )
    )
    parser.add_argument("request", nargs="?", default=None, metavar="REQUETE",
                        help="Requete one-shot (mode interactif si absent)")
    parser.add_argument("--vocal", action="store_true", help="Mode vocal (STT/TTS)")
    parser.add_argument("-p", "--performance", action="store_true", help="Mode performance")
    parser.add_argument("--config", "-c", default="config.yaml", help="Fichier de config")
    parser.add_argument("--check", action="store_true", help="Verifier les modeles et quitter")
    parser.add_argument("--rag-enhanced", action="store_true", help="Activer RAG Enhanced")
    parser.add_argument("--debug", "-d", action="store_true", help="Mode debug pipeline Enhanced")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose one-shot: affiche les etapes du pipeline")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Auto-confirmer les actions (sauf outils dangereux)")
    args = parser.parse_args()

    # Mode one-shot: requete passee en argument
    one_shot = args.request is not None

    # Charger la config (avant le bandeau pour afficher les vrais noms de modeles)
    config = load_config(args.config)

    # Fast path one-shot : detection IMMEDIATE avant check_models et init.
    # Si une regle statique matche -> on skipera check_models + SentenceTransformer + ChromaDB + LLMs.
    _fast_analysis = None
    if one_shot:
        _fast_analysis = _try_fast_path_rules(args.request)
        if _fast_analysis is not None:
            tool_short = _fast_analysis.tool.split(".")[-1].replace("_", " ") if _fast_analysis.tool else "?"
            print(f"  -> {tool_short}", flush=True)

    # Bandeau : compact en one-shot, complet en interactif
    if one_shot:
        print(f"{ui.Colors.CYAN}LYRA{ui.Colors.RESET}  {args.request}", flush=True)
    else:
        banner_mode = "enhanced" if args.rag_enhanced else "v2"
        print_banner(
            mode=banner_mode,
            ephaistos_model=config.models.ephaistos.name,
            lyra_model=config.models.lyra.name,
        )

    # Import lourd apres le banner : sentence_transformers + torch (~1-2s)
    from lyra.core.pipeline import Pipeline  # noqa: E402

    # Charger le webhook Discord depuis config.yaml
    global DISCORD_WEBHOOK_URL
    try:
        with open(args.config) as f:
            cfg = yaml.safe_load(f)
        discord_cfg = cfg.get("discord", {})
        if discord_cfg.get("enabled", False):
            DISCORD_WEBHOOK_URL = discord_cfg.get("webhook_url", "")
            if DISCORD_WEBHOOK_URL:
                ui.print_info("Discord notifications activees")
    except Exception as e:
        cfg = {}
        ui.print_warning(f"Config non chargee: {e}")

    # Health check devices (interactif uniquement, non-bloquant)
    if not one_shot:
        ui.print_info("Peripheriques domotiques :")
        check_devices(cfg)

    # Verifier les modeles en one-shot uniquement (interactif: fait dans le thread bg)
    if one_shot and _fast_analysis is None:
        if not check_models(config):
            sys.exit(1)

    if args.check:
        ui.print_success("Verification terminee.")
        sys.exit(0)

    # Mode
    mode = "performance" if args.performance else "default"

    # Interface vocale (optionnel)
    vocal = args.vocal
    voice = None
    if vocal:
        try:
            from modules.audio import VoiceInterface, AudioConfig

            with open("config.yaml") as f:
                cfg = yaml.safe_load(f)

            audio_cfg = cfg.get("audio", {})
            stt_cfg = cfg.get("stt", {})
            tts_cfg = cfg.get("tts", {})

            audio_config = AudioConfig(
                sample_rate=audio_cfg.get("sample_rate", 16000),
                channels=audio_cfg.get("channels", 1),
                silence_threshold=audio_cfg.get("silence_threshold", 0.01),
                silence_duration=audio_cfg.get("silence_duration", 1.0),
                input_device=audio_cfg.get("input_device"),
                output_device=audio_cfg.get("output_device")
            )

            ui.print_info("Chargement du modele STT (Whisper)...")
            voice = VoiceInterface(
                stt_model=stt_cfg.get("model", "base"),
                tts_model=f"models/{tts_cfg.get('model', 'fr_FR-upmc-medium')}.onnx",
                language=stt_cfg.get("language", "fr"),
                device=stt_cfg.get("device", "cuda"),
                audio_config=audio_config
            )
            ui.print_success("Interface vocale prete")
        except Exception as e:
            ui.print_warning(f"Mode vocal indisponible: {e}")
            vocal = False
            voice = None

    # Initialiser le pipeline
    if args.rag_enhanced:
        if not one_shot:
            ui.print_info("Pipeline RAG Enhanced...")
        from lyra.rag_enhanced import EnhancedPipeline
        from lyra.rag_enhanced.config import RAGEnhancedConfig

        # Charger la config RAG Enhanced depuis YAML
        with open(args.config) as f:
            cfg = yaml.safe_load(f)
        enhanced_config = RAGEnhancedConfig.from_dict(cfg.get("rag_enhanced", {}))

        pipeline = EnhancedPipeline(
            config=config,
            enhanced_config=enhanced_config,
            enabled=enhanced_config.enabled,
            tts_mode=vocal
        )
    else:
        if not one_shot:
            ui.print_info("Pipeline RAG V2...")
        pipeline = Pipeline(config, tts_mode=vocal)  # tts_mode=True si vocal

    # Initialisation en arriere-plan avec progression visible
    _init_done   = threading.Event()
    _checks_done = threading.Event()  # set apres check_models (prints finis, barre peut s'afficher)
    _init_error  = [None]

    def _bg_init():
        try:
            if _fast_analysis is not None:
                _checks_done.set()
                pipeline.initialize_fast()
            else:
                # En mode interactif: verifier les modeles ici (non-bloquant pour l'UI)
                if not one_shot and not check_models(config):
                    _init_error[0] = Exception("Modele Ollama introuvable (voir messages ci-dessus)")
                    _checks_done.set()
                    return
                _checks_done.set()   # check_models a fini de printer — la barre peut apparaitre
                pipeline.initialize()
                # Warm-up Ollama en mode interactif : charge EPHAISTOS + LYRA en VRAM
                # pendant que l'utilisateur lit le banner (premiere requete sans cold-load)
                if not one_shot:
                    pipeline.preload_models()
        except Exception as e:
            _init_error[0] = e
            _checks_done.set()
        finally:
            _init_done.set()

    threading.Thread(target=_bg_init, daemon=True).start()

    # one-shot: attendre la fin de l'init avant tout
    if one_shot:
        if _fast_analysis is not None:
            print("  connexion MCP...", end="", flush=True)
        else:
            print("  chargement...", end="", flush=True)
        _init_done.wait()
        print(" pret", flush=True)
        if _init_error[0]:
            ui.print_error(f"Erreur initialisation: {_init_error[0]}")
            sys.exit(1)
        if hasattr(pipeline, '_pipeline_v2'):
            servers = list(pipeline._pipeline_v2._hestia.mcp_manager.clients.keys())
        else:
            servers = list(pipeline._hestia.mcp_manager.clients.keys())
        if args.verbose:
            ui.print_success(f"MCP: {', '.join(servers)} ({len(servers)} serveurs)")
    _servers_shown = False  # pour afficher les serveurs au premier tour interactif

    # Session memory
    session = SessionMemory(max_turns=config.session.max_turns)

    # Background task manager
    task_manager = BackgroundTaskManager()

    # Restaurer les taches des sessions precedentes
    _restored = task_manager.restore_from_registry()
    if _restored > 0:
        print()
        ui.print_info(f"{_restored} tache(s) en cours detectee(s) depuis la session precedente.")

    # Mode one-shot: executer la requete et quitter
    if one_shot:
        sys.exit(run_one_shot(
            request=args.request,
            pipeline=pipeline,
            mode=mode,
            verbose=args.verbose,
            yes=args.yes,
            task_manager=task_manager,
            webhook_url=DISCORD_WEBHOOK_URL,
            fast_analysis=_fast_analysis,
        ))

    # Mode interactif: juste une ligne avant le prompt
    if args.debug and args.rag_enhanced:
        ui.print_warning("Mode DEBUG actif")
    if vocal:
        ui.print_info("Mode vocal actif")

    # Callback pour feedback progressif (Phase 4 - LYRA Immersive)
    def on_progress(step: str, message: str):
        """Callback pour affichage progressif de LYRA.

        Args:
            step: Type de step ("acknowledgement", "progress", "result")
            message: Message à afficher
        """
        if step == "acknowledgement":
            # Afficher l'acknowledgement immédiat en cyan (bleu clair)
            print(f"{ui.Colors.CYAN}{message}{ui.Colors.RESET}")

            # TTS immédiat si mode vocal
            if vocal and voice:
                voice.speak(message)

    # Callback verbose RAG (M1) - messages LYRA correles au score
    def on_rag_step(step: str, data: dict):
        """Callback appele a chaque etape du pipeline RAG.

        Affiche un message LYRA adapte au score intermediaire.
        Gere les etapes RAG (registry_done, capabilities_done) et pre-LLM (before_llm).

        Args:
            step: Nom de l'etape
            data: Donnees de l'etape (score, server, tool, confidence_level...)
        """
        score = data.get("score", 0.0)
        # Couleur selon score: vert=high, jaune=medium, rouge=low
        if score > 0.80:
            color = ui.Colors.GREEN
        elif score >= 0.50:
            color = ui.Colors.YELLOW
        else:
            color = ui.Colors.RED

        if step == "rule_matched":
            # Regle statique matchee : RAG skipee, message direct
            import random as _random
            tool = data.get("tool_short", data.get("tool", "?").split(".")[-1].replace("_", " "))
            server = data.get("server", "?")
            msg = _random.choice([
                f"{server}: {tool}",
                f"direct -> {tool}",
                f"j'ai ca: {server} -> {tool}",
            ])
            ui.print_lyra_tag(msg)
            if vocal and voice:
                voice.speak(msg)
            return

        if step == "before_llm":
            # Message avant l'appel EPHAISTOS
            level = data.get("confidence_level", "medium")
            tool = data.get("tool", "?").split(".")[-1].replace("_", " ")
            if level == "high":
                msg = f"EPHAISTOS verifie {tool}..."
            elif level == "medium":
                msg = f"EPHAISTOS analyse {tool}..."
            else:
                msg = "EPHAISTOS cherche parmi les options..."
            ui.print_lyra_tag(msg)
            if vocal and voice:
                voice.speak(msg)
            return

        # Etapes RAG (registry_done, capabilities_done, etc.)
        msg = _get_lyra_rag_step_message(step, data)
        if msg:
            ui.print_lyra_tag(msg)
            if vocal and voice:
                voice.speak(msg)

    # Boucle principale
    while True:
        try:
            # Afficher les notifications de succes (les erreurs restent dans le bandeau)
            completed_notifs = [n for n in task_manager.get_completed_notifications() if n.get("success")]
            if completed_notifs:
                ui.print_completed_task_notifications(completed_notifs)

            # Nettoyer les taches completees anciennes (>5min)
            task_manager.cleanup_completed(max_age_seconds=300)

            # Input (vocal ou texte)
            # live_input affiche le bandeau et le rafraichit toutes les secondes
            if vocal and voice:
                # Attendre la fin de l'init avant d'ecouter (evite pipeline.process sur init echouee)
                if not _servers_shown:
                    if not _init_done.is_set():
                        _init_done.wait()
                    if _init_error[0]:
                        ui.print_error(f"Erreur initialisation: {_init_error[0]}")
                        break
                # En mode vocal, afficher le bandeau separement (pas de live refresh)
                active_tasks = task_manager.get_active_tasks()
                if active_tasks:
                    ui.print_background_tasks(active_tasks, task_manager)
                ui.print_info("Ecoute...")
                user_input = voice.listen()
                if user_input:
                    print(f">>> {user_input}")
            else:
                # Premier tour: attendre que check_models ait fini de printer
                # avant de dessiner la barre (evite corruption de la barre)
                if not _servers_shown and not _checks_done.is_set():
                    _checks_done.wait()
                _loading = _init_done if not _servers_shown else None
                user_input = ui.live_input(">>> ", task_manager, loading=_loading, mode=mode).strip()

            # Afficher les notifications de succes creees PENDANT live_input
            new_notifs = [n for n in task_manager.get_completed_notifications() if n.get("success")]
            if new_notifs:
                ui.print_completed_task_notifications(new_notifs)

            # Attendre fin init si l'utilisateur a soumis avant la fin du chargement
            if not _servers_shown:
                if not _init_done.is_set():
                    _init_done.wait()
                if _init_error[0]:
                    ui.print_error(f"Erreur initialisation: {_init_error[0]}")
                    break
                if hasattr(pipeline, '_pipeline_v2'):
                    _srv_list = list(pipeline._pipeline_v2._hestia.mcp_manager.clients.keys())
                else:
                    _srv_list = list(pipeline._hestia.mcp_manager.clients.keys())
                ui.print_success(f"MCP: {', '.join(_srv_list)} ({len(_srv_list)} serveurs)")
                _servers_shown = True

            # Permettre entrée vide SEULEMENT si action en attente (pour accepter valeurs par défaut)
            # EnhancedPipeline wrappe Pipeline V2, accéder via _pipeline_v2
            session_obj = pipeline._pipeline_v2._session if hasattr(pipeline, '_pipeline_v2') else pipeline._session
            if not user_input and not session_obj.get_pending_action():
                continue

            # Effacer les notifications apres le premier message utilisateur
            task_manager.clear_notifications()

            # Commandes internes
            cmd = user_input.lower()

            if cmd in ("quit", "stop", "exit", "q"):
                msg = "Au revoir!"
                print(f"\n{msg}")
                if vocal and voice:
                    voice.speak(msg)
                break

            if cmd == "clear":
                session.clear()
                # EnhancedPipeline wrappe Pipeline V2, accéder via _pipeline_v2
                session_obj = pipeline._pipeline_v2._session if hasattr(pipeline, '_pipeline_v2') else pipeline._session
                session_obj.clear()
                ui.print_info("Session effacee.")
                continue

            if cmd in ("clearscreen", "cls"):
                ui.clear_screen()
                continue

            if cmd == "help":
                print("""
Commandes internes:
  quit, stop, exit  - Quitter Lyra
  clear             - Effacer la session
  clearscreen       - Effacer l'ecran
  mode              - Afficher le mode actif
  mode performance  - Activer le mode performance
  mode default      - Activer le mode default
  help              - Afficher cette aide
  outils            - Lister tous les outils MCP

Exemples:
  "demarre preprod-09"
  "status des VMs"
  "clone test-vm en test-vm-2"
  "qu'est-ce que vm_clone ?"
""")
                continue

            if cmd in ("outils", "tools", "liste outils"):
                # Lister tous les outils MCP via le pipeline
                result = pipeline.process("quels outils disponibles ?")
                ui.print_lyra(result.response)
                continue

            if cmd == "mode":
                ui.print_info(f"Mode actuel: {mode}")
                continue

            if cmd == "mode performance":
                mode = "performance"
                ui.print_success("Mode performance active")
                continue

            if cmd in ("mode default", "mode normal"):
                mode = "default"
                ui.print_success("Mode default active")
                continue

            # Traiter la requete via le pipeline RAG (avec callbacks progressif + RAG verbose)
            # En mode enhanced: les messages M1 remplacent l'indicateur "Reflexion en cours..."
            if not args.rag_enhanced:
                ui.print_thinking()
            result = pipeline.process(
                user_input,
                callback=on_progress,
                rag_step_callback=on_rag_step if args.rag_enhanced else None
            )
            if not args.rag_enhanced:
                ui.clear_thinking()

            # Mode DEBUG: Afficher details pipeline Enhanced
            if args.debug and args.rag_enhanced and hasattr(result, 'normalized_query'):
                print("\n" + "="*80)
                print("🔍 DEBUG - Pipeline Enhanced")
                print("="*80)

                # Étape 1: Slang Normalization
                if result.normalized_query and result.normalized_query != user_input:
                    print(f"[1] Slang Normalization:")
                    print(f"    Input:  '{user_input}'")
                    print(f"    Output: '{result.normalized_query}'")
                else:
                    print(f"[1] Slang Normalization: (inchangé)")

                # Étape 2: Synonym Expansion
                if result.expanded_query and result.expanded_query != (result.normalized_query or user_input):
                    orig_tokens = len((result.normalized_query or user_input).split())
                    exp_tokens = len(result.expanded_query.split())
                    added = exp_tokens - orig_tokens
                    print(f"[2] Synonym Expansion: +{added} tokens")
                    print(f"    '{result.expanded_query[:80]}...'")
                else:
                    print(f"[2] Synonym Expansion: (inchangé)")

                # Étape 3: RAG Retrieval
                if hasattr(result, 'rag_score') and result.rag_score is not None:
                    print(f"[3] RAG Retrieval:")
                    print(f"    Score: {result.rag_score:.3f}")
                    if hasattr(result, 'rag_source') and result.rag_source:
                        print(f"    Source: {result.rag_source}")

                # Étape 4: Confidence Cascade
                if hasattr(result, 'cascade_action') and result.cascade_action:
                    print(f"[4] Confidence Cascade:")
                    print(f"    Action: {result.cascade_action}")
                    if result.rag_score:
                        if result.rag_score > 0.85:
                            print(f"    Level: HIGH (>0.85)")
                        elif result.rag_score >= 0.60:
                            print(f"    Level: MEDIUM (0.60-0.85)")
                        else:
                            print(f"    Level: LOW (<0.60)")

                # Étape 5: Context Injection
                if hasattr(result, 'should_inject_context'):
                    if result.should_inject_context:
                        print(f"[5] Context Injection: OUI")
                    else:
                        print(f"[5] Context Injection: NON")

                # Étape 6: Tool Call Final
                if result.tool_call:
                    print(f"[6] Tool Final:")
                    print(f"    Name: {result.tool_call.get('name', 'N/A')}")
                    if result.tool_call.get('arguments'):
                        print(f"    Args: {result.tool_call['arguments']}")

                # Métriques de performance
                if hasattr(result, 'metrics') and result.metrics:
                    print(f"\n📊 Performance Metrics:")
                    total = 0
                    for key, value in result.metrics.items():
                        if '_ms' in key and isinstance(value, (int, float)):
                            print(f"    {key:25s}: {value:6.2f}ms")
                            total += value
                    if total > 0:
                        print(f"    {'TOTAL':25s}: {total:6.2f}ms")

                print("="*80 + "\n")

            # Cas 1: Question de connaissance -> reponse directe
            if result.query_type == QueryType.KNOWLEDGE:
                ui.print_lyra(result.response)
                if vocal and voice:
                    voice.speak(result.response)

            # Cas 2: Action avec args manquants -> clarification
            elif result.pending_args:
                ui.print_lyra(result.response)
                if vocal and voice:
                    voice.speak(result.response)

            # Cas 3: Action prete -> confirmation et execution
            elif result.tool_call:
                # Afficher la reponse de LYRA (confirmation)
                ui.print_lyra(result.response)
                if vocal and voice:
                    voice.speak(result.response)

                # Gerer l'execution avec confirmation
                response = handle_action(
                    pipeline, result, mode, vocal, voice,
                    task_manager=task_manager,
                    webhook_url=DISCORD_WEBHOOK_URL
                )

                # Synthese vocale du resultat
                if vocal and voice and response:
                    voice.speak(response)

            # Cas 4: Pas de match -> reponse directe
            else:
                ui.print_lyra(result.response)
                if vocal and voice:
                    voice.speak(result.response)

            # Ajouter au contexte de session
            session.add_turn(
                user_input=user_input,
                assistant_response=result.response,
                tool_call=result.tool_call
            )

        except KeyboardInterrupt:
            print("\n")
            ui.print_info("Interruption. Au revoir!")
            break
        except Exception as e:
            ui.print_error(f"Erreur: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
