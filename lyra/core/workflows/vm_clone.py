"""
Lyra Core - Workflow vm_clone.

Gere le workflow interactif de clonage de VM:
- Validation source/destination
- Proposition de nom alternatif
- Arret de la VM source si necessaire
- Choix COW vs copie complete
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from ..types import QueryType, PipelineResult
from ..validation import get_existing_vm_names, get_vm_state
from ...rag.session_memory import META_COW_CHOICE_PENDING, META_STOP_CHOICE_PENDING

if TYPE_CHECKING:
    from ...models.ephaistos import EphaistosAnalysis
    from ...rag.session_memory import PendingAction
    from .context import WorkflowContext


# ---------------------------------------------------------------------------
# Fonction pure
# ---------------------------------------------------------------------------

def suggest_vm_name(existing_names: list[str], source_name: str) -> str:
    """Suggere un nom de VM unique a partir du nom source.

    Args:
        existing_names: Noms de VMs existantes
        source_name:    Nom de la VM source (pour inspiration)

    Returns:
        Nom suggere unique
    """
    base = source_name.rstrip("0123456789-_") if source_name else "vm"
    for i in range(2, 100):
        suggestion = f"{base}-{i:02d}"
        if suggestion not in existing_names:
            return suggestion
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


# ---------------------------------------------------------------------------
# Handler COW choice
# ---------------------------------------------------------------------------

def handle_cow_choice(
    query: str, pending: "PendingAction", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Gere le choix COW vs copie complete pour vm_clone.

    - "1" / "copie" / "complete" / "" -> linked=False (copie complete, defaut)
    - "2" / "cow" / "linked" / "partage" -> linked=True (copy-on-write)
    - "?" / "info" / "c'est quoi" -> explication, repose la question
    - "annule" -> annulation

    Args:
        query:   Reponse utilisateur
        pending: PendingAction avec source_vm, new_vm_name
        ctx:     Contexte workflow
    """
    from ...models.ephaistos import EphaistosAnalysis

    source_vm = pending.known_args.get("source_vm")
    new_vm_name = pending.known_args.get("new_vm_name")

    # Demande d'information sur le COW
    if re.search(
        r"\b(?:c'?est quoi|qu'?est.+ce|explique|aide|help|diff.?rence|avantage|pourquoi|comment)\b",
        query, re.IGNORECASE
    ) or query.strip() in ("?", "info"):
        explanation = (
            "**Copy-on-Write (COW / clone lie)**\n"
            "Le clone partage les blocs de donnees de la VM source. Seuls les changements "
            "apres le clone sont stockes separement.\n"
            "  + Tres rapide a creer (quelques secondes)\n"
            "  + Tres leger au depart (quelques Mo seulement)\n"
            "  - Depend de la VM source : si elle est supprimee, le clone peut etre corrompu\n"
            "  - Moins adapte pour un environnement de production isole\n\n"
            "**Copie complete (full clone)**\n"
            "Le clone est totalement independant de la source.\n"
            "  + Autonome : fonctionne meme si la source est supprimee ou modifiee\n"
            "  + Ideal pour la production\n"
            "  - Plus lent a creer, occupe autant d'espace que la VM source\n\n"
            "Ton choix ? (1 = copie complete / 2 = COW) [Entree = copie complete par defaut]"
        )
        ctx.session.add_turn(user_input=query, assistant_response=explanation)
        return PipelineResult(
            response=explanation,
            query_type=QueryType.ACTION,
            pending_args=["_linked_choice"]
        )

    # Annulation - "non" seul = annuler, "non copie complete" = garder copie complete
    _cancel_only = re.sub(
        r'\b(?:copie|complete|full|complet|cow|linked|partage)\b', '',
        query, flags=re.IGNORECASE
    ).strip()
    if re.search(r"\b(?:annule[rz]?|cancel|stop)\b", query, re.IGNORECASE) or \
            re.match(r'^\s*non\.?!?\s*$', _cancel_only, re.IGNORECASE):
        ctx.session.clear_pending_action()
        response = f"Clone de {source_vm} annule."
        ctx.session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(response=response, query_type=QueryType.ACTION)

    # COW (linked=True)
    if re.search(
        r"\b(?:2|cow|copy.?on.?write|linked|partage|lie|rapide|leger)\b",
        query, re.IGNORECASE
    ):
        linked = True
    else:
        linked = False  # Par defaut: copie complete

    type_label = "COW (clone lie)" if linked else "copie complete"
    ctx.session.clear_pending_action()

    # Path vm_clone_with_stop: la VM etait en cours, renvoyer tool_call directement
    restart_after = pending.known_args.get("_restart_after")
    if pending.tool_name == "vm_clone_with_stop":
        message = f"Clone {type_label} de {source_vm} vers {new_vm_name}."
        ctx.session.add_turn(user_input=query, assistant_response=message)
        return PipelineResult(
            response=message,
            query_type=QueryType.ACTION,
            tool_call={
                "name": "vm_clone_with_stop",
                "arguments": {
                    "source_vm": source_vm,
                    "new_vm_name": new_vm_name,
                    "restart_after": bool(restart_after),
                    "linked": linked
                }
            }
        )

    # Path normal: vm_clone (VM deja arretee)
    analysis = EphaistosAnalysis(
        tool=pending.tool_name,
        arguments={"source_vm": source_vm, "new_vm_name": new_vm_name, "linked": linked},
        missing_args=[],
        confidence=1.0,
        reasoning=f"COW choice: linked={linked}",
        raw_response=""
    )
    ctx.session.add_turn(
        user_input=query,
        assistant_response=f"Clone {type_label} de {source_vm} vers {new_vm_name}."
    )
    return ctx.prepare_execution(analysis, query)


