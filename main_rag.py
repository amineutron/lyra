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
import random
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
from lyra.models.model_manager import ModelManager
from lyra.rag.session_memory import SessionMemory
from lyra.hestia.background_tasks import BackgroundTaskManager

# Import du module UI existant pour la compatibilite
from modules import ui
from modules.n8n import send_discord_notification
import yaml


# Dossier de logs d'erreurs MCP
ERROR_LOG_DIR = Path.home() / ".lyra" / "logs" / "errors"

# Messages LYRA pour les erreurs (ton chill et naturel)
_LYRA_ERROR_MESSAGES = [
    "ouuf... ca a plante. j'ai mis les details là :",
    "hmm ya eu un souci. j'ai tout logué ici :",
    "ca a pas marche... details dans le log :",
    "aie, erreur MCP. j'ai sauvegardé ca là :",
    "ca s'est pas passe comme prevu. log ici :",
]


def write_error_log(tool_name: str, arguments: dict, exec_result) -> Path:
    """Ecrit un log d'erreur MCP dans ~/.lyra/logs/errors/.

    Args:
        tool_name: Nom de l'outil MCP
        arguments: Arguments passes a l'outil
        exec_result: PipelineResult apres execution

    Returns:
        Path vers le fichier log cree
    """
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Nom de fichier: timestamp + tool name (sanitize)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = tool_name.replace(".", "_").replace("/", "_")
    log_path = ERROR_LOG_DIR / f"{ts}_{safe_name}.log"

    # Collecter les details d'erreur
    pipeline_error = getattr(exec_result, 'error', None) or ""
    mcp_error = ""
    mcp_output = ""
    duration_ms = ""

    exec_r = getattr(exec_result, 'execution_result', None)
    if exec_r is not None:
        mcp_error = getattr(exec_r, 'error', None) or ""
        mcp_output = getattr(exec_r, 'content', None) or ""
        duration_ms = str(getattr(exec_r, 'duration_ms', ""))

    # Formater les arguments (masquer les mots de passe eventuels)
    _SENSITIVE_KEYS = {"password", "pass", "passwd", "token", "api_key", "webhook_url",
                       "user", "username", "secret", "key", "auth", "credential"}
    args_lines = []
    for k, v in (arguments or {}).items():
        masked = "[REDACTED]" if k.lower() in _SENSITIVE_KEYS else v
        args_lines.append(f"  {k}: {masked}")
    args_str = "\n".join(args_lines) if args_lines else "  (aucun)"

    content = (
        f"=== LYRA Error Log ===\n"
        f"Date       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Tool       : {tool_name}\n"
        f"Arguments  :\n{args_str}\n"
        f"\n"
        f"--- Erreur ---\n"
        f"Pipeline   : {pipeline_error or '(aucune)'}\n"
        f"MCP Error  : {mcp_error or '(aucune)'}\n"
        f"Duree (ms) : {duration_ms or '?'}\n"
        f"\n"
        f"--- Sortie MCP ---\n"
        f"{mcp_output or '(vide)'}\n"
    )

    log_path.write_text(content, encoding="utf-8")
    return log_path


def _lyra_error_message(log_path: Path) -> str:
    """Genere un message LYRA friendly apres une erreur avec le chemin du log."""
    prefix = random.choice(_LYRA_ERROR_MESSAGES)
    return f"LYRA: {prefix}\n  {log_path}"


def _is_execution_error(exec_result) -> bool:
    """Retourne True si l'execution a produit une erreur."""
    if getattr(exec_result, 'error', None):
        return True
    er = getattr(exec_result, 'execution_result', None)
    if er is not None and not getattr(er, 'success', True):
        return True
    return False


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

    # Cas special: clone avec arret de VM
    if tool_name == "vm_clone_with_stop":
        return _handle_vm_clone_with_stop(pipeline, arguments, vocal, voice)

    # Cas special: restauration de snapshot avec securite
    if "vm_snapshot" in tool_name and arguments.get("action") == "revert":
        return _handle_snapshot_restore_with_safety(pipeline, arguments, vocal, voice)

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


