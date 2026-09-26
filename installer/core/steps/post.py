"""Etape finale : repertoires, connectivite des devices, reindexation RAG."""
from __future__ import annotations

import socket
from pathlib import Path

import requests

from ..catalog import resolve_placeholders
from ..events import Output
from ..pipeline import StepContext
from ..runner import run


def check_device(check: dict, timeout: float = 3.0) -> bool:
    """Test de connectivite declaratif (http | tcp). Logique pure hors I/O."""
    if check["type"] == "http":
        try:
            requests.get(check["url"], timeout=timeout)
            return True
        except requests.RequestException:
            return False
    if check["type"] == "tcp":
        try:
            with socket.create_connection(
                    (check["host"], int(check["port"])), timeout=timeout):
                return True
        except OSError:
            return False
    return False


def run_step(ctx: StepContext) -> None:
    lyra = ctx.state.lyra_dir

    for d in (Path.home() / ".lyra" / "logs" / "errors",
              lyra / "logs", lyra / "data"):
        d.mkdir(parents=True, exist_ok=True)

    # Connectivite : avertit sans bloquer (le device peut etre eteint)
    mapping = {"lyra": str(lyra), "home": str(Path.home())}
    for mcp in ctx.mcps:
        if not mcp.check:
            continue
        local_map = dict(mapping)
        local_map.update({k: str(v) for k, v in
                          (ctx.state.device_config.get(mcp.id) or {}).items()})
        try:
            check = resolve_placeholders(mcp.check, local_map)
        except KeyError:
            continue
        ok = check_device(check)
        status = "joignable" if ok else "INJOIGNABLE (verifie le device)"
        ctx.emit(Output(f"{mcp.name} : {status}"))

    # Reindexation RAG des specs MCP
    python = str(ctx.state.venv_python)
    for label, cmd in rag_index_commands(lyra, python):
        ctx.emit(Output(label))
        run(cmd, ctx.emit, step_id=ctx.step_id, check=False)


def rag_index_commands(lyra: Path, python: str) -> list[tuple[str, list[str]]]:
    """Commandes d'indexation RAG, dans l'ordre de docs/dev/INDEX_RAG.md.

    La v2 interroge les serveurs MCP ; la v3 (lue par le pipeline de production)
    en derive. Avant 2026-09-26 seule la v2 etait construite : sur une
    installation neuve, les collections v3 restaient vides et le RAG ne
    proposait aucun outil hors regles."""
    scripts = lyra / "scripts"
    v2 = scripts / "reindex_mcp_rag_optimized.py"
    if not v2.exists():
        legacy = scripts / "index_mcp_specs.py"
        return [("Reindexation RAG des specs MCP...", [python, str(legacy)])] if legacy.exists() else []
    commands = [("Reindexation RAG des specs MCP (v2)...", [python, str(v2)])]
    v3 = scripts / "index_rag_3tier.py"
    if v3.exists():
        commands.append(("Index RAG 3 niveaux (v3, derive de la v2)...", [python, str(v3), "--clear"]))
    return commands
