"""
Lyra Core - WorkflowContext.

Injection de dependances pour les workflows metier.
Passe les composants du pipeline aux handlers sans couplage fort.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

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
