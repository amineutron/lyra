"""
Lyra Core - Workflow vm_stop_choice.

Traite le choix d'arret de VM avant clone (arret+redemarrage ou arret seul).
Fait partie du workflow vm_clone lorsque la VM source est en cours.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..types import QueryType, PipelineResult
from ...rag.session_memory import META_COW_CHOICE_PENDING

if TYPE_CHECKING:
    from ...rag.session_memory import PendingAction
    from .context import WorkflowContext


def handle_vm_stop_choice(
    query: str, pending: "PendingAction", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Gere le choix d'arret de VM avant clone.

    Args:
        query:   Reponse utilisateur (1/2/3 ou texte)
        pending: Action en attente avec source_vm, new_vm_name
        ctx:     Contexte workflow
    """
    choice = query.strip()
    source_vm = pending.known_args.get("source_vm")
    new_vm_name = pending.known_args.get("new_vm_name")

    # Option 3: Annuler
    if choice in ("3", "annuler", "annule", "non", "n"):
        ctx.session.clear_pending_action()
        response = f"Clone de {source_vm} annule."
        ctx.session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(response=response, query_type=QueryType.ACTION)

    # Option 1 ou 2: Arreter la VM
    restart_after = choice in ("1", "redemarrer", "redémarrer", "restart")

    stop_label = (
        f"arreter puis redemarrer {source_vm}" if restart_after
        else f"arreter {source_vm}"
    )
    question = (
        f"OK, je vais {stop_label} pour cloner vers **{new_vm_name}**.\n\n"
        f"Quel type de clone ?\n"
        f"  1. Copie complete  (independante, prend l'espace de la VM source)\n"
        f"  2. Copy-on-Write   (COW - partage les donnees, rapide et leger)\n"
        f"  ?  Quelle difference ?\n\n"
        f"Ton choix ? (1/2 ou ?) [Entree = copie complete par defaut]"
    )

    ctx.session.set_pending_action(
        tool_name="vm_clone_with_stop",
        known_args={
            "source_vm": source_vm,
            "new_vm_name": new_vm_name,
            "_restart_after": restart_after,
            META_COW_CHOICE_PENDING: True
        },
        missing_args=[],
        clarification_question=question
    )
    ctx.session.add_turn(user_input=query, assistant_response=question)

    return PipelineResult(
        response=question,
        query_type=QueryType.ACTION,
        tool_call={
            "name": "vm_clone_with_stop",
            "arguments": {"source_vm": source_vm, "new_vm_name": new_vm_name}
        },
        pending_args=["_linked_choice"]
    )