# ---------------------------------------------------------------------------
# Workflow principal vm_clone
# ---------------------------------------------------------------------------

def handle_vm_clone_workflow(
    query: str, analysis: "EphaistosAnalysis", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Gere le workflow interactif de vm_clone.

    Workflow:
    1. Liste les VMs existantes avec vm_status
    2. Demande source_vm si manquant (avec verification)
    3. Demande new_vm_name si manquant (avec verification)
    4. Valide que new_vm_name n'existe pas
    5. Verifie l'etat de la VM source (running -> proposer arret)
    6. Demande COW vs copie complete si 'linked' non specifie
    7. Prepare l'execution

    Args:
        query:    Requete utilisateur
        analysis: Analyse EPHAISTOS
        ctx:      Contexte workflow
    """
    # Extraction regex de fallback si EPHAISTOS n'a pas extrait les args
    if not analysis.arguments.get("source_vm") and not analysis.missing_args:
        m = re.search(
            r'(?:clone[rz]?|duplique[rz]?)\s+([\w][\w.-]*)\s+en\s+([\w][\w.-]*)',
            query.lower()
        )
        if m:
            analysis.arguments["source_vm"] = m.group(1)
            analysis.arguments["new_vm_name"] = m.group(2)
        else:
            analysis.missing_args = ["source_vm", "new_vm_name"]

    existing_vms = get_existing_vm_names(ctx.hestia)

    if existing_vms:
        vm_list = ", ".join(existing_vms)
        vm_intro = f"VMs existantes: {vm_list}\n\n"
    else:
        vm_intro = "Aucune VM existante trouvee.\n\n"

    # Cas 1: source_vm manquant
    if "source_vm" in analysis.missing_args or "source_vm_name" in analysis.missing_args:
        question = vm_intro + "Quelle VM veux-tu cloner (source) ?"
        ctx.session.set_pending_action(
            tool_name=analysis.tool,
            known_args=analysis.arguments,
            missing_args=analysis.missing_args,
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            tool_call={"name": analysis.tool, "arguments": analysis.arguments},
            pending_args=analysis.missing_args
        )

    # Cas 2: source_vm fourni mais pas encore confirmee
    pending = ctx.session.get_pending_action()
    source_confirmed = pending and pending.known_args.get("_source_confirmed") if pending else False
    source_vm = analysis.arguments.get("source_vm") or analysis.arguments.get("source_vm_name")

    if not source_confirmed and "new_vm_name" in analysis.missing_args:
        if source_vm not in existing_vms:
            # Chercher un nom similaire (typo: preprod01 -> preprod-01)
            suggested_source = None
            if source_vm:
                for vm in existing_vms:
                    if vm.replace("-", "").lower() == source_vm.replace("-", "").lower():
                        suggested_source = vm
                        break
            if suggested_source:
                question = (
                    vm_intro +
                    f"VM '{source_vm}' introuvable. Tu voulais dire **{suggested_source}** ?\n\n"
                    f"VM disponibles: {', '.join(existing_vms)}\n\n"
                    f"Quelle VM veux-tu cloner ?"
                )
            else:
                question = vm_intro + f"La VM '{source_vm}' n'existe pas!\n\nQuelle VM veux-tu cloner ?"

            ctx.session.set_pending_action(
                tool_name=analysis.tool,
                known_args={},
                missing_args=["source_vm", "new_vm_name"],
                clarification_question=question
            )
            ctx.session.add_turn(user_input=query, assistant_response=question)
            return PipelineResult(
                response=question,
                query_type=QueryType.ACTION,
                tool_call={"name": analysis.tool, "arguments": {}},
                pending_args=["source_vm", "new_vm_name"]
            )

        # Source existe -> demander nom destination
        suggested_name = suggest_vm_name(existing_vms, source_vm)
        question = (
            vm_intro +
            f"VM source: **{source_vm}**\n\n"
            f"Quel nom veux-tu donner a la nouvelle VM ?\n\n"
            f"Suggestion: {suggested_name}"
        )
        ctx.session.set_pending_action(
            tool_name=analysis.tool,
            known_args={"source_vm": source_vm, "_source_confirmed": True},
            missing_args=["new_vm_name"],
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            tool_call={"name": analysis.tool, "arguments": {"source_vm": source_vm}},
            pending_args=["new_vm_name"]
        )

    # Cas 3: new_vm_name fourni -> valider qu'il n'existe pas
    new_vm_name = analysis.arguments.get("new_vm_name")
    if new_vm_name and new_vm_name in existing_vms:
        suggested_name = suggest_vm_name(existing_vms, source_vm)
        question = (
            f"Le nom '{new_vm_name}' existe deja!\n\n"
            f"Proposition: {suggested_name}\n\n"
            f"Quel nom veux-tu utiliser ?"
        )
        ctx.session.set_pending_action(
            tool_name=analysis.tool,
            known_args={"source_vm": source_vm, "_source_confirmed": True},
            missing_args=["new_vm_name"],
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            tool_call={"name": analysis.tool, "arguments": {"source_vm": source_vm}},
            pending_args=["new_vm_name"]
        )

    # Cas 4: Verification finale que la source existe
    if source_vm not in existing_vms:
        suggested_source = None
        if source_vm:
            for vm in existing_vms:
                if vm.replace("-", "").lower() == source_vm.replace("-", "").lower():
                    suggested_source = vm
                    break
        if suggested_source:
            question = (
                vm_intro +
                f"La VM '{source_vm}' n'existe pas!\n\n"
                f"Peut-etre voulais-tu: **{suggested_source}** ?\n\n"
                f"Quelle VM veux-tu cloner ?"
            )
        else:
            question = (
                vm_intro +
                f"La VM '{source_vm}' n'existe pas!\n\n"
                f"Quelle VM veux-tu cloner ?"
            )
        ctx.session.set_pending_action(
            tool_name=analysis.tool,
            known_args={},
            missing_args=["source_vm", "new_vm_name"],
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            tool_call={"name": analysis.tool, "arguments": {}},
            pending_args=["source_vm", "new_vm_name"]
        )

    # Cas 5: VM source en cours d'execution -> proposer arret
    vm_state = get_vm_state(ctx.hestia, source_vm)
    if vm_state.get("running"):
        question = (
            f"La VM **{source_vm}** est en cours d'execution!\n\n"
            f"Pour cloner une VM, elle doit etre arretee.\n\n"
            f"Options:\n"
            f"  1. Arreter temporairement {source_vm}, cloner, puis redemarrer\n"
            f"  2. Arreter {source_vm} et cloner (sans redemarrage)\n"
            f"  3. Annuler le clonage\n\n"
            f"Ton choix ? (1/2/3)"
        )
        ctx.session.set_pending_action(
            tool_name=analysis.tool,
            known_args={
                "source_vm": source_vm,
                "new_vm_name": new_vm_name,
                "_vm_running": True,
                META_STOP_CHOICE_PENDING: True
            },
            missing_args=[],
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            tool_call={
                "name": analysis.tool,
                "arguments": {"source_vm": source_vm, "new_vm_name": new_vm_name}
            },
            pending_args=["_user_choice"]
        )

    # Cas 6: Demander COW vs copie complete si 'linked' non specifie
    if "linked" not in analysis.arguments:
        question = (
            f"Clone **{source_vm}** -> **{new_vm_name}** : quel type de clone ?\n\n"
            f"  1. Copie complete  (independante, prend l'espace de la VM source)\n"
            f"  2. Copy-on-Write   (COW - partage les donnees, rapide et leger)\n"
            f"  ?  Quelle difference ?\n\n"
            f"Ton choix ? (1/2 ou ?) [Entree = copie complete par defaut]"
        )
        ctx.session.set_pending_action(
            tool_name=analysis.tool,
            known_args={
                "source_vm": source_vm,
                "new_vm_name": new_vm_name,
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
                "name": analysis.tool,
                "arguments": {"source_vm": source_vm, "new_vm_name": new_vm_name}
            },
            pending_args=["_linked_choice"]
        )

    # Tout est OK -> nettoyer les metadata internes et preparer execution
    clean_args = {k: v for k, v in analysis.arguments.items() if not k.startswith("_")}
    analysis.arguments = clean_args
    return ctx.prepare_execution(analysis, query)