def _handle_vm_clone_with_stop(
    pipeline: Pipeline,
    arguments: dict,
    vocal: bool = False,
    voice=None
) -> str:
    """Gere le clone avec arret de VM avec validations multiples.

    Sequence avec validations:
    1. Afficher le plan complet
    2. Demander confirmation avant arrêt
    3. Arreter la VM source
    4. Demander confirmation avant clone
    5. Cloner la VM
    6. Optionnellement redemarrer la VM source

    Args:
        pipeline: Pipeline RAG
        arguments: Arguments (source_vm, new_vm_name, restart_after)
        vocal: Mode vocal
        voice: VoiceInterface

    Returns:
        Message final
    """
    source_vm = arguments.get("source_vm")
    new_vm_name = arguments.get("new_vm_name")
    restart_after = arguments.get("restart_after", False)

    messages = []

    # Afficher le plan d'action complet
    print()
    ui.print_info("📋 Plan d'action:")
    print(f"  1. {ui.colored('Arrêter', ui.Colors.YELLOW)} {source_vm}")
    print(f"  2. {ui.colored('Cloner', ui.Colors.CYAN)} {source_vm} → {new_vm_name}")
    if restart_after:
        print(f"  3. {ui.colored('Redémarrer', ui.Colors.GREEN)} {source_vm}")
    else:
        print(f"  3. {ui.colored('Laisser arrêtée', ui.Colors.DIM)} {source_vm}")
    print()

    # Confirmation du plan complet
    plan_confirm = input(ui.colored("  Confirmer ce plan ? [O/n] ", ui.Colors.YELLOW)).strip().lower()
    if plan_confirm in ("n", "non", "no"):
        ui.print_warning("Plan annulé.")
        return "Plan annulé."

    # === ETAPE 1: Arrêter la VM source ===
    print()
    ui.print_info(f"Etape 1/{3 if restart_after else 2}: Arrêt de {source_vm}")

    # Afficher l'état actuel
    # EnhancedPipeline wrappe Pipeline V2
    hestia = pipeline._pipeline_v2._hestia if hasattr(pipeline, '_pipeline_v2') else pipeline._hestia
    vm_state = hestia.execute("fedora.vm_status", {"vm_name": source_vm})
    if vm_state.success:
        print(f"\n{ui.colored('État actuel:', ui.Colors.CYAN)}")
        # Afficher un extrait du status
        for line in vm_state.content.split("\n")[:5]:
            if line.strip():
                print(f"  {line}")
        print()

    # Demander confirmation avant d'arrêter
    stop_confirm = ui.confirm_action(
        tool_name="vm_stop",
        arguments={"vm_name": source_vm},
        vocal_mode=vocal,
        voice=voice
    )

    if stop_confirm == "modify":
        ui.print_warning("Modification non disponible pour cette étape.")
        stop_confirm = False

    if not stop_confirm:
        ui.print_warning(f"Arrêt de {source_vm} annulé. Clone annulé.")
        return f"Clone annulé (arrêt de {source_vm} refusé)."

    # Exécuter l'arrêt
    ui.print_info(f"Arrêt de {source_vm} en cours...")
    stop_result = get_actual_pipeline(pipeline).execute_action("vm_stop", {"vm_name": source_vm})

    if stop_result.error or not (stop_result.execution_result and stop_result.execution_result.success):
        ui.print_error(f"Echec de l'arret de {source_vm}")
        return f"Impossible d'arrêter {source_vm}: {stop_result.error}"

    ui.print_success(f"✅ {source_vm} arrêtée")
    messages.append(f"✅ {source_vm} arrêtée")

    # === ETAPE 2: Cloner la VM ===
    print()
    ui.print_info(f"Etape 2/{3 if restart_after else 2}: Clonage")

    # Afficher le récapitulatif du clone
    print(f"\n{ui.colored('📋 Récapitulatif du clonage:', ui.Colors.CYAN)}")
    print(f"  🔹 VM source     : {ui.colored(source_vm, ui.Colors.BOLD)} ({ui.colored('arrêtée ✓', ui.Colors.GREEN)})")
    print(f"  🔸 VM destination: {ui.colored(new_vm_name, ui.Colors.BOLD)}")
    print()

    # Demander confirmation avant de cloner
    clone_confirm = ui.confirm_action(
        tool_name="vm_clone",
        arguments={"source_vm": source_vm, "new_vm_name": new_vm_name},
        vocal_mode=vocal,
        voice=voice
    )

    # Gérer modification des arguments
    if clone_confirm == "modify":
        ui.print_info("Modification des parametres du clone...")
        print()
        new_new_vm_name = input(f"  new_vm_name [{new_vm_name}]: ").strip()
        if new_new_vm_name:
            new_vm_name = new_new_vm_name

        # Re-demander confirmation
        clone_confirm = ui.confirm_action(
            tool_name="vm_clone",
            arguments={"source_vm": source_vm, "new_vm_name": new_vm_name},
            vocal_mode=vocal,
            voice=voice
        )

    if not clone_confirm or clone_confirm == "modify":
        ui.print_warning("Clone annulé.")
        messages.append("❌ Clone annulé par l'utilisateur")

        # Proposer de redémarrer la source
        if restart_after:
            restart_confirm = input(ui.colored(f"\n  Redémarrer {source_vm} quand même ? [O/n] ", ui.Colors.YELLOW)).strip().lower()
            if restart_confirm not in ("n", "non", "no"):
                ui.print_info(f"Redémarrage de {source_vm}...")
                restart_result = get_actual_pipeline(pipeline).execute_action("vm_start", {"vm_name": source_vm})
                if restart_result.execution_result and restart_result.execution_result.success:
                    messages.append(f"✅ {source_vm} redémarrée")

        return "\n".join(messages)

    # Exécuter le clone
    ui.print_info(f"Clonage de {source_vm} vers {new_vm_name} en cours...")
    clone_result = get_actual_pipeline(pipeline).execute_action(
        "vm_clone",
        {"source_vm": source_vm, "new_vm_name": new_vm_name}
    )

    if clone_result.error or not (clone_result.execution_result and clone_result.execution_result.success):
        ui.print_error(f"Echec du clonage")
        messages.append(f"❌ Echec du clonage: {clone_result.error}")

        # Redémarrer la source même en cas d'échec si demandé
        if restart_after:
            ui.print_info(f"Redémarrage de {source_vm}...")
            restart_result = get_actual_pipeline(pipeline).execute_action("vm_start", {"vm_name": source_vm})
            if restart_result.execution_result and restart_result.execution_result.success:
                messages.append(f"✅ {source_vm} redémarrée")

        final_message = "\n".join(messages)
        ui.print_tool_result(final_message, success=False)
        return final_message

    ui.print_success(f"✅ Clone {new_vm_name} créé avec succès")
    messages.append(f"✅ Clone {new_vm_name} créé")

    # Envoyer notification Discord
    _send_discord_if_async("vm_clone", {"source_vm": source_vm, "new_vm_name": new_vm_name}, clone_result)

    # === ETAPE 3: Redémarrer la VM source si demandé ===
    if restart_after:
        print()
        ui.print_info(f"Etape 3/3: Redémarrage de {source_vm}")

        # Demander confirmation avant de redémarrer
        restart_confirm = input(ui.colored(f"\n  Redémarrer {source_vm} maintenant ? [O/n] ", ui.Colors.YELLOW)).strip().lower()

        if restart_confirm not in ("n", "non", "no"):
            ui.print_info(f"Redémarrage de {source_vm} en cours...")
            restart_result = get_actual_pipeline(pipeline).execute_action("vm_start", {"vm_name": source_vm})

            if restart_result.execution_result and restart_result.execution_result.success:
                ui.print_success(f"✅ {source_vm} redémarrée")
                messages.append(f"✅ {source_vm} redémarrée")
            else:
                ui.print_warning(f"Echec du redémarrage de {source_vm}")
                messages.append(f"⚠️  Echec redémarrage de {source_vm}")
        else:
            ui.print_info(f"{source_vm} reste arrêtée")
            messages.append(f"ℹ️  {source_vm} reste arrêtée")
    else:
        messages.append(f"ℹ️  {source_vm} reste arrêtée")

    final_message = "\n".join(messages)
    print()
    ui.print_tool_result(final_message, success=True)

    return final_message


