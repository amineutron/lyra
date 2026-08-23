"""Etape : paquets systeme (dnf/apt/pacman)."""
from __future__ import annotations

from ..events import Output
from ..pipeline import StepContext
from ..runner import run


def run_step(ctx: StepContext) -> None:
    distro = ctx.state.distro
    if not distro.supported:
        raise RuntimeError(
            f"distribution non supportee : {distro.pretty_name} "
            "(familles gerees : fedora, debian, arch)")

    ctx.emit(Output(f"Distribution : {distro.pretty_name} (famille {distro.family})"))
    ok = ctx.broker.confirm(
        "Installer les paquets systeme (necessite sudo) ?", default=True)
    if not ok:
        raise RuntimeError("installation des paquets refusee")

    run(distro.install_cmd + distro.packages, ctx.emit, step_id=ctx.step_id)
