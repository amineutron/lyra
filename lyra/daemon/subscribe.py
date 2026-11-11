"""
Lyra Daemon - Abonnes passifs (capsule) : diffusion des etats de session.

Un client envoie `subscribe` ; il recoit ensuite des evenements `state`
additifs, UN par changement d'etat (jamais en continu). Il ne recoit JAMAIS le
contenu des reponses ni les arguments des outils : seulement l'etat, un
libelle court (nom d'outil nettoye) et le `display` deja emis par la
confirmation.

Robustesse :
- cout nul sans abonne (publish_state / open_ask rendent immediatement) ;
- un abonne = une file bornee + un thread d'ecriture : un abonne lent ne
  bloque ni le pipeline ni les autres, il est ABANDONNE (socket coupe) si sa
  file est pleine ;
- nombre d'abonnes plafonne (MAX_SUBSCRIBERS) ;
- une connexion abonnee est restreinte (voir server.py) : ping, unsubscribe,
  answer. Un abonne ne peut declencher aucune action.

Reponses d'un abonne : un `answer` ne vaut QUE pour une confirmation qui lui a
ete diffusee (ask_id), tranchee une seule fois (premier arrive). La valeur est
filtree par external_answer() puis revalidee par translate_confirm_answer :
jamais plus permissif que le clic existant, et strictement plus prudent pour
le texte (un abonne ne confirme jamais une action dangereuse).
"""

from __future__ import annotations

import logging
import queue
import secrets
import threading
import time
from typing import Any, Optional

from .display import _clean, parse_slider_answer, resolve_display_answer
from .protocol import ChannelClosed, LineChannel

logger = logging.getLogger(__name__)

MAX_SUBSCRIBERS = 8
QUEUE_SIZE = 32
MAX_LABEL = 60
MAX_SESSION = 64
STATES = frozenset({"idle", "thinking", "speaking", "confirm", "ok", "error"})
_YES = frozenset({"o", "oui", "y", "yes"})
_NO = frozenset({"n", "non", "no"})
_MAX_SESSIONS_TRACKED = 256


def _short_label(tool: Optional[str]) -> Optional[str]:
    if not isinstance(tool, str) or not tool:
        return None
    return _clean(tool.split(".")[-1], MAX_LABEL) or None


def external_answer(display: Optional[dict], danger: bool, value: Any,
                    control: Any = None) -> str:
    """Filtre la reponse d'un abonne ; rend une valeur a passer a translate_confirm_answer.

    - curseur : `control {id, value}` entier strict -> "id=valeur" (le format
      `id=valeur` historique) ; control illisible -> refus ;
    - "o/oui/y/yes" : confirme seulement une action NON dangereuse (danger -> "n") ;
    - "n/non/no" : refus ;
    - id propose par le display ou "id=entier" valide : transmis tel quel
      (translate_confirm_answer applique ses propres regles) ;
    - tout le reste (vide, "m", texte libre) : refus. Pas d'Entree-vaut-oui,
      pas de correction "m" : elles passent par le client demandeur.
    """
    if control is not None:
        if not isinstance(control, dict):
            return "n"
        cid, cval = control.get("id"), control.get("value")
        if not isinstance(cid, str) or isinstance(cval, bool) or not isinstance(cval, int):
            return "n"
        candidate = f"{cid}={cval}"
        return candidate if parse_slider_answer(display, candidate) is not None else "n"
    if not isinstance(value, str) or len(value) > 64:
        return "n"
    low = value.strip().lower()
    if low in _YES:
        return "n" if danger else "o"
    if low in _NO:
        return "n"
    if parse_slider_answer(display, value) is not None \
            or resolve_display_answer(display, value) is not None:
        return value
    return "n"


class PendingAsk:
    """Une confirmation diffusee, tranchable une seule fois par un abonne."""

    def __init__(self, ask_id: str, session: str, danger: bool,
                 display: Optional[dict], recipients: set[int]):
        self.ask_id = ask_id
        self.session = session
        self.danger = danger
        self.display = display
        self.recipients = recipients
        self.event = threading.Event()
        self._lock = threading.Lock()
        self._value: Optional[str] = None
        self.source = "client"

    def offer(self, value: str, source: str = "subscriber") -> bool:
        """Premier arrive gagne ; False si deja tranchee."""
        with self._lock:
            if self._value is not None:
                return False
            self._value = value
            self.source = source
        self.event.set()
        return True

    @property
    def value(self) -> Optional[str]:
        return self._value


class _Subscriber:
    def __init__(self, channel: LineChannel):
        self.channel = channel
        self.queue: queue.Queue = queue.Queue(maxsize=QUEUE_SIZE)
        self.asks: list[str] = []          # ask_id diffuses, du plus ancien au plus recent
        self.thread = threading.Thread(target=self._run, daemon=True, name="lyra-subscriber")
        self.hub: Optional[StateHub] = None

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                return
            try:
                self.channel.send(item)
            except ChannelClosed:
                if self.hub is not None:
                    self.hub._drop(self, "connexion fermee")
                return


