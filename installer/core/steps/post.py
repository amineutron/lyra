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
    reindex = lyra / "scripts" / "reindex_mcp_rag_optimized.py"
    fallback = lyra / "scripts" / "index_mcp_specs.py"
    script = reindex if reindex.exists() else fallback
    if script.exists():
        ctx.emit(Output("Reindexation RAG des specs MCP..."))
        run([python, str(script)], ctx.emit, step_id=ctx.step_id, check=False)
