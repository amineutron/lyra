"""
Lyra Core - Validation des VMs.

Fonctions de validation d'existence et d'etat des VMs KVM
avant execution d'outils MCP.
"""

import difflib
import re
from typing import TYPE_CHECKING, Optional

from ..rag.session_memory import CHOICE_VM_START_CONFIRM
from .constants import DESTRUCTIVE_TOOLS
from .types import PipelineResult, QueryType

if TYPE_CHECKING:
    from ..hestia.executor import HestiaExecutor
    from ..models._analysis import EphaistosAnalysis
    from ..rag.session_memory import SessionMemory


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


def get_hue_groups(hestia: "HestiaExecutor") -> dict:
    """Groupes Hue reels {id: nom} via hue.get_all_groups (vide si echec)."""
    try:
        result = hestia.execute("hue.get_all_groups", {})
        if result.success:
            import json
            data = json.loads(result.content)
            if isinstance(data, dict):
                return {str(k): str((v or {}).get("name", k)) for k, v in data.items()}
    except Exception:
        pass
    return {}


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


def _vm_key(name: object) -> str:
    """Forme comparable d'un nom de VM : minuscules, espaces/underscores -> tirets."""
    return re.sub(r"[\s_]+", "-", str(name or "").strip().lower()).strip("-")


def resolve_vm_name(name: str, existing: list[str], exact_only: bool = False) -> Optional[str]:
    """Nom reel de la VM pour un nom saisi ou dit a voix haute, ou None.

    "test vm" -> "test-vm", "preprod 09" -> "preprod-09". Sans `exact_only`,
    accepte aussi une sous-chaine ou un nom quasi identique, mais seulement
    s'il n'y a qu'un candidat (jamais de choix au hasard entre deux VM).
    `exact_only` : egalite apres normalisation uniquement (actions destructives).
    """
    key = _vm_key(name)
    if not key:
        return None
    keyed = [(_vm_key(vm), vm) for vm in existing]
    exact = [vm for k, vm in keyed if k == key]
    if len(exact) == 1:
        return exact[0]
    if exact_only or exact:
        return None
    contained = [vm for k, vm in keyed
                 if len(key) >= 3 and (key in k or (len(k) >= 3 and k in key))]
    if len(contained) == 1:
        return contained[0]
    if contained:
        return None  # plusieurs candidats : l'utilisateur doit preciser
    close = difflib.get_close_matches(key, [k for k, _ in keyed], n=2, cutoff=0.85)
    if len(close) == 1:
        return next(vm for k, vm in keyed if k == close[0])
    return None


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
    if existing and vm_name not in existing:
        # "test vm" dit a voix haute -> "test-vm" (jamais d'approximation pour
        # une action destructive : egalite apres normalisation uniquement)
        resolved = resolve_vm_name(vm_name, existing,
                                   exact_only=tool_short in DESTRUCTIVE_TOOLS)
        if resolved:
            analysis.arguments = {**analysis.arguments, "vm_name": resolved}
            vm_name = resolved
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
                    choice_type=CHOICE_VM_START_CONFIRM,
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
