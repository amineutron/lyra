"""
Lyra Core - Workflows vm_snapshot.

Gere la creation et le listage de snapshots VM:
- Proposition de nom par defaut pour la creation
- Liste des VMs disponibles pour le listage
- Traitement des reponses en attente (valeur par defaut acceptee)
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from ..types import QueryType, PipelineResult
from ..validation import get_existing_vm_names

if TYPE_CHECKING:
    from ...models.ephaistos import EphaistosAnalysis
    from ...rag.session_memory import PendingAction
    from .context import WorkflowContext


def handle_vm_snapshot_create_workflow(
    query: str, analysis: "EphaistosAnalysis", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Gere le workflow de creation de snapshot avec nom par defaut.

    Workflow:
    1. Genere un nom par defaut: snap-{vm_name}-{timestamp}
    2. Propose ce nom a l'utilisateur
    3. Si reponse vide/"ok"/"default" -> utilise le nom par defaut
    4. Sinon utilise la reponse de l'utilisateur

    Args:
        query:    Requete utilisateur
        analysis: Analyse EPHAISTOS
        ctx:      Contexte workflow
    """
    vm_name = analysis.arguments.get("vm_name")

    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    default_snapshot_name = f"snap-{vm_name}-{timestamp}"

    question = (
        f"D'accord pour creer un snapshot de **{vm_name}**.\n\n"
        f"Quel nom tu veux lui donner ?\n\n"
        f"Par defaut: **{default_snapshot_name}**\n"
        f"   (Appuie sur Entree pour valider)"
    )

    ctx.session.set_pending_action(
        tool_name=analysis.tool,
        known_args={
            **analysis.arguments,
            "_default_snapshot_name": default_snapshot_name
        },
        missing_args=["snapshot_name"],
        clarification_question=question
    )
    ctx.session.add_turn(user_input=query, assistant_response=question)

    return PipelineResult(
        response=question,
        query_type=QueryType.ACTION,
        tool_call={"name": analysis.tool, "arguments": analysis.arguments},
        pending_args=["snapshot_name"]
    )


def handle_vm_snapshot_list_workflow(
    query: str, analysis: "EphaistosAnalysis", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Gere le workflow de listage de snapshots avec liste des VMs proactive.

    Workflow:
    1. Liste les VMs disponibles via virsh
    2. Affiche la liste avec VM par defaut
    3. Demande "De quelle VM veux-tu voir les snapshots ?"

    Args:
        query:    Requete utilisateur
        analysis: Analyse EPHAISTOS
        ctx:      Contexte workflow
    """
    existing_vms = get_existing_vm_names(ctx.hestia)

    default_vm = None
    if existing_vms:
        default_vm = existing_vms[0]
        vm_list = "\n".join([f"  - **{vm}**" for vm in existing_vms])
        question = (
            f"VMs disponibles ({len(existing_vms)}):\n\n"
            f"{vm_list}\n\n"
            f"De quelle VM veux-tu voir les snapshots ?\n\n"
            f"Par defaut: **{default_vm}**\n"
            f"   (Appuie sur Entree pour valider)"
        )
    else:
        question = "Aucune VM trouvee. De quelle VM veux-tu voir les snapshots ?"

    ctx.session.set_pending_action(
        tool_name=analysis.tool,
        known_args={
            **analysis.arguments,
            "_default_vm_name": default_vm
        },
        missing_args=["vm_name"],
        clarification_question=question
    )
    ctx.session.add_turn(user_input=query, assistant_response=question)

    return PipelineResult(
        response=question,
        query_type=QueryType.ACTION,
        tool_call={"name": analysis.tool, "arguments": analysis.arguments},
        pending_args=["vm_name"]
    )


def handle_vm_snapshot_pending(
    query: str, pending: "PendingAction", ctx: "WorkflowContext"
) -> Optional["PipelineResult"]:
    """Traite les reponses en attente pour les snapshots (valeur par defaut).

    Couvre deux cas:
    - create: nom de snapshot par defaut accepte (reponse vide ou "ok")
    - list:   VM par defaut acceptee (reponse vide ou "ok")

    Args:
        query:   Reponse de l'utilisateur
        pending: PendingAction de type vm_snapshot
        ctx:     Contexte workflow

    Returns:
        PipelineResult si gere, None si non concerne (pipeline continue normalement)
    """
    from ...models.ephaistos import EphaistosAnalysis

    _DEFAULTS = ("", "ok", "oui", "d'accord", "default", "par defaut", "par défaut")
    q = query.strip().lower()

    if pending.known_args.get("action") == "create":
        default_name = pending.known_args.get("_default_snapshot_name")
        if default_name and q in _DEFAULTS:
            clean_args = {k: v for k, v in pending.known_args.items() if not k.startswith("_")}
            clean_args["snapshot_name"] = default_name
            analysis = EphaistosAnalysis(
                tool=pending.tool_name,
                arguments=clean_args,
                missing_args=[],
                confidence=1.0,
                reasoning="Nom par defaut accepte",
                raw_response=""
            )
            ctx.session.clear_pending_action()
            return ctx.prepare_execution(analysis, query)

    if pending.known_args.get("action") == "list":
        default_vm = pending.known_args.get("_default_vm_name")
        if default_vm and q in _DEFAULTS:
            clean_args = {k: v for k, v in pending.known_args.items() if not k.startswith("_")}
            clean_args["vm_name"] = default_vm
            analysis = EphaistosAnalysis(
                tool=pending.tool_name,
                arguments=clean_args,
                missing_args=[],
                confidence=1.0,
                reasoning="VM par defaut acceptee",
                raw_response=""
            )
            ctx.session.clear_pending_action()
            return ctx.prepare_execution(analysis, query)

    return None
