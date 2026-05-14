"""
Lyra Core - Workflow vm_export mode custom.

Gere le workflow interactif multi-tours pour l'export personnalise de VM:
- Pose successivement une question par groupe d'operations virt-sysprep
- Gere la question firstboot si user-account selectionne
- Affiche un recapitulatif et lance l'export
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..types import QueryType, PipelineResult

if TYPE_CHECKING:
    from ...rag.session_memory import PendingAction
    from .context import WorkflowContext


# ---------------------------------------------------------------------------
# Groupes d'operations virt-sysprep pour le mode custom
# ---------------------------------------------------------------------------

CUSTOM_EXPORT_GROUPS = [
    {
        "key": "identite",
        "label": "Identite machine",
        "desc": "machine-id, hostname, UUID reseau (udev)",
        "ops": ["machine-id", "net-hostname", "net-hwaddr", "udev-persistent-net"],
    },
    {
        "key": "comptes",
        "label": "Comptes utilisateurs",
        "desc": "comptes (UID>=1000), mots de passe, donnees PAM",
        "ops": ["user-account", "passwd-backups", "pam-data"],
    },
    {
        "key": "ssh",
        "label": "Cles SSH",
        "desc": "cles host SSH + repertoires ~/.ssh/ des users",
        "ops": ["ssh-hostkeys", "ssh-userdir"],
    },
    {
        "key": "reseau",
        "label": "Connexions reseau",
        "desc": "connexions NetworkManager (WiFi, VPN), DHCP",
        "ops": ["net-nmconn", "dhcp-client-state", "dhcp-server-state"],
    },
    {
        "key": "historiques",
        "label": "Historiques et logs",
        "desc": "historiques bash, logs systeme, logins, comptabilite",
        "ops": ["bash-history", "logfiles", "utmp", "pacct-log"],
    },
    {
        "key": "cache",
        "label": "Cache et fichiers temporaires",
        "desc": "fichiers /tmp, cache paquets RPM/yum, crash, blkid",
        "ops": ["tmp-files", "package-manager-cache", "crash-data", "abrt-data", "blkid-tab"],
    },
]


# ---------------------------------------------------------------------------
# Helper interne
# ---------------------------------------------------------------------------

def _export_confirm(
    query: str, vm_name: str, ops: list, firstboot: bool, ctx: "WorkflowContext"
) -> "PipelineResult":
    """Affiche le recapitulatif et lance l'export."""
    from ...models.ephaistos import EphaistosAnalysis

    ctx.session.clear_pending_action()

    if not ops:
        response = (
            f"Aucune operation selectionnee. Export de {vm_name} annule.\n"
            f"(Lance 'exporte {vm_name} en mode custom' pour recommencer.)"
        )
        ctx.session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(response=response, query_type=QueryType.ACTION)

    ops_display = ", ".join(ops)
    firstboot_line = "Oui (creation user + mot de passe au 1er boot)" if firstboot else "Non"
    recap = (
        f"**Recapitulatif export custom de {vm_name}:**\n"
        f"  Operations : {ops_display}\n"
        f"  Firstboot  : {firstboot_line}\n\n"
        f"Lancement de l'export..."
    )
    ctx.session.add_turn(user_input=query, assistant_response=recap)

    analysis = EphaistosAnalysis(
        tool="fedora.vm_export",
        arguments={
            "vm_name": vm_name,
            "mode": "custom",
            "operations": ops,
            "firstboot": firstboot,
        },
        missing_args=[],
        confidence=1.0,
        reasoning="custom export workflow complete",
        raw_response=""
    )
    return ctx.prepare_execution(analysis, query)


# ---------------------------------------------------------------------------
# Handlers publics
# ---------------------------------------------------------------------------

