"""
Lyra Daemon - Intention implicite ("ok vasy" reprend la derniere action proposee).

Fonctionnement :
- remember_from_reply() : apres une reponse de Lyra qui PROPOSE une action
  ("je peux lancer la scene soiree"), memorise cette action dans la session
  (Suggestion immuable).
- resolve_implicit() : au debut d'une requete, si la phrase est un simple
  assentiment ET qu'une proposition recente existe, rend l'analyse a rejouer.
  Sinon None : le comportement est exactement celui d'avant.

Securite : la proposition ne fait que remplacer la phrase de l'utilisateur ;
l'appelant la soumet au flux normal (affichage de l'action, confirmation, outils
dangereux jamais auto-confirmes). Une proposition sert une seule fois.

Expiration : MAX_REQUESTS requetes ou MAX_AGE_S secondes, le premier atteint.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..models._analysis import EphaistosAnalysis
from ..rag.session_memory import Suggestion
from ..rules.implicit import extract_proposal, is_affirmation

logger = logging.getLogger("lyra.daemon.implicit")

MAX_REQUESTS = 2     # l'assentiment doit venir dans les 2 requetes qui suivent
MAX_AGE_S = 120.0


def _session(v2):
    return getattr(v2, "_session", None)


def is_live(suggestion: Suggestion, request_no: int, now: float) -> bool:
    """Proposition encore valable : pas trop de requetes ni de temps ecoules."""
    return (request_no - suggestion.request_no <= MAX_REQUESTS
            and 0 <= now - suggestion.created_at <= MAX_AGE_S)


def resolve_implicit(v2, session_id: str, text: str,
                     now: Optional[float] = None) -> Optional[EphaistosAnalysis]:
    """Analyse a rejouer si `text` est un assentiment et qu'une proposition vit."""
    now = time.time() if now is None else now
    with v2.session_scope(session_id):
        session = _session(v2)
        if session is None:
            return None
        request_no = session.note_request()
        suggestion = session.get_suggestion()
        # Une question ou un choix en attente recoit "ok" en priorite (pipeline).
        if session.get_pending_action() or session.get_pending_choice():
            return None
        if suggestion is None or not is_affirmation(text):
            return None
        session.clear_suggestion()          # usage unique, meme si perimee
        if not is_live(suggestion, request_no, now):
            return None
        return EphaistosAnalysis(
            tool=suggestion.tool, arguments=dict(suggestion.arguments),
            missing_args=list(suggestion.missing_args), confidence=0.9,
            reasoning=f"implicit: assentiment apres proposition ({suggestion.source})",
            raw_response="")


def remember_from_reply(v2, session_id: str, reply: str,
                        now: Optional[float] = None) -> bool:
    """Memorise l'action proposee par `reply`, si une seule est reconnue."""
    try:
        analysis = extract_proposal(reply)
        with v2.session_scope(session_id):
            session = _session(v2)
            if session is None:
                return False
            if analysis is None:
                return False
            session.set_suggestion(Suggestion(
                tool=analysis.tool,
                arguments=tuple(sorted(analysis.arguments.items())),
                missing_args=tuple(analysis.missing_args or ()),
                request_no=session._request_count,
                created_at=time.time() if now is None else now,
                source=str(reply)[:80]))
            return True
    except Exception as e:  # noqa: BLE001 - facultatif, ne doit jamais casser une requete
        logger.warning("memorisation de proposition impossible: %s", e)
        return False


def forget(v2, session_id: str) -> None:
    """Oublie la proposition (une action vient d'etre traitee autrement)."""
    with v2.session_scope(session_id):
        session = _session(v2)
        if session is not None:
            session.clear_suggestion()