class StateHub:
    """Registre des abonnes et des confirmations en attente."""

    def __init__(self, max_subscribers: int = MAX_SUBSCRIBERS):
        self._max = max_subscribers
        self._lock = threading.Lock()
        self._subs: dict[int, _Subscriber] = {}     # cle : id(channel)
        self._asks: dict[str, PendingAsk] = {}
        self._last: dict[str, tuple] = {}

    @property
    def active(self) -> bool:
        return bool(self._subs)

    # -- abonnes -----------------------------------------------------------

    def subscribe(self, channel: LineChannel, ack: dict) -> bool:
        """Abonne le canal ; `ack` est le PREMIER message qu'il recevra. False si plein."""
        with self._lock:
            if id(channel) in self._subs:
                return True
            if len(self._subs) >= self._max:
                return False
            sub = _Subscriber(channel)
            sub.hub = self
            sub.queue.put_nowait(ack)
            self._subs[id(channel)] = sub
        sub.thread.start()
        return True

    def unsubscribe(self, channel: LineChannel) -> bool:
        with self._lock:
            sub = self._subs.pop(id(channel), None)
        if sub is None:
            return False
        self._stop(sub)
        return True

    def subscriber_count(self) -> int:
        return len(self._subs)

    @staticmethod
    def _stop(sub: _Subscriber) -> None:
        try:
            sub.queue.put_nowait(None)
        except queue.Full:
            pass

    def _drop(self, sub: _Subscriber, why: str) -> None:
        """Abandonne un abonne (lent ou parti) : retire, coupe le socket."""
        with self._lock:
            self._subs.pop(id(sub.channel), None)
        logger.info("abonne retire (%s)", why)
        try:
            sub.channel.abort()
        except Exception:  # noqa: BLE001
            pass
        # vide la file pour que le thread d'ecriture sorte
        try:
            while True:
                sub.queue.get_nowait()
        except queue.Empty:
            pass
        self._stop(sub)

    def _broadcast(self, message: dict, only: Optional[set[int]] = None) -> set[int]:
        with self._lock:
            targets = [s for k, s in self._subs.items() if only is None or k in only]
        reached: set[int] = set()
        for sub in targets:
            try:
                sub.queue.put_nowait(message)
                reached.add(id(sub.channel))
            except queue.Full:
                self._drop(sub, "file pleine")
        return reached

    # -- etats -------------------------------------------------------------

    def publish_state(self, session: str, state: str, label: Optional[str] = None,
                      **extra: Any) -> None:
        """Diffuse un changement d'etat (ignore si identique au precedent de la session)."""
        if not self._subs or state not in STATES:
            return
        session = _clean(session, MAX_SESSION) or "default"
        label = _short_label(label)
        key = (state, label, extra.get("ask_id"))
        with self._lock:
            if self._last.get(session) == key:
                return
            if len(self._last) >= _MAX_SESSIONS_TRACKED:
                self._last.clear()
            self._last[session] = key
        message: dict = {"type": "state", "state": state, "session": session,
                         "ts": round(time.time(), 3)}
        if label:
            message["label"] = label
        message.update(extra)
        self._broadcast(message)

    # -- confirmations ------------------------------------------------------

    def open_ask(self, session: str, tool: str, danger: bool,
                 display: Optional[dict]) -> Optional[PendingAsk]:
        """Diffuse une confirmation aux abonnes ; None si personne n'ecoute."""
        if not self._subs:
            return None
        session = _clean(session, MAX_SESSION) or "default"
        ask_id = secrets.token_hex(8)
        extra: dict = {"ask_id": ask_id, "danger": bool(danger)}
        if display is not None:
            extra["display"] = display
        with self._lock:
            recipients = set(self._subs)
        pending = PendingAsk(ask_id, session, bool(danger), display, recipients)
        with self._lock:
            self._asks[ask_id] = pending
        message = {"type": "state", "state": "confirm", "session": session,
                   "ts": round(time.time(), 3), **extra}
        label = _short_label(tool)
        if label:
            message["label"] = label
        reached = self._broadcast(message, recipients)
        with self._lock:
            pending.recipients = reached
            self._last[session] = ("confirm", label, ask_id)
            for key in reached:
                sub = self._subs.get(key)
                if sub is not None:
                    sub.asks.append(ask_id)
        return pending

    def answer_from(self, channel: LineChannel, message: dict) -> Optional[str]:
        """Reponse d'un abonne. Rend None si prise en compte, sinon un code d'erreur.

        Codes : "forbidden" (pas abonne, ou ask non diffuse a ce canal),
        "stale" (aucune confirmation en attente / deja tranchee).
        """
        with self._lock:
            sub = self._subs.get(id(channel))
            if sub is None:
                return "forbidden"
            ask_id = message.get("ask_id")
            if ask_id is None:
                ask_id = sub.asks[-1] if sub.asks else None   # pont actuel : sans ask_id
            elif not isinstance(ask_id, str) or ask_id not in sub.asks:
                return "forbidden" if ask_id in self._asks else "stale"
            pending = self._asks.get(ask_id) if ask_id else None
        if pending is None:
            return "stale"
        value = external_answer(pending.display, pending.danger,
                                message.get("value"), message.get("control"))
        return None if pending.offer(value) else "stale"

    def close_ask(self, pending: PendingAsk, verdict: str, source: str) -> None:
        """Retire la confirmation et diffuse `answer_ack` (verdict "o" ou "n")."""
        with self._lock:
            self._asks.pop(pending.ask_id, None)
            for sub in self._subs.values():
                if pending.ask_id in sub.asks:
                    sub.asks.remove(pending.ask_id)
        self._broadcast({"type": "answer_ack", "session": pending.session,
                         "ask_id": pending.ask_id, "value": verdict,
                         "source": source, "ts": round(time.time(), 3)})
