"""
Lyra Daemon - UI distante.

Serialise la surface UIContext (9 callables, cf. lyra/core/workflows/context.py)
vers le client via le protocole : 7 sorties unidirectionnelles ("output"),
2 interactions bloquantes ("ask" -> attente d'un "answer").

Le code metier (workflows vm_clone_exec / vm_snapshot_exec) recoit un
UIContext construit ici et n'a AUCUNE idee qu'il parle a un socket.
"""

from __future__ import annotations

from typing import Any, Optional

from ..core.workflows.context import UIContext
from .protocol import ASK_TIMEOUT, ChannelClosed, LineChannel


class RequestCancelled(Exception):
    """Le client a annule (deconnexion ou refus) pendant une interaction."""



def build_confirm_prompt(tool_name: str, arguments: dict) -> tuple[str, bool]:
    """Prompt de confirmation explicite : quel outil, sur quoi.

    Les actions destructives (DANGEROUS_TOOLS) sont mises en avant sans
    ambiguite — "Je vais executer X. Tu confirmes ?" ressemblait a une
    commande basique (retour utilisateur 2026-08-14).
    """
    from ..core.constants import DANGEROUS_TOOLS, DESTRUCTIVE_TOOLS

    short = tool_name.split(".")[-1]
    danger = short in DANGEROUS_TOOLS
    args_txt = ", ".join(f"{k}={v}" for k, v in list(arguments.items())[:3])
    target = f" ({args_txt})" if args_txt else ""
    if short in DESTRUCTIVE_TOOLS:
        return (f"!! ACTION DESTRUCTIVE !! {tool_name}{target} — "
                f"operation irreversible. Confirmer ?", True)
    if danger:
        return (f"! ACTION SENSIBLE ! {tool_name}{target} — "
                f"operation importante (rien n'est detruit). Confirmer ?", True)
    return (f"Executer {tool_name}{target} ?", False)

class RemoteUI:
    """Traduit les appels UI en messages protocole sur un canal."""

    def __init__(self, channel: LineChannel):
        self._channel = channel

    # -- Sorties unidirectionnelles ------------------------------------

    def _output(self, kind: str, text: str = "", **extra) -> None:
        self._channel.send({"type": "output", "kind": kind, "text": text, **extra})

    def info(self, text: str) -> None:
        self._output("info", text)

    def success(self, text: str) -> None:
        self._output("success", text)

    def warning(self, text: str) -> None:
        self._output("warning", text)

    def error(self, text: str) -> None:
        self._output("error", text)

    def lyra(self, text: str) -> None:
        self._output("lyra", text)

    def lyra_tag(self, text: str) -> None:
        self._output("lyra_tag", text)

    def println(self, text: str = "") -> None:
        self._output("plain", str(text))

    def tool_call(self, tool_name: str, arguments: dict,
                  vm_state: Optional[dict] = None) -> None:
        self._output("tool_call", tool=tool_name, arguments=arguments,
                     vm_state=vm_state)

    def tool_result(self, text: str, success: bool = True,
                    raw_error: Optional[str] = None) -> None:
        self._output("tool_result", text, success=success, raw_error=raw_error)

    def progress(self, step: str, data: dict) -> None:
        self._channel.send({"type": "progress", "step": step, "data": data})

    # -- Interactions bloquantes ----------------------------------------

    def ask(self, kind: str, prompt: str, payload: Optional[dict] = None) -> str:
        """Envoie un ask et attend la reponse texte du client."""
        self._channel.send({"type": "ask", "kind": kind, "prompt": prompt,
                            "payload": payload or {}})
        try:
            message = self._channel.recv(timeout=ASK_TIMEOUT)
        except (ChannelClosed, TimeoutError) as e:
            raise RequestCancelled(f"client injoignable pendant un ask: {e}") from e
        if message.get("type") == "cancel":
            raise RequestCancelled("annule par le client")
        if message.get("type") != "answer":
            raise RequestCancelled(f"reponse inattendue: {message.get('type')}")
        return str(message.get("value", "")).strip()

    def ask_input(self, prompt: str = "") -> str:
        return self.ask("input", prompt)

    def confirm_action(self, tool_name: str, arguments: dict,
                       vocal_mode: bool = False, voice: Any = None):
        """Equivalent distant de ui.confirm_action : True | False | "modify".

        Le client rend le prompt [O/n/m] comme il veut (clavier ou vocal) et
        renvoie la reponse brute ; l'interpretation reste ici, identique au
        comportement historique.
        """
        prompt, danger = build_confirm_prompt(tool_name, arguments)
        answer = self.ask("confirm", prompt,
                          {"tool": tool_name, "arguments": arguments,
                           "danger": danger}).lower()
        if answer in ("m", "modify", "modifier"):
            return "modify"
        return answer in ("", "o", "oui", "y", "yes")

    # -- Construction du UIContext pour les workflows metier -------------

    def uic(self) -> UIContext:
        return UIContext(
            print_info=self.info,
            print_success=self.success,
            print_error=self.error,
            print_warning=self.warning,
            print_tool_result=self.tool_result,
            colored=lambda text, color: text,  # les couleurs sont cote client
            confirm_action=self.confirm_action,
            ask_input=self.ask_input,
            println=self.println,
        )
