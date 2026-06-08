"""
Lyra Core - Execution workflow vm_clone_with_stop.

Gere le clonage d'une VM avec arret prealable (VM source en cours d'execution).
Workflow multi-etapes avec validations et confirmations a chaque etape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import ExecContext


def handle_vm_clone_with_stop(arguments: dict, ctx: "ExecContext") -> str:
    """Execute le clone d'une VM avec arret et redemarrage optionnel.

    Sequence:
    1. Afficher le plan complet
    2. Demander confirmation du plan
    3. Arreter la VM source (avec confirmation)
    4. Cloner la VM (avec confirmation)
    5. Redemarrer la VM source si demande (avec confirmation)

    Args:
        arguments: source_vm, new_vm_name, restart_after, linked (optionnel)
        ctx:       Contexte d'execution avec UI, execute_action, etc.

    Returns:
        Message de synthese (multi-lignes si plusieurs etapes).
    """
    ui = ctx.ui
    source_vm = arguments.get("source_vm")
    new_vm_name = arguments.get("new_vm_name")
    restart_after = arguments.get("restart_after", False)

    messages: list[str] = []
    total_steps = 3 if restart_after else 2

    # --- Plan d'action ---
    ui.println()
    ui.print_info("Plan d'action:")
    ui.println(f"  1. {ui.colored('Arreter', 'yellow')} {source_vm}")
    ui.println(f"  2. {ui.colored('Cloner', 'cyan')} {source_vm} -> {new_vm_name}")
    if restart_after:
        ui.println(f"  3. {ui.colored('Redemarrer', 'green')} {source_vm}")
    else:
        ui.println(f"  3. {ui.colored('Laisser arretee', 'dim')} {source_vm}")
    ui.println()

    plan_confirm = ui.ask_input(ui.colored("  Confirmer ce plan ? [O/n] ", "yellow")).strip().lower()
    if plan_confirm in ("n", "non", "no"):
        ui.print_warning("Plan annule.")
        return "Plan annule."

    # --- Etape 1: Arreter la VM source ---
    ui.println()
    ui.print_info(f"Etape 1/{total_steps}: Arret de {source_vm}")

    vm_state = ctx.hestia_execute("fedora.vm_status", {"vm_name": source_vm})
    if vm_state.success:
        ui.println(f"\n{ui.colored('Etat actuel:', 'cyan')}")
        for line in vm_state.content.split("\n")[:5]:
            if line.strip():
                ui.println(f"  {line}")
        ui.println()

    stop_confirm = ui.confirm_action(
        tool_name="vm_stop",
        arguments={"vm_name": source_vm},
        vocal_mode=ctx.vocal,
        voice=ctx.voice,
    )
    if stop_confirm == "modify":
        ui.print_warning("Modification non disponible pour cette etape.")
        stop_confirm = False

    if not stop_confirm:
        ui.print_warning(f"Arret de {source_vm} annule. Clone annule.")
        return f"Clone annule (arret de {source_vm} refuse)."

    ui.print_info(f"Arret de {source_vm} en cours...")
    stop_result = ctx.execute_action("vm_stop", {"vm_name": source_vm})

    if stop_result.error or not (stop_result.execution_result and stop_result.execution_result.success):
        ui.print_error(f"Echec de l'arret de {source_vm}")
        return f"Impossible d'arreter {source_vm}: {stop_result.error}"

    ui.print_success(f"{source_vm} arretee")
    messages.append(f"{source_vm} arretee")

    # --- Etape 2: Cloner la VM ---
    ui.println()
    ui.print_info(f"Etape 2/{total_steps}: Clonage")

    ui.println(f"\n{ui.colored('Recapitulatif du clonage:', 'cyan')}")
    ui.println(f"  VM source     : {ui.colored(source_vm, 'bold')} ({ui.colored('arretee', 'green')})")
    ui.println(f"  VM destination: {ui.colored(new_vm_name, 'bold')}")
    ui.println()

    clone_confirm = ui.confirm_action(
        tool_name="vm_clone",
        arguments={"source_vm": source_vm, "new_vm_name": new_vm_name},
        vocal_mode=ctx.vocal,
        voice=ctx.voice,
    )

    if clone_confirm == "modify":
        ui.print_info("Modification des parametres du clone...")
        ui.println()
        new_name_input = ui.ask_input(f"  new_vm_name [{new_vm_name}]: ").strip()
        if new_name_input:
            new_vm_name = new_name_input
        clone_confirm = ui.confirm_action(
            tool_name="vm_clone",
            arguments={"source_vm": source_vm, "new_vm_name": new_vm_name},
            vocal_mode=ctx.vocal,
            voice=ctx.voice,
        )

    if not clone_confirm or clone_confirm == "modify":
        ui.print_warning("Clone annule.")
        messages.append("Clone annule par l'utilisateur")

        if restart_after:
            restart_confirm = ui.ask_input(
                ui.colored(f"\n  Redemarrer {source_vm} quand meme ? [O/n] ", "yellow")
            ).strip().lower()
            if restart_confirm not in ("n", "non", "no"):
                ui.print_info(f"Redemarrage de {source_vm}...")
                restart_result = ctx.execute_action("vm_start", {"vm_name": source_vm})
                if restart_result.execution_result and restart_result.execution_result.success:
                    messages.append(f"{source_vm} redemarree")
        return "\n".join(messages)

    ui.print_info(f"Clonage de {source_vm} vers {new_vm_name} en cours...")
    clone_result = ctx.execute_action(
        "vm_clone",
        {"source_vm": source_vm, "new_vm_name": new_vm_name},
    )

    if clone_result.error or not (clone_result.execution_result and clone_result.execution_result.success):
        ui.print_error("Echec du clonage")
        messages.append(f"Echec du clonage: {clone_result.error}")

        if restart_after:
            ui.print_info(f"Redemarrage de {source_vm}...")
            restart_result = ctx.execute_action("vm_start", {"vm_name": source_vm})
            if restart_result.execution_result and restart_result.execution_result.success:
                messages.append(f"{source_vm} redemarree")

        final_message = "\n".join(messages)
        ui.print_tool_result(final_message, False)
        return final_message

    ui.print_success(f"Clone {new_vm_name} cree avec succes")
    messages.append(f"Clone {new_vm_name} cree")

    if ctx.notify_discord:
        ctx.notify_discord("vm_clone", {"source_vm": source_vm, "new_vm_name": new_vm_name}, clone_result)

    # --- Etape 3: Redemarrer la VM source ---
    if restart_after:
        ui.println()
        ui.print_info(f"Etape 3/3: Redemarrage de {source_vm}")

        restart_confirm = ui.ask_input(
            ui.colored(f"\n  Redemarrer {source_vm} maintenant ? [O/n] ", "yellow")
        ).strip().lower()

        if restart_confirm not in ("n", "non", "no"):
            ui.print_info(f"Redemarrage de {source_vm} en cours...")
            restart_result = ctx.execute_action("vm_start", {"vm_name": source_vm})

            if restart_result.execution_result and restart_result.execution_result.success:
                ui.print_success(f"{source_vm} redemarree")
                messages.append(f"{source_vm} redemarree")
            else:
                ui.print_warning(f"Echec du redemarrage de {source_vm}")
                messages.append(f"Echec redemarrage de {source_vm}")
        else:
            ui.print_info(f"{source_vm} reste arretee")
            messages.append(f"{source_vm} reste arretee")
    else:
        messages.append(f"{source_vm} reste arretee")

    final_message = "\n".join(messages)
    ui.println()
    ui.print_tool_result(final_message, True)
    return final_message
