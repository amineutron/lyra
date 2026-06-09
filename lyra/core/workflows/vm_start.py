"""
Lyra Core - Workflow vm_start_confirm.

Traite la reponse utilisateur a la proposition de demarrer une VM eteinte
avant d'executer un outil qui necessite une VM active.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..types import QueryType, PipelineResult
from ...rag.session_memory import CHOICE_VM_START_CONFIRM

if TYPE_CHECKING:
    from ...models.ephaistos import EphaistosAnalysis
    from ...rag.session_memory import PendingChoice
    from .context import WorkflowContext


def handle_vm_start_confirm(
    query: str, pending: "PendingChoice", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Traite la reponse a la proposition de demarrer une VM eteinte.

    4 cas possibles:
    - Oui           -> execute vm_start sur la VM
    - Non           -> annule, message de confirmation
    - Clarification -> repond a la question et re-pose la proposition
    - Autre         -> traite comme une nouvelle requete

    Args:
        query:   Reponse de l'utilisateur
        pending: PendingChoice avec metadata {vm_name, original_tool}
        ctx:     Contexte workflow
    """
    from ...models.ephaistos import EphaistosAnalysis

    metadata = pending.metadata
    vm_name = metadata.get("vm_name", "")
    original_tool = metadata.get("original_tool", "")

    q = query.lower().strip()

    # Cas 1 : Oui
    _OUI = {"oui", "o", "ok", "yes", "yep", "ouais", "bien sur", "vas-y",
            "allez", "go", "stp", "please", "affirmatif", "demarre", "demarre-la"}
    if q in _OUI or any(mot in q for mot in ("oui", "ok", "vas-y", "bien sur", "ouais",
                                               "demarre", "allume", "lance")):
        analysis = EphaistosAnalysis(
            tool="fedora.vm_start",
            arguments={"vm_name": vm_name},
            missing_args=[],
            confidence=1.0,
            reasoning=f"confirm: demarre {vm_name} avant {original_tool}",
            raw_response=""
        )
        response_prefix = (
            f"Je demarre **{vm_name}**.\n"
            f"Une fois allumee, relance `{original_tool}` pour continuer.\n\n"
        )
        result = ctx.prepare_execution(analysis, query)
        result.response = response_prefix + result.response
        return result

    # Cas 2 : Non
    _NON = {"non", "n", "no", "nope", "annule", "laisse", "laisse tomber",
            "pas la peine", "abandonne", "stop"}
    if q in _NON or any(mot in q for mot in ("non", "annule", "laisse", "pas la peine")):
        response = f"OK, `{original_tool}` annule. La VM **{vm_name}** reste eteinte."
        ctx.session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(response=response, query_type=QueryType.ACTION)

    # Cas 3 : Clarification (question sur pourquoi, comment, etc.)
    if "?" in query or any(mot in q for mot in ("pourquoi", "comment", "c est quoi",
                                                  "c'est quoi", "qu est", "qu'est")):
        clarif = ctx.lyra.chat(
            user_message=query,
            context=(
                f"L'utilisateur a demande `{original_tool}` sur la VM **{vm_name}** "
                f"qui est eteinte. Lyra a propose de la demarrer. "
                f"L'utilisateur pose maintenant une question de clarification."
            )
        )
        response = clarif.text + f"\n\nDonc, veux-tu que je demarre **{vm_name}** ?"
        ctx.session.set_pending_choice(
            choice_type=CHOICE_VM_START_CONFIRM,
            options=[],
            question=response,
            metadata=metadata
        )
        ctx.session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(response=response, query_type=QueryType.KNOWLEDGE)

    # Cas 4 : Autre -> traiter comme nouvelle requete
    return ctx.route_query(query)
