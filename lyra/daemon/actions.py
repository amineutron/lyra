"""
Lyra Daemon - Traitement d'une requete cote serveur.

Port UI-agnostique de run_one_shot()/handle_action() de main_rag.py :
toute l'interface passe par RemoteUI, la logique metier est identique.

Codes de sortie (parite avec run_one_shot) :
    0 = ok, 1 = erreur, 2 = annule, 3 = args manquants (one-shot uniquement)
"""

from __future__ import annotations

from ..core.constants import PERFORMANCE_TOOLS, is_dangerous_tool
from ..core.fastpath import try_fast_path_rules
from ..core.types import QueryType
from ..core.workflows.context import ExecContext
from ..core.workflows.vm_clone_exec import handle_vm_clone_with_stop
from ..core.workflows.vm_snapshot_exec import handle_snapshot_restore_with_safety
from ..utils.error_log import is_execution_error, lyra_error_message, write_error_log
from .remote_ui import RemoteUI, RequestCancelled


def _actual(pipeline):
    """Pipeline V2 sous-jacent (EnhancedPipeline wrappe V2)."""
    return pipeline._pipeline_v2 if hasattr(pipeline, "_pipeline_v2") else pipeline


def _should_skip_confirmation(tool_name: str, mode: str) -> bool:
    """Parite avec main_rag.should_skip_confirmation."""
    if is_dangerous_tool(tool_name):
        return False
    return mode == "performance" and tool_name in PERFORMANCE_TOOLS


def run_request(
    pipeline,
    task_manager,
    text: str,
    rui: RemoteUI,
    session_id: str = "default",
    mode: str = "default",
    yes: bool = False,
    interactive: bool = False,
    webhook_url: str = "",
    use_fast_path: bool = True,
) -> int:
    """Traite une requete complete : process -> confirmation -> execution.

    Args:
        pipeline: EnhancedPipeline (ou Pipeline V2)
        task_manager: BackgroundTaskManager du demon
        text: Requete utilisateur
        rui: RemoteUI du client
        session_id: Session de conversation (isolation multi-clients)
        mode: default | performance
        yes: Auto-confirmation (sauf outils dangereux)
        interactive: True pour un client REPL (les clarifications multi-tours
            restent en session au lieu de sortir en code 3)
        webhook_url: Webhook Discord pour les taches async
        use_fast_path: Tenter les regles statiques avant le pipeline

    Returns:
        Code de sortie (0/1/2/3)
    """
    v2 = _actual(pipeline)

    fast_analysis = try_fast_path_rules(text) if use_fast_path else None
    if fast_analysis is not None and hasattr(pipeline, "process_precomputed"):
        with v2.session_scope(session_id):
            result = pipeline.process_precomputed(text, fast_analysis)
    else:
        result = pipeline.process(text, rag_step_callback=rui.progress,
                                  session_id=session_id)

    for warning in getattr(result, "warnings", []):
        rui.warning(warning)

    # Cas 1 : question de connaissance -> reponse directe
    if result.query_type == QueryType.KNOWLEDGE:
        rui.lyra(result.response)
        return 0

    # Cas 2 : arguments manquants
    if result.pending_args:
        rui.lyra_tag(result.response)
        # Ligne DETERMINISTE en complement : le texte LLM ci-dessus peut
        # halluciner (ex: "snapshot test-vm" sorti des exemples du 0.5b).
        # L'utilisateur doit toujours savoir precisement quoi fournir.
        _labels = {"name": "nom de la nouvelle VM (la source est ton PC)",
                   "source_vm": "VM source", "new_vm_name": "nom de la nouvelle VM",
                   "vm_name": "nom de la VM", "snapshot_name": "nom du snapshot"}
        _need = ", ".join(_labels.get(a, a) for a in result.pending_args)
        if result.pending_args == ["name"]:
            # clone systeme : la reponse attendue est juste le nom
            rui.info(f"Il me manque : {_need}. Reponds juste le nom, "
                     f"ex: \u00ab test-vm \u00bb")
        else:
            rui.info(f"Il me manque : {_need}. "
                     f"Ex: \u00ab la source est X et le nom Y \u00bb")
        if interactive:
            return 0  # la session garde le pending, le prochain tour complete
        rui.warning(f"One-shot: arguments manquants ({', '.join(result.pending_args)})")
        rui.warning("Relancez avec la requete complete ou utilisez le mode interactif.")
        return 3

    # Cas 3 : action prete -> confirmation puis execution
    if result.tool_call:
        return _run_action(pipeline, v2, task_manager, result, rui,
                           session_id=session_id, mode=mode, yes=yes,
                           fast=fast_analysis is not None,
                           webhook_url=webhook_url)

    # Cas 4 : pas de match -> reponse directe
    rui.lyra(result.response)
    return 0


