"""Etape : demon Lyra en service systemd user + alias client.

Templatise install/lyra-daemon.service : chemins substitues, PATH
reconstruit avec le venv en tete (piege documente : les MCP spawnes avec
'command: python' doivent resoudre le python du venv).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..events import Output
from ..pipeline import StepContext
from ..runner import run

_DEV_LYRA = "/home/amineutron/dev/lyra"


def render_service(template: str, lyra_dir: str, home: str) -> str:
    """Substitution des chemins machine-de-dev (logique pure, testee)."""
    lines = []
    for line in template.splitlines():
        if line.startswith("Environment=PATH="):
            adb = shutil.which("adb")
            parts = [f"{lyra_dir}/.venv/bin", f"{home}/.local/bin",
                     "/usr/local/bin", "/usr/bin", "/bin"]
            if adb:
                adb_dir = str(Path(adb).parent)
                if adb_dir not in parts:
                    parts.append(adb_dir)
            line = "Environment=PATH=" + ":".join(parts)
        else:
            line = line.replace(_DEV_LYRA, lyra_dir)
        lines.append(line)
    return "\n".join(lines) + "\n"


def run_step(ctx: StepContext) -> None:
    lyra = ctx.state.lyra_dir
    template = lyra / "install" / "lyra-daemon.service"
    if not template.exists():
        raise RuntimeError(f"{template} introuvable")

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    content = render_service(template.read_text(encoding="utf-8"),
                             str(lyra), str(Path.home()))
    (unit_dir / "lyra-daemon.service").write_text(content, encoding="utf-8")

    run(["systemctl", "--user", "daemon-reload"], ctx.emit, step_id=ctx.step_id)
    run(["systemctl", "--user", "enable", "--now", "lyra-daemon"],
        ctx.emit, step_id=ctx.step_id)
    ctx.emit(Output("Demon lyra-daemon actif (journalctl --user -u lyra-daemon -f)"))

    if ctx.state.install_smoke_timer:
        for name in ("lyra-mcp-smoke.service", "lyra-mcp-smoke.timer"):
            src = lyra / "install" / name
            if src.exists():
                (unit_dir / name).write_text(
                    src.read_text(encoding="utf-8").replace(_DEV_LYRA, str(lyra)),
                    encoding="utf-8")
        run(["systemctl", "--user", "daemon-reload"], ctx.emit, step_id=ctx.step_id)
        run(["systemctl", "--user", "enable", "--now", "lyra-mcp-smoke.timer"],
            ctx.emit, step_id=ctx.step_id, check=False)

    # Client leger : executable dans ~/.local/bin (marche dans tous les
    # shells, meme non-interactifs/non-bash -- une alias .bashrc seule
    # echoue silencieusement en sh/dash ou en shell non-interactif).
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    shim = local_bin / "lyra"
    shim.write_text(
        f"#!/bin/sh\nexec \"{lyra}/.venv/bin/python\" -m lyra.client \"$@\"\n",
        encoding="utf-8")
    shim.chmod(0o755)
    ctx.emit(Output(f"Executable 'lyra' installe dans {shim}"))

    # Alias .bashrc en complement (confort bash interactif)
    bashrc = Path.home() / ".bashrc"
    alias = f"\nalias lyra='{lyra}/.venv/bin/python -m lyra.client'\n"
    text = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
    if "alias lyra=" not in text:
        with open(bashrc, "a", encoding="utf-8") as f:
            f.write(alias)
        ctx.emit(Output("Alias 'lyra' ajoute au .bashrc"))