def handle_vm_export_custom_workflow(
    vm_name: str, query: str, ctx: "WorkflowContext"
) -> "PipelineResult":
    """Demarre le workflow interactif multi-tours pour vm_export mode custom.

    Pose successivement une question par groupe d'operations virt-sysprep.

    Args:
        vm_name: Nom de la VM a exporter
        query:   Requete utilisateur
        ctx:     Contexte workflow
    """
    first_group = CUSTOM_EXPORT_GROUPS[0]
    question = (
        f"Export personnalise de **{vm_name}**. Je vais te demander groupe par groupe.\n\n"
        f"**1/{len(CUSTOM_EXPORT_GROUPS)} - {first_group['label']}**\n"
        f"  ({first_group['desc']})\n"
        f"Effacer ? [O/n]"
    )
    ctx.session.set_pending_action(
        tool_name="fedora.vm_export",
        known_args={
            "_custom_export_vm": vm_name,
            "_custom_export_step": first_group["key"],
            "_custom_export_ops": [],
            "_custom_export_firstboot": None,
        },
        missing_args=[],
        clarification_question=question
    )
    ctx.session.add_turn(user_input=query, assistant_response=question)
    return PipelineResult(
        response=question,
        query_type=QueryType.ACTION,
        # tool_call presente pour les tests one-shot (args connus) ;
        # pending_args empeche l'execution immediate en mode interactif
        tool_call={"name": "fedora.vm_export", "arguments": {"vm_name": vm_name, "mode": "custom"}},
        pending_args=["_custom_export_step"]
    )


def handle_custom_export_step(
    query: str, pending: "PendingAction", ctx: "WorkflowContext"
) -> "PipelineResult":
    """Gere chaque tour du workflow vm_export mode custom.

    Avance d'un groupe a l'autre, puis pose la question firstboot si pertinent,
    puis affiche le recapitulatif et lance l'export.

    Args:
        query:   Reponse utilisateur (O/n)
        pending: PendingAction avec les metadonnees du workflow
        ctx:     Contexte workflow
    """
    vm_name = pending.known_args.get("_custom_export_vm", "")
    current_step = pending.known_args.get("_custom_export_step", "")
    ops: list = list(pending.known_args.get("_custom_export_ops", []))
    firstboot = pending.known_args.get("_custom_export_firstboot")

    q = query.strip().lower()
    yes = q in ("", "o", "oui", "yes", "y", "1", "ok", "d'accord") or bool(re.match(r'^oui', q))
    cancel = re.search(r'\b(?:annule[rz]?|cancel|stop|quitter|quitte)\b', q)

    if cancel:
        ctx.session.clear_pending_action()
        response = f"Export de {vm_name} annule."
        ctx.session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(response=response, query_type=QueryType.ACTION)

    group_keys = [g["key"] for g in CUSTOM_EXPORT_GROUPS]

    # Etape firstboot
    if current_step == "firstboot":
        return _export_confirm(query, vm_name, ops, bool(yes), ctx)

    # Etape d'un groupe normal
    group = next((g for g in CUSTOM_EXPORT_GROUPS if g["key"] == current_step), None)
    if group is None:
        return _export_confirm(query, vm_name, ops, bool(firstboot), ctx)

    if yes:
        ops.extend(group["ops"])

    idx = group_keys.index(current_step)
    next_idx = idx + 1

    if next_idx < len(CUSTOM_EXPORT_GROUPS):
        next_group = CUSTOM_EXPORT_GROUPS[next_idx]
        step_num = next_idx + 1
        question = (
            f"**{step_num}/{len(CUSTOM_EXPORT_GROUPS)} - {next_group['label']}**\n"
            f"  ({next_group['desc']})\n"
            f"Effacer ? [O/n]"
        )
        ctx.session.set_pending_action(
            tool_name="fedora.vm_export",
            known_args={
                "_custom_export_vm": vm_name,
                "_custom_export_step": next_group["key"],
                "_custom_export_ops": ops,
                "_custom_export_firstboot": firstboot,
            },
            missing_args=[],
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            pending_args=["_custom_export_step"]
        )

    # Tous les groupes parcourus
    if "user-account" in ops:
        question = (
            f"**Firstboot**\n"
            f"Les comptes utilisateurs seront effaces. Installer le script de\n"
            f"configuration au premier demarrage (demande user + mot de passe) ?\n"
            f"[O/n]"
        )
        ctx.session.set_pending_action(
            tool_name="fedora.vm_export",
            known_args={
                "_custom_export_vm": vm_name,
                "_custom_export_step": "firstboot",
                "_custom_export_ops": ops,
                "_custom_export_firstboot": None,
            },
            missing_args=[],
            clarification_question=question
        )
        ctx.session.add_turn(user_input=query, assistant_response=question)
        return PipelineResult(
            response=question,
            query_type=QueryType.ACTION,
            pending_args=["_custom_export_step"]
        )

    # Pas de user-account -> confirmation directe
    return _export_confirm(query, vm_name, ops, False, ctx)