def _handle_snapshot_restore_with_safety(
    pipeline,
    arguments: dict,
    vocal: bool = False,
    voice=None
) -> str:
    """Gère la restauration de snapshot avec snapshot de sécurité et validations multiples.

    Workflow:
    1. Lister les snapshots disponibles
    2. Proposer création snapshot de sécurité (recommandé)
    3. Afficher le plan complet
    4. Si VM running: arrêter
    5. Créer snapshot de sécurité (si choisi)
    6. Restaurer le snapshot
    7. Redémarrer la VM (si demandé)
    8. Notification Discord

    Args:
        pipeline: Pipeline RAG
        arguments: Arguments (vm_name, snapshot_name, create_safety_snapshot, restart_after)
        vocal: Mode vocal
        voice: VoiceInterface

    Returns:
        Message final
    """
    vm_name = arguments.get("vm_name")
    snapshot_name = arguments.get("snapshot_name")
    create_safety = arguments.get("create_safety_snapshot", None)  # None = demander
    restart_after = arguments.get("restart_after", None)  # None = demander

    messages = []

    # === ÉTAPE 0: Vérifications préalables ===
    print()
    ui.print_info("Vérifications préalables...")

    # Lister les snapshots disponibles
    # EnhancedPipeline wrappe Pipeline V2
    hestia = pipeline._pipeline_v2._hestia if hasattr(pipeline, '_pipeline_v2') else pipeline._hestia
    snapshots_result = hestia.execute("fedora.vm_snapshot", {
        "vm_name": vm_name,
        "action": "list"
    })

    if not snapshots_result.success:
        ui.print_error(f"Impossible de lister les snapshots de {vm_name}")
        return f"Erreur: {snapshots_result.error}"

    print(f"\n{ui.colored('📸 Snapshots disponibles:', ui.Colors.CYAN)}")
    print(snapshots_result.content)
    print()

    # Vérifier que le snapshot existe
    if snapshot_name not in snapshots_result.content:
        ui.print_error(f"Snapshot '{snapshot_name}' introuvable!")
        return f"Snapshot '{snapshot_name}' n'existe pas pour {vm_name}"

    # Afficher l'état actuel de la VM
    # EnhancedPipeline wrappe Pipeline V2
    hestia = pipeline._pipeline_v2._hestia if hasattr(pipeline, '_pipeline_v2') else pipeline._hestia
    vm_state_result = hestia.execute("fedora.vm_status", {"vm_name": vm_name})
    if vm_state_result.success:
        print(f"{ui.colored('État actuel de la VM:', ui.Colors.CYAN)}")
        for line in vm_state_result.content.split("\n")[:5]:
            if line.strip():
                print(f"  {line}")
        print()

    # Détecter si la VM est running
    vm_running = "en cours" in vm_state_result.content.lower() if vm_state_result.success else False

    # === ÉTAPE 1: Choix snapshot de sécurité ===
    if create_safety is None:
        print()
        print(ui.colored("⚠️  ATTENTION: La restauration va écraser l'état actuel!", ui.Colors.BG_YELLOW + ui.Colors.BLACK + ui.Colors.BOLD))
        print()
        ui.print_info("💡 Je recommande de créer un snapshot de sécurité")
        print("   pour pouvoir revenir à l'état actuel si besoin.")
        print()
        print(f"  1. {ui.colored('Créer snapshot de sécurité', ui.Colors.GREEN)} puis restaurer (recommandé)")
        print(f"  2. {ui.colored('Restaurer directement', ui.Colors.YELLOW)} (sans snapshot de sécurité)")
        print(f"  3. {ui.colored('Annuler', ui.Colors.RED)}")
        print()

        choice = input(ui.colored("  Ton choix ? (1/2/3) ", ui.Colors.YELLOW)).strip()

        if choice == "3" or choice.lower() in ("annuler", "annule", "n"):
            ui.print_warning("Restauration annulée.")
            return "Restauration annulée."

        create_safety = (choice == "1" or choice.lower() in ("oui", "o", ""))

    safety_snapshot_name = f"restore-backup-{vm_name}-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}" if create_safety else None

    # === ÉTAPE 2: Plan d'action complet ===
    print()
    ui.print_info("📋 Plan d'action:")

    step = 1
    if create_safety:
        print(f"  {step}. {ui.colored('Créer snapshot de sécurité', ui.Colors.CYAN)} «{safety_snapshot_name}»")
        step += 1

    if vm_running:
        print(f"  {step}. {ui.colored('Arrêter', ui.Colors.YELLOW)} {vm_name}")
        step += 1

    print(f"  {step}. {ui.colored('Restaurer snapshot', ui.Colors.MAGENTA)} «{snapshot_name}»")
    step += 1

    if restart_after is None:
        # Demander si redémarrage
        restart_prompt = input(ui.colored(f"  Redémarrer {vm_name} après restauration ? [O/n] ", ui.Colors.YELLOW)).strip().lower()
        restart_after = restart_prompt not in ("n", "non", "no")

    if restart_after:
        print(f"  {step}. {ui.colored('Redémarrer', ui.Colors.GREEN)} {vm_name}")

    print()

    # Confirmation du plan
    plan_confirm = input(ui.colored("  Confirmer ce plan ? [O/n] ", ui.Colors.YELLOW)).strip().lower()
    if plan_confirm in ("n", "non", "no"):
        ui.print_warning("Plan annulé.")
        return "Plan annulé."

    # === ÉTAPE 3: Créer snapshot de sécurité (si demandé) ===
    if create_safety:
        print()
        ui.print_info(f"Étape 1/{step-1}: Création snapshot de sécurité")

        # Demander confirmation
        safety_confirm = ui.confirm_action(
            tool_name="vm_snapshot",
            arguments={"vm_name": vm_name, "action": "create", "snapshot_name": safety_snapshot_name},
            vocal_mode=vocal,
            voice=voice
        )

        if safety_confirm == "modify":
            ui.print_warning("Modification non disponible pour cette étape.")
            safety_confirm = False

        if not safety_confirm:
            ui.print_warning("Snapshot de sécurité annulé. Restauration annulée.")
            return "Restauration annulée (snapshot de sécurité refusé)."

        # Créer le snapshot de sécurité
        ui.print_info(f"Création de '{safety_snapshot_name}' en cours...")
        safety_result = get_actual_pipeline(pipeline).execute_action("fedora.vm_snapshot", {
            "vm_name": vm_name,
            "action": "create",
            "snapshot_name": safety_snapshot_name,
            "description": f"Snapshot de sécurité avant restauration de '{snapshot_name}'"
        })

        if safety_result.error or not (safety_result.execution_result and safety_result.execution_result.success):
            ui.print_error("Échec de la création du snapshot de sécurité")
            return f"Impossible de créer le snapshot de sécurité: {safety_result.error}"

        ui.print_success(f"✅ Snapshot de sécurité '{safety_snapshot_name}' créé")
        messages.append(f"✅ Snapshot de sécurité créé")

    # === ÉTAPE 4: Arrêter la VM (si running) ===
    if vm_running:
        print()
        current_step = 2 if create_safety else 1
        ui.print_info(f"Étape {current_step}/{step-1}: Arrêt de {vm_name}")

        stop_confirm = ui.confirm_action(
            tool_name="vm_stop",
            arguments={"vm_name": vm_name},
            vocal_mode=vocal,
            voice=voice
        )

        if stop_confirm == "modify":
            ui.print_warning("Modification non disponible.")
            stop_confirm = False

        if not stop_confirm:
            ui.print_warning(f"Arrêt de {vm_name} annulé.")
            return "Restauration annulée (arrêt refusé)."

        ui.print_info(f"Arrêt de {vm_name} en cours...")
        stop_result = get_actual_pipeline(pipeline).execute_action("fedora.vm_stop", {"vm_name": vm_name})

        if stop_result.error or not (stop_result.execution_result and stop_result.execution_result.success):
            ui.print_error(f"Échec de l'arrêt de {vm_name}")
            return f"Impossible d'arrêter {vm_name}: {stop_result.error}"

        ui.print_success(f"✅ {vm_name} arrêtée")
        messages.append(f"✅ {vm_name} arrêtée")

    # === ÉTAPE 5: Restaurer le snapshot ===
    print()
    restore_step = (2 if create_safety else 1) + (1 if vm_running else 0)
    ui.print_info(f"Étape {restore_step}/{step-1}: Restauration snapshot '{snapshot_name}'")

    print(f"\n{ui.colored('⚠️  ATTENTION:', ui.Colors.YELLOW)} Cette action va remplacer l'état actuel de {vm_name}")
    print(f"   par l'état du snapshot '{snapshot_name}'.\n")

    restore_confirm = ui.confirm_action(
        tool_name="vm_snapshot",
        arguments={"vm_name": vm_name, "action": "revert", "snapshot_name": snapshot_name},
        vocal_mode=vocal,
        voice=voice
    )

    if restore_confirm == "modify":
        ui.print_warning("Modification non disponible.")
        restore_confirm = False

    if not restore_confirm:
        ui.print_warning("Restauration annulée.")

        # Proposer de redémarrer la VM si on l'a arrêtée
        if vm_running:
            restart_anyway = input(ui.colored(f"\n  Redémarrer {vm_name} quand même ? [O/n] ", ui.Colors.YELLOW)).strip().lower()
            if restart_anyway not in ("n", "non", "no"):
                ui.print_info(f"Redémarrage de {vm_name}...")
                restart_result = get_actual_pipeline(pipeline).execute_action("fedora.vm_start", {"vm_name": vm_name})
                if restart_result.execution_result and restart_result.execution_result.success:
                    messages.append(f"✅ {vm_name} redémarrée")

        return "\n".join(messages + ["⚠️  Restauration annulée"])

    # Exécuter la restauration
    ui.print_info(f"Restauration du snapshot '{snapshot_name}' en cours...")
    restore_result = get_actual_pipeline(pipeline).execute_action("fedora.vm_snapshot", {
        "vm_name": vm_name,
        "action": "revert",
        "snapshot_name": snapshot_name
    })

    if restore_result.error or not (restore_result.execution_result and restore_result.execution_result.success):
        ui.print_error("Échec de la restauration")
        messages.append(f"❌ Échec de la restauration: {restore_result.error}")

        # Si échec ET on a créé un snapshot de sécurité, proposer de le restaurer
        if create_safety:
            ui.print_warning(f"\n💡 Tu peux restaurer le snapshot de sécurité '{safety_snapshot_name}'")
            ui.print_warning("   pour revenir à l'état avant cette tentative de restauration.")

        return "\n".join(messages)

    ui.print_success(f"✅ Snapshot '{snapshot_name}' restauré")
    messages.append(f"✅ Snapshot '{snapshot_name}' restauré")

    # Envoyer notification Discord
    _send_discord_if_async("vm_snapshot", {
        "vm_name": vm_name,
        "action": "revert",
        "snapshot_name": snapshot_name,
        "safety_snapshot": safety_snapshot_name
    }, restore_result)

    # === ÉTAPE 6: Redémarrer la VM (si demandé) ===
    if restart_after:
        print()
        final_step = step - 1
        ui.print_info(f"Étape {final_step}/{final_step}: Redémarrage de {vm_name}")

        restart_confirm = input(ui.colored(f"\n  Redémarrer {vm_name} maintenant ? [O/n] ", ui.Colors.YELLOW)).strip().lower()

        if restart_confirm not in ("n", "non", "no"):
            ui.print_info(f"Redémarrage de {vm_name} en cours...")
            restart_result = get_actual_pipeline(pipeline).execute_action("fedora.vm_start", {"vm_name": vm_name})

            if restart_result.execution_result and restart_result.execution_result.success:
                ui.print_success(f"✅ {vm_name} redémarrée")
                messages.append(f"✅ {vm_name} redémarrée")
            else:
                ui.print_warning(f"Échec du redémarrage de {vm_name}")
                messages.append(f"⚠️  Échec redémarrage de {vm_name}")
        else:
            ui.print_info(f"{vm_name} reste arrêtée")
            messages.append(f"ℹ️  {vm_name} reste arrêtée")
    else:
        messages.append(f"ℹ️  {vm_name} reste arrêtée")

    # Résumé final
    final_message = "\n".join(messages)
    print()
    ui.print_tool_result(final_message, success=True)

    return final_message


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
        ui.print_warning(f"Config Discord non chargee: {e}")

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
                user_input = ui.live_input(">>> ", task_manager, loading=_loading).strip()

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
