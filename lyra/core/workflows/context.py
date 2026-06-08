"""
Lyra Core - WorkflowContext / UIContext / ExecContext.

Injection de dependances pour les workflows metier.

- WorkflowContext : pipeline-level handlers (vm_clone, vm_export, vm_snapshot...)
- UIContext       : fonctions UI injectees dans les handlers d'execution
- ExecContext     : execution-level handlers (clone+stop, snapshot restore...)
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ...hestia.executor import HestiaExecutor
from ...models.lyra_voice import LyraVoice
from ...models.ephaistos import Ephaistos
from ...rag.session_memory import SessionMemory


@dataclass
class WorkflowContext:
    """Contexte partage entre le pipeline et les workflows metier.

    Construit par Pipeline.initialize() et passe aux handlers
    de workflows (vm_clone, vm_export, vm_stop, vm_start, vm_snapshot).
    """
    hestia: HestiaExecutor
    lyra: LyraVoice
    ephaistos: Ephaistos
    session: SessionMemory
    tts_mode: bool
    # Callbacks pipeline (injectes pour eviter couplage direct)
    prepare_execution: Optional[Callable] = field(default=None, repr=False)
    route_query: Optional[Callable] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Contexte d'execution (handlers post-pipeline avec interaction terminal)
# ---------------------------------------------------------------------------

@dataclass
class UIContext:
    """Fonctions d'interface utilisateur injectees dans les handlers d'execution.

    Encapsule modules.ui pour permettre les tests unitaires sans terminal reel.
    """
    print_info: Callable[[str], None]
    print_success: Callable[[str], None]
    print_error: Callable[[str], None]
    print_warning: Callable[[str], None]
    print_tool_result: Callable[..., None]      # (msg: str, success: bool = True)
    colored: Callable[[str, str], str]
    confirm_action: Callable[..., Any]           # (tool_name, arguments, vocal_mode, voice)
    ask_input: Callable[[str], str]              # wraps input()
    println: Callable[..., None]                 # wraps print()


@dataclass
class ExecContext:
    """Contexte d'execution pour les handlers de workflows longs.

    Distinct de WorkflowContext (qui sert les handlers pipeline).
    Utilise par vm_clone_exec et vm_snapshot_exec depuis main_rag.py.

    execute_action  : appelle un outil MCP via le pipeline (avec confirmation UI).
    hestia_execute  : appelle un outil MCP directement sur hestia (lecture d'etat).
    """
    ui: UIContext
    execute_action: Callable[[str, dict], Any]      # pipeline.execute_action
    hestia_execute: Callable[[str, dict], Any]      # hestia.execute
    vocal: bool = False
    voice: Any = field(default=None, repr=False)
    notify_discord: Optional[Callable] = field(default=None, repr=False)
