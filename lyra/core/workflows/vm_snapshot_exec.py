"""
Lyra Core - Execution workflow snapshot restore.

Gere la restauration de snapshot avec:
- Creation d'un snapshot de securite avant restauration (recommande)
- Arret de la VM si en cours d'execution
- Validations et confirmations multi-etapes
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import ExecContext


def handle_snapshot_restore_with_safety(arguments: dict, ctx: "ExecContext") -> str:
    """Execute la restauration de snapshot avec snapshot de securite.

    Sequence:
    1. Lister les snapshots disponibles
    2. Verifier que le snapshot existe
    3. Proposer creation d'un snapshot de securite (recommande)
    4. Afficher le plan complet + demander si redemarrage
    5. Confirmer le plan
    6. Creer le snapshot de securite (si choisi)
    7. Arreter la VM si en cours d'execution
    8. Restaurer le snapshot
    9. Redemarrer la VM si demande
    10. Notification Discord

    Args:
        arguments: vm_name, snapshot_name, create_safety_snapshot (opt), restart_after (opt)
        ctx:       Contexte d'execution avec UI, execute_action, etc.

    Returns:
        Message de synthese (multi-lignes si plusieurs etapes).
    """
    ui = ctx.ui
    vm_name = arguments.get("vm_name")
    snapshot_name = arguments.get("snapshot_name")
    create_safety = arguments.get("create_safety_snapshot", None)   # None = demander
    restart_after = arguments.get("restart_after", None)            # None = demander

    messages: list[str] = []

    # --- Etape 0: Verifications prealables ---
    ui.println()
    ui.print_info("Verifications prealables...")

    snapshots_result = ctx.hestia_execute("fedora.vm_snapshot", {
        "vm_name": vm_name,
        "action": "list",
    })

    if not snapshots_result.success:
        ui.print_error(f"Impossible de lister les snapshots de {vm_name}")
        return f"Erreur: {snapshots_result.error}"

    ui.println(f"\n{ui.colored('Snapshots disponibles:', 'cyan')}")
    ui.println(snapshots_result.content)
    ui.println()

    if snapshot_name not in snapshots_result.content:
        ui.print_error(f"Snapshot '{snapshot_name}' introuvable!")
        return f"Snapshot '{snapshot_name}' n'existe pas pour {vm_name}"

    vm_state_result = ctx.hestia_execute("fedora.vm_status", {"vm_name": vm_name})
    if vm_state_result.success:
        ui.println(f"{ui.colored('Etat actuel de la VM:', 'cyan')}")
        for line in vm_state_result.content.split("\n")[:5]:
            if line.strip():
                ui.println(f"  {line}")
        ui.println()

    vm_running = "en cours" in vm_state_result.content.lower() if vm_state_result.success else False

    # --- Etape 1: Choix snapshot de securite ---
    if create_safety is None:
        ui.println()
        ui.println(ui.colored("ATTENTION: La restauration va ecraser l'etat actuel!", "yellow"))
        ui.println()
        ui.print_info("Je recommande de creer un snapshot de securite")
        ui.println("   pour pouvoir revenir a l'etat actuel si besoin.")
        ui.println()
        ui.println(f"  1. {ui.colored('Creer snapshot de securite', 'green')} puis restaurer (recommande)")
        ui.println(f"  2. {ui.colored('Restaurer directement', 'yellow')} (sans snapshot de securite)")
        ui.println(f"  3. {ui.colored('Annuler', 'red')}")
        ui.println()

        choice = ui.ask_input(ui.colored("  Ton choix ? (1/2/3) ", "yellow")).strip()

        if choice == "3" or choice.lower() in ("annuler", "annule", "n"):
            ui.print_warning("Restauration annulee.")
            return "Restauration annulee."

        create_safety = (choice == "1" or choice.lower() in ("oui", "o", ""))

    safety_snapshot_name: str | None = None
    if create_safety:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_snapshot_name = f"restore-backup-{vm_name}-{ts}"

    # --- Etape 2: Plan d'action complet ---
    ui.println()
    ui.print_info("Plan d'action:")

    step = 1
    if create_safety:
        ui.println(f"  {step}. {ui.colored('Creer snapshot de securite', 'cyan')} <<{safety_snapshot_name}>>")
        step += 1
    if vm_running:
        ui.println(f"  {step}. {ui.colored('Arreter', 'yellow')} {vm_name}")
        step += 1

    ui.println(f"  {step}. {ui.colored('Restaurer snapshot', 'magenta')} <<{snapshot_name}>>")
    step += 1

    if restart_after is None:
        restart_prompt = ui.ask_input(
            ui.colored(f"  Redemarrer {vm_name} apres restauration ? [O/n] ", "yellow")
        ).strip().lower()
        restart_after = restart_prompt not in ("n", "non", "no")

    if restart_after:
        ui.println(f"  {step}. {ui.colored('Redemarrer', 'green')} {vm_name}")

    ui.println()

    plan_confirm = ui.ask_input(ui.colored("  Confirmer ce plan ? [O/n] ", "yellow")).strip().lower()
    if plan_confirm in ("n", "non", "no"):
        ui.print_warning("Plan annule.")
        return "Plan annule."

    total_steps = step - 1

    # --- Etape 3: Creer snapshot de securite ---
    if create_safety and safety_snapshot_name:
        ui.println()
        ui.print_info(f"Etape 1/{total_steps}: Creation snapshot de securite")

        safety_confirm = ui.confirm_action(
            tool_name="vm_snapshot",
            arguments={"vm_name": vm_name, "action": "create", "snapshot_name": safety_snapshot_name},
            vocal_mode=ctx.vocal,
            voice=ctx.voice,
        )
        if safety_confirm == "modify":
            ui.print_warning("Modification non disponible pour cette etape.")
            safety_confirm = False

        if not safety_confirm:
            ui.print_warning("Snapshot de securite annule. Restauration annulee.")
            return "Restauration annulee (snapshot de securite refuse)."

        ui.print_info(f"Creation de '{safety_snapshot_name}' en cours...")
        safety_result = ctx.execute_action("fedora.vm_snapshot", {
            "vm_name": vm_name,
            "action": "create",
            "snapshot_name": safety_snapshot_name,
            "description": f"Snapshot de securite avant restauration de '{snapshot_name}'",
        })

        if safety_result.error or not (safety_result.execution_result and safety_result.execution_result.success):
            ui.print_error("Echec de la creation du snapshot de securite")
            return f"Impossible de creer le snapshot de securite: {safety_result.error}"

        ui.print_success(f"Snapshot de securite '{safety_snapshot_name}' cree")
        messages.append("Snapshot de securite cree")

    # --- Etape 4: Arreter la VM si running ---
    if vm_running:
        current_step = 2 if create_safety else 1
        ui.println()
        ui.print_info(f"Etape {current_step}/{total_steps}: Arret de {vm_name}")

        stop_confirm = ui.confirm_action(
            tool_name="vm_stop",
            arguments={"vm_name": vm_name},
            vocal_mode=ctx.vocal,
            voice=ctx.voice,
        )
        if stop_confirm == "modify":
            ui.print_warning("Modification non disponible.")
            stop_confirm = False

        if not stop_confirm:
            ui.print_warning(f"Arret de {vm_name} annule.")
            return "Restauration annulee (arret refuse)."

        ui.print_info(f"Arret de {vm_name} en cours...")
        stop_result = ctx.execute_action("fedora.vm_stop", {"vm_name": vm_name})

        if stop_result.error or not (stop_result.execution_result and stop_result.execution_result.success):
            ui.print_error(f"Echec de l'arret de {vm_name}")
            return f"Impossible d'arreter {vm_name}: {stop_result.error}"

        ui.print_success(f"{vm_name} arretee")
        messages.append(f"{vm_name} arretee")

    # --- Etape 5: Restaurer le snapshot ---
    restore_step = (2 if create_safety else 1) + (1 if vm_running else 0)
    ui.println()
    ui.print_info(f"Etape {restore_step}/{total_steps}: Restauration snapshot '{snapshot_name}'")

    ui.println(f"\n{ui.colored('ATTENTION:', 'yellow')} Cette action va remplacer l'etat actuel de {vm_name}")
    ui.println(f"   par l'etat du snapshot '{snapshot_name}'.\n")

    restore_confirm = ui.confirm_action(
        tool_name="vm_snapshot",
        arguments={"vm_name": vm_name, "action": "revert", "snapshot_name": snapshot_name},
        vocal_mode=ctx.vocal,
        voice=ctx.voice,
    )
    if restore_confirm == "modify":
        ui.print_warning("Modification non disponible.")
        restore_confirm = False

    if not restore_confirm:
        ui.print_warning("Restauration annulee.")
        if vm_running:
            restart_anyway = ui.ask_input(
                ui.colored(f"\n  Redemarrer {vm_name} quand meme ? [O/n] ", "yellow")
            ).strip().lower()
            if restart_anyway not in ("n", "non", "no"):
                ui.print_info(f"Redemarrage de {vm_name}...")
                restart_result = ctx.execute_action("fedora.vm_start", {"vm_name": vm_name})
                if restart_result.execution_result and restart_result.execution_result.success:
                    messages.append(f"{vm_name} redemarree")
        return "\n".join(messages + ["Restauration annulee"])

    ui.print_info(f"Restauration du snapshot '{snapshot_name}' en cours...")
    restore_result = ctx.execute_action("fedora.vm_snapshot", {
        "vm_name": vm_name,
        "action": "revert",
        "snapshot_name": snapshot_name,
    })

    if restore_result.error or not (restore_result.execution_result and restore_result.execution_result.success):
        ui.print_error("Echec de la restauration")
        messages.append(f"Echec de la restauration: {restore_result.error}")

        if create_safety and safety_snapshot_name:
            ui.print_warning(f"Tu peux restaurer le snapshot de securite '{safety_snapshot_name}'")
            ui.print_warning("   pour revenir a l'etat avant cette tentative.")

        return "\n".join(messages)

    ui.print_success(f"Snapshot '{snapshot_name}' restaure")
    messages.append(f"Snapshot '{snapshot_name}' restaure")

    if ctx.notify_discord:
        ctx.notify_discord("vm_snapshot", {
            "vm_name": vm_name,
            "action": "revert",
            "snapshot_name": snapshot_name,
            "safety_snapshot": safety_snapshot_name,
        }, restore_result)

    # --- Etape 6: Redemarrer la VM ---
    if restart_after:
        final_step = total_steps
        ui.println()
        ui.print_info(f"Etape {final_step}/{final_step}: Redemarrage de {vm_name}")

        restart_confirm = ui.ask_input(
            ui.colored(f"\n  Redemarrer {vm_name} maintenant ? [O/n] ", "yellow")
        ).strip().lower()

        if restart_confirm not in ("n", "non", "no"):
            ui.print_info(f"Redemarrage de {vm_name} en cours...")
            restart_result = ctx.execute_action("fedora.vm_start", {"vm_name": vm_name})

            if restart_result.execution_result and restart_result.execution_result.success:
                ui.print_success(f"{vm_name} redemarree")
                messages.append(f"{vm_name} redemarree")
            else:
                ui.print_warning(f"Echec du redemarrage de {vm_name}")
                messages.append(f"Echec redemarrage de {vm_name}")
        else:
            ui.print_info(f"{vm_name} reste arretee")
            messages.append(f"{vm_name} reste arretee")
    else:
        messages.append(f"{vm_name} reste arretee")

    final_message = "\n".join(messages)
    ui.println()
    ui.print_tool_result(final_message, True)
    return final_message
