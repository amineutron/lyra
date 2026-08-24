"""
Lyra Client - Rendu terminal des messages du protocole.

Reutilise modules/ui.py (stdlib pur, demarrage instantane) pour un rendu
identique au mode historique : memes panneaux, memes couleurs.
"""

from __future__ import annotations

import sys
from typing import Optional

from modules import ui


def render_output(message: dict) -> None:
    """Affiche un message {"type": "output", ...}."""
    kind = message.get("kind", "plain")
    text = message.get("text", "")
    if kind == "info":
        ui.print_info(text)
    elif kind == "success":
        ui.print_success(text)
    elif kind == "warning":
        ui.print_warning(text)
    elif kind == "error":
        print(f"\n{ui.Colors.RED}{text}{ui.Colors.RESET}")
    elif kind == "lyra":
        ui.print_lyra(text)
    elif kind == "lyra_tag":
        ui.print_lyra_tag(text)
    elif kind == "tool_call":
        ui.print_tool_call(message.get("tool", "?"),
                           message.get("arguments", {}),
                           message.get("vm_state"))
    elif kind == "tool_result":
        ui.print_tool_result(text, success=message.get("success", True),
                             raw_error=message.get("raw_error"))
    else:  # plain
        print(text)


def render_progress(message: dict, verbose: bool = False) -> None:
    """Affiche un message {"type": "progress", ...} (verbose uniquement)."""
    if not verbose:
        return
    step = message.get("step", "")
    data = message.get("data", {})
    if step == "acknowledgement":
        print(f"  {ui.Colors.CYAN}[lyra] {data.get('message', '')}{ui.Colors.RESET}",
              flush=True)
        return
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
        print(f"  {color}[rag] {tool} score={score_str} ({level}){ui.Colors.RESET}",
              flush=True)
    else:
        tool = data.get("tool", "") or data.get("server", "")
        if tool:
            score_str = f"{score:.2f}" if score else "?"
            print(f"  {color}[rag] {step}: {tool} score={score_str}"
                  f"{ui.Colors.RESET}", flush=True)


def answer_ask(message: dict) -> Optional[str]:
    """Affiche un ask et lit la reponse clavier.

    Returns:
        La reponse, ou None si l'utilisateur a annule (Ctrl+C / EOF).
    """
    kind = message.get("kind", "input")
    prompt = message.get("prompt", "")
    payload = message.get("payload", {})

    if kind == "confirm":
        if payload.get("dangerous"):
            sys.stdout.write(f"\n{ui.Colors.RED}{prompt}{ui.Colors.RESET} ")
        else:
            tag = f"{ui.Colors.BG_ORANGE}{ui.Colors.FG_DARK} Lyra {ui.Colors.RESET}"
            sys.stdout.write(f"\n{tag} {prompt} ")
        sys.stdout.flush()
        try:
            return input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

    # kind == "input" : question libre d'un workflow
    try:
        return input(f"{prompt} ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None