def _run_action(pipeline, v2, task_manager, result, rui: RemoteUI, *,
                session_id: str, mode: str, yes: bool, fast: bool,
                webhook_url: str) -> int:
    tool_name = result.tool_call["name"]
    arguments = result.tool_call["arguments"]

    # Workflows speciaux multi-interactions (clone avec arret / revert snapshot)
    if tool_name == "vm_clone_with_stop" or (
        "vm_snapshot" in tool_name and arguments.get("action") == "revert"
    ):
        exec_ctx = ExecContext(
            ui=rui.uic(),
            execute_action=lambda t, a, **kw: v2.execute_action(
                t, a, session_id=session_id, **kw),
            hestia_execute=v2._hestia.execute,
            vocal=False,   # le rendu vocal est une affaire de client
            voice=None,
            notify_discord=lambda *a, **kw: None,
        )
        try:
            with v2.session_scope(session_id):
                if tool_name == "vm_clone_with_stop":
                    message = handle_vm_clone_with_stop(arguments, exec_ctx)
                else:
                    message = handle_snapshot_restore_with_safety(arguments, exec_ctx)
            rui.lyra(message)
            return 0
        except RequestCancelled:
            raise

    rui.lyra(result.response)

    is_dangerous = is_dangerous_tool(tool_name)
    skip_confirm = _should_skip_confirmation(tool_name, mode)

    if not skip_confirm and not (yes and not is_dangerous):
        rui.tool_call(tool_name, arguments)
        # meme prompt explicite que remote_ui.confirm_action (outil + cible,
        # mise en avant destructive) — les deux chemins etaient incoherents
        from .remote_ui import build_confirm_prompt
        prompt, _danger = build_confirm_prompt(tool_name, arguments)
        if not is_dangerous:
            prompt += " [O/n]"
        answer = rui.ask("confirm", prompt,
                         {"tool": tool_name, "arguments": arguments,
                          "danger": is_dangerous}).lower()
        confirmed = (answer in ("o", "oui") if is_dangerous
                     else answer in ("", "o", "oui"))
        if not confirmed:
            rui.warning("Action annulee.")
            return 2

    # Operations async (longues) -> tache en arriere-plan
    if task_manager and v2._hestia.is_async_tool(tool_name):
        async_info = v2._hestia.get_async_info(tool_name)
        task_id = task_manager.launch_task(
            tool_name=tool_name,
            arguments=arguments,
            description=async_info["description"],
            estimated_time=async_info["estimated_time"],
            webhook_url=webhook_url,
        )
        rui.success(f"Operation lancee en arriere-plan (task: {task_id[-6:]})")
        return 0

    # Execution synchrone
    exec_result = v2.execute_action(tool_name, arguments,
                                    skip_lyra_format=fast,
                                    session_id=session_id)

    has_error = is_execution_error(exec_result)
    if exec_result.executed:
        rui.tool_result(exec_result.response, success=not has_error,
                        raw_error=exec_result.error if has_error else None)
    else:
        rui.tool_result(exec_result.response, success=False,
                        raw_error=exec_result.error)
        has_error = True

    if has_error:
        log_path = write_error_log(tool_name, arguments, exec_result)
        rui.error(lyra_error_message(log_path))
        return 1
    return 0
