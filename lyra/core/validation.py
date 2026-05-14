"""
Lyra Core - Validation des VMs.

Fonctions de validation d'existence et d'etat des VMs KVM
avant execution d'outils MCP.
"""

import re
from typing import TYPE_CHECKING, Optional

from .types import PipelineResult, QueryType

if TYPE_CHECKING:
    from ..hestia.executor import HestiaExecutor
    from ..rag.session_memory import SessionMemory
    from ..models._analysis import EphaistosAnalysis


# Outils qui necessitent que la VM existe avant execution
VM_TOOLS_NEED_EXISTING: frozenset[str] = frozenset({
    "vm_start", "vm_stop", "vm_destroy", "vm_exec",
    "vm_copy", "vm_snapshot", "vm_verify", "vm_export",
})

# Outils pour lesquels vm_name est OBLIGATOIRE (erreur explicite si absent)
VM_TOOLS_REQUIRE_VM_NAME: frozenset[str] = frozenset({
    "vm_start", "vm_stop", "vm_destroy", "vm_exec",
    "vm_copy", "vm_snapshot", "vm_verify", "vm_export",
})

# Outils qui necessitent que la VM soit en cours d'execution (connexion SSH)
VM_TOOLS_REQUIRE_RUNNING: frozenset[str] = frozenset({
    "vm_verify",  # SSH dans la VM pour comparer
    "vm_exec",    # Execute une commande via SSH
    "vm_copy",    # SCP vers/depuis la VM
})

# Outils pour lesquels on affiche l'etat courant dans la confirmation
VM_TOOLS_SHOW_STATE: frozenset[str] = frozenset({
    "vm_start", "vm_stop", "vm_destroy", "vm_exec",
    "vm_copy", "vm_snapshot", "vm_export",
})


def get_existing_vm_names(hestia: "HestiaExecutor") -> list[str]:
    """Recupere les noms des VMs existantes via vm_status.

    Args:
        hestia: Executeur MCP HESTIA

    Returns:
        Liste des noms de VMs (vide si echec)
    """
    try:
        result = hestia.execute("fedora.vm_status", {})
        if result.success:
            names = []
            for line in result.content.split("\n"):
                # Format: "NOM    ETAT    IP    SSH"
                match = re.match(r'^\s*([a-zA-Z0-9\-_]+)\s+', line)
                # Filtrer les en-tetes du tableau
                if match and match.group(1) not in ("NOM", "---", "Liste"):
                    names.append(match.group(1))
            return names
    except Exception:
        pass
    return []


def get_vm_state(hestia: "HestiaExecutor", vm_name: str) -> dict:
    """Recupere l'etat courant d'une VM.

    Args:
        hestia: Executeur MCP HESTIA
        vm_name: Nom de la VM

    Returns:
        Dict avec 'running' (bool) et 'ip' (str ou None)
    """
    try:
        result = hestia.execute("fedora.vm_status", {"vm_name": vm_name})
        if result.success:
            content = result.content
            is_running = False
            ip = None

            # Chercher "Status:" ou "Status :"
            status_match = re.search(r'Status\s*:\s*(.+)', content, re.IGNORECASE)
            if status_match:
                status_line = status_match.group(1).strip()
                # Enlever les codes ANSI
                status_clean = re.sub(r'\x1b\[[0-9;]*m', '', status_line)
                is_running = (
                    "en cours" in status_clean.lower()
                    or "running" in status_clean.lower()
                )

            # Chercher "IP:"
            ip_match = re.search(r'IP\s*:\s*(\d+\.\d+\.\d+\.\d+)', content, re.IGNORECASE)
            if ip_match:
                ip = ip_match.group(1)

            return {"running": is_running, "ip": ip}
    except Exception:
        pass

    return {"running": False, "ip": None}


def validate_vm_existence(
    hestia: "HestiaExecutor",
    session: "SessionMemory",
    analysis: "EphaistosAnalysis",
    query: str,
) -> Optional[PipelineResult]:
    """Verifie que le vm_name fourni correspond a une VM existante.

    Appele juste avant _prepare_execution. Retourne un PipelineResult
    d'erreur si la VM est introuvable, None si tout est OK.

    Args:
        hestia: Executeur MCP HESTIA
        session: Memoire de session
        analysis: Analyse EPHAISTOS avec tool et arguments
        query: Requete originale

    Returns:
        PipelineResult d'erreur si VM invalide, None sinon
    """
    if not analysis.tool:
        return None

    tool_short = analysis.tool.split(".")[-1]
    if tool_short not in VM_TOOLS_NEED_EXISTING:
        return None

    vm_name = analysis.arguments.get("vm_name")
    if not vm_name:
        if tool_short not in VM_TOOLS_REQUIRE_VM_NAME:
            return None
        # vm_name requis mais absent : demander a l'utilisateur
        existing = get_existing_vm_names(hestia)
        vms_str = "\n".join(f"  - {n}" for n in (existing[:8] if existing else []))
        suffix = "\n  ..." if existing and len(existing) > 8 else ""
        response = (
            f"Quel nom de VM veux-tu utiliser pour `{tool_short}` ?\n\n"
            + (f"VMs disponibles :\n{vms_str}{suffix}" if existing else "Aucune VM trouvee.")
        )
        session.add_turn(user_input=query, assistant_response=response)
        return PipelineResult(
            response=response,
            query_type=QueryType.ACTION,
            error=f"vm_name requis pour {tool_short}"
        )

    existing = get_existing_vm_names(hestia)
    if not existing or vm_name in existing:
        # VM trouvee : verifier si l'outil requiert qu'elle soit allumee
        if tool_short in VM_TOOLS_REQUIRE_RUNNING:
            vm_state = get_vm_state(hestia, vm_name)
            if not vm_state.get("running"):
                response = (
                    f"La VM **{vm_name}** est actuellement eteinte.\n\n"
                    f"`{tool_short}` necessite qu'elle soit en cours d'execution "
                    f"(connexion SSH).\n\n"
                    f"Veux-tu que je la demarre ?"
                )
                session.set_pending_choice(
                    choice_type="vm_start_confirm",
                    options=[],
                    question=response,
                    metadata={"vm_name": vm_name, "original_tool": tool_short}
                )
                session.add_turn(user_input=query, assistant_response=response)
                return PipelineResult(
                    response=response,
                    query_type=QueryType.ACTION,
                )
        return None

    # VM introuvable : construire suggestions
    suggestions = [n for n in existing if vm_name.lower() in n.lower() or n.lower() in vm_name.lower()]
    display_list = suggestions[:6] if suggestions else existing[:6]
    vms_str = "\n".join(f"  - {n}" for n in display_list)
    suffix = "\n  ..." if len(existing) > 6 and not suggestions else ""

    response = (
        f"La VM **{vm_name}** n'existe pas.\n\n"
        f"VMs disponibles :\n{vms_str}{suffix}\n\n"
        "Verifie le nom et reessaie."
    )
    session.add_turn(user_input=query, assistant_response=response)
    return PipelineResult(
        response=response,
        query_type=QueryType.ACTION,
        error=f"VM '{vm_name}' introuvable"
    )
