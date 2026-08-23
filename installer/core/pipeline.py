"""Pipeline declaratif d'installation.

Une etape = StepDef(id, label, fn, condition). Le pipeline emet des
evenements StepChange/Output/Progress/Result ; les frontaux ne font que
les rendre. En mode demo, chaque etape est simulee (memes ids, memes
labels — pas de logs figes divergents comme dans l'ancien installeur).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .catalog import McpDef
from .events import AskBroker, Emit, Output, Result, StepChange
from .state import InstallState

StepFn = Callable[["StepContext"], None]


@dataclass(frozen=True)
class StepContext:
    state: InstallState
    emit: Emit
    broker: AskBroker
    mcps: tuple[McpDef, ...]        # entrees du catalogue selectionnees
    step_id: str = ""

    def with_step(self, step_id: str) -> "StepContext":
        return StepContext(state=self.state, emit=self.emit,
                           broker=self.broker, mcps=self.mcps,
                           step_id=step_id)


@dataclass(frozen=True)
class StepDef:
    id: str
    label: str
    fn: StepFn
    condition: Callable[[InstallState], bool] = lambda _s: True


def build_pipeline(state: InstallState, selected: tuple[McpDef, ...]) -> tuple[StepDef, ...]:
    """Construit la liste ordonnee des etapes selon l'etat."""
    from .steps import (clone, config, mcps, ollama, packages, piper, post,
                        systemd, venv)

    steps: list[StepDef] = [
        StepDef("system", "Paquets systeme", packages.run_step),
        StepDef("clone", "Clone du repo Lyra", clone.run_step),
        StepDef("venv", "Environnement Python", venv.run_venv),
        StepDef("pip", "Dependances pip", venv.run_pip),
        StepDef("piper", "Piper TTS", piper.run_piper),
        StepDef("voice", "Voix francaise", piper.run_voice),
        StepDef("ollama", "Ollama", ollama.run_ollama),
        StepDef("models", "Modeles LLM", ollama.run_models,
                condition=lambda s: not s.skip_models),
    ]

    for mcp in selected:
        if not mcp.installable:
            continue
        steps.append(StepDef(
            f"mcp_{mcp.id}", f"MCP {mcp.name}",
            mcps.make_step(mcp),
        ))

    steps += [
        StepDef("config", "Configuration", config.run_step),
        StepDef("daemon", "Demon Lyra (systemd)", systemd.run_step),
        StepDef("post", "Verifications finales", post.run_step),
    ]
    return tuple(steps)


def run_pipeline(state: InstallState, selected: tuple[McpDef, ...],
                 emit: Emit, broker: AskBroker,
                 pipeline: Optional[Iterable[StepDef]] = None) -> bool:
    """Execute le pipeline. Retourne True si tout est OK."""
    steps = tuple(pipeline) if pipeline is not None else build_pipeline(state, selected)
    ctx = StepContext(state=state, emit=emit, broker=broker, mcps=selected)

    for step in steps:
        if not step.condition(state):
            emit(StepChange(step.id, "skip"))
            continue
        emit(StepChange(step.id, "run"))
        t0 = time.monotonic()
        try:
            if state.demo:
                _demo_step(step, ctx)
            else:
                step.fn(ctx.with_step(step.id))
        except Exception as exc:  # noqa: BLE001 — une erreur = arret propre
            emit(StepChange(step.id, "err", detail=str(exc)))
            emit(Result(ok=False, error=f"{step.label} : {exc}"))
            return False
        emit(StepChange(step.id, "ok", elapsed=time.monotonic() - t0))

    emit(Result(ok=True))
    return True


def _demo_step(step: StepDef, ctx: StepContext) -> None:
    """Simulation : memes etapes que le reel, commandes remplacees."""
    emit = ctx.emit
    emit(Output(f"[demo] {step.label}..."))
    time.sleep(0.4)
    if step.id == "config":
        emit(Output("[demo] config.yaml genere (dry-run, rien d'ecrit)"))
    elif step.id.startswith("mcp_"):
        emit(Output(f"[demo] git clone + install simules ({step.id[4:]})"))
    time.sleep(0.2)
