"""
Lyra Daemon - UI distante.

Serialise la surface UIContext (9 callables, cf. lyra/core/workflows/context.py)
vers le client via le protocole : 7 sorties unidirectionnelles ("output"),
2 interactions bloquantes ("ask" -> attente d'un "answer").

Le code metier (workflows vm_clone_exec / vm_snapshot_exec) recoit un
UIContext construit ici et n'a AUCUNE idee qu'il parle a un socket.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..core.workflows.context import UIContext
from .display import build_display, translate_confirm_answer
from .protocol import ASK_TIMEOUT, ChannelClosed, LineChannel

logger = logging.getLogger(__name__)


class RequestCancelled(Exception):
    """Le client a annule (deconnexion ou refus) pendant une interaction."""



def build_confirm_prompt(tool_name: str, arguments: dict,
                         danger: bool | None = None) -> tuple[str, bool]:
    """Prompt de confirmation explicite : quel outil, sur quoi.

    Les actions destructives (DANGEROUS_TOOLS) sont mises en avant sans
    ambiguite — "Je vais executer X. Tu confirmes ?" ressemblait a une
    commande basique (retour utilisateur 2026-08-14).

    `danger` : verdict deja calcule par l'appelant (annotation destructiveHint du
    serveur comprise, voir actions._outil_dangereux). Il ne peut que durcir le
    prompt, jamais l'assouplir pour un outil des listes statiques.
    """
    from ..core.constants import DANGEROUS_TOOLS, DESTRUCTIVE_TOOLS

    short = tool_name.split(".")[-1]
    args_txt = ", ".join(f"{k}={v}" for k, v in list(arguments.items())[:3])
    target = f" ({args_txt})" if args_txt else ""
    if short in DESTRUCTIVE_TOOLS:
        return (f"!! ACTION DESTRUCTIVE !! {tool_name}{target} — "
                f"operation irreversible. Confirmer ?", True)
    if danger is True and short not in DANGEROUS_TOOLS:
        return (f"!! ACTION DESTRUCTIVE !! {tool_name}{target} — "
                f"operation declaree destructive par son serveur. Confirmer ?", True)
    danger = short in DANGEROUS_TOOLS
    if danger:
        return (f"! ACTION SENSIBLE ! {tool_name}{target} — "
                f"operation importante (rien n'est detruit). Confirmer ?", True)
    return (f"Executer {tool_name}{target} ?", False)

def build_confirm_payload(tool_name: str, arguments: dict, danger: bool,
                          state: Optional[dict] = None) -> dict:
    """Payload d'un `ask` de kind confirm, avec `display` si l'outil s'y prete.

    `display` est additif (les clients existants l'ignorent) et purement
    decoratif : un echec de sa construction ne doit jamais bloquer la
    confirmation.
    """
    payload = {"tool": tool_name, "arguments": arguments, "danger": danger}
    try:
        display = build_display(tool_name, arguments, state)
    except Exception:
        logger.warning("build_display a echoue pour %s", tool_name, exc_info=True)
        display = None
    if display is not None:
        payload["display"] = display
    return payload


class RemoteUI:
    """Traduit les appels UI en messages protocole sur un canal."""

    def __init__(self, channel: LineChannel, recorder: Any = None,
                 state_provider: Any = None):
        self._channel = channel
        # state_provider(tool, arguments) -> dict | None : etat reel pour le display
        self._state_provider = state_provider
        # recorder (history.Recorder) : note l'outil et le verdict pour le journal
        self._recorder = recorder

    # -- Sorties unidirectionnelles ------------------------------------

    def _output(self, kind: str, text: str = "", **extra) -> None:
        self._channel.send({"type": "output", "kind": kind, "text": text, **extra})

    def info(self, text: str) -> None:
        self._output("info", text)

    def success(self, text: str) -> None:
        self._output("success", text)

    def warning(self, text: str) -> None:
        self._output("warning", text)

    def note_tool(self, tool_name: str) -> None:
        """Retient l'outil choisi pour le journal (rien n'est envoye au client)."""
        if self._recorder is not None:
            self._recorder.tool_call(tool_name)

    def error(self, text: str) -> None:
        if self._recorder is not None:
            self._recorder.error(text)
        self._output("error", text)

    def lyra(self, text: str) -> None:
        self._output("lyra", text)

    def lyra_tag(self, text: str) -> None:
        self._output("lyra_tag", text)

    def println(self, text: str = "") -> None:
        self._output("plain", str(text))

    def tool_call(self, tool_name: str, arguments: dict,
                  vm_state: Optional[dict] = None) -> None:
        if self._recorder is not None:
            self._recorder.tool_call(tool_name)
        self._output("tool_call", tool=tool_name, arguments=arguments,
                     vm_state=vm_state)

    def tool_result(self, text: str, success: bool = True,
                    raw_error: Optional[str] = None) -> None:
        if self._recorder is not None:
            self._recorder.tool_result(success, raw_error)
        self._output("tool_result", text, success=success, raw_error=raw_error)

    def progress(self, step: str, data: dict) -> None:
        self._channel.send({"type": "progress", "step": step, "data": data})

    def set_state_provider(self, provider: Any) -> None:
        self._state_provider = provider

    def _display_state(self, tool_name: str, arguments: dict) -> Optional[dict]:
        provider = getattr(self, "_state_provider", None)
        if provider is None:
            return None
        try:
            state = provider(tool_name, arguments)
        except Exception:  # noqa: BLE001 - l'etat est decoratif
            logger.warning("etat indisponible pour %s", tool_name, exc_info=True)
            return None
        return state if isinstance(state, dict) else None

    # -- Interactions bloquantes ----------------------------------------

    def ask_confirm(self, tool_name: str, arguments: dict, prompt: str,
                    danger: bool) -> tuple[str, dict]:
        """ask confirm avec display ; rend (reponse minuscule, arguments effectifs).

        Le clic est valide contre le display emis pour CETTE confirmation
        (voir display.translate_confirm_answer) ; les arguments effectifs ne
        different des arguments d'origine que pour un curseur valide.
        """
        payload = build_confirm_payload(
            tool_name, arguments, danger,
            self._display_state(tool_name, arguments))
        raw = self.ask("confirm", prompt, payload)
        answer, effective = translate_confirm_answer(
            payload.get("display"), raw, tool_name, arguments, danger)
        return answer.lower(), effective

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
                       vocal_mode: bool = False, voice: Any = None,
                       danger: bool | None = None):
        """Equivalent distant de ui.confirm_action : True | False | "modify".

        Le client rend le prompt [O/n/m] comme il veut (clavier ou vocal) et
        renvoie la reponse brute ; l'interpretation reste ici, identique au
        comportement historique. `danger` : voir build_confirm_prompt.
        """
        prompt, danger = build_confirm_prompt(tool_name, arguments, danger)
        answer, effective = self.ask_confirm(tool_name, arguments, prompt, danger)
        if effective != arguments:
            # ce chemin ne peut pas appliquer une valeur de curseur : pas de oui
            return False
        if answer in ("m", "modify", "modifier"):
            return "modify"
        # Une action sensible exige un "oui" explicite : Entree ne suffit pas
        # (parite avec actions.py ; audit 2026-09-19).
        if danger:
            return answer in ("o", "oui", "y", "yes")
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
