"""
Lyra Utils - Error Log.

Ecriture et formatage des logs d'erreur MCP dans ~/.lyra/logs/errors/.
"""

import random
from datetime import datetime
from pathlib import Path

ERROR_LOG_DIR = Path.home() / ".lyra" / "logs" / "errors"

_LYRA_ERROR_MESSAGES = [
    "ouuf... ca a plante. j'ai mis les details là :",
    "hmm ya eu un souci. j'ai tout logué ici :",
    "ca a pas marche... details dans le log :",
    "aie, erreur MCP. j'ai sauvegardé ca là :",
    "ca s'est pas passe comme prevu. log ici :",
]

_SENSITIVE_KEYS = frozenset({
    "password", "pass", "passwd", "token", "api_key", "webhook_url",
    "user", "username", "secret", "key", "auth", "credential",
})


def write_error_log(tool_name: str, arguments: dict, exec_result) -> Path:
    """Ecrit un log d'erreur MCP dans ~/.lyra/logs/errors/.

    Args:
        tool_name: Nom de l'outil MCP
        arguments: Arguments passes a l'outil
        exec_result: PipelineResult apres execution

    Returns:
        Path vers le fichier log cree
    """
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = tool_name.replace(".", "_").replace("/", "_")
    log_path = ERROR_LOG_DIR / f"{ts}_{safe_name}.log"

    pipeline_error = getattr(exec_result, 'error', None) or ""
    mcp_error = ""
    mcp_output = ""
    duration_ms = ""

    exec_r = getattr(exec_result, 'execution_result', None)
    if exec_r is not None:
        mcp_error = getattr(exec_r, 'error', None) or ""
        mcp_output = getattr(exec_r, 'content', None) or ""
        duration_ms = str(getattr(exec_r, 'duration_ms', ""))

    args_lines = []
    for k, v in (arguments or {}).items():
        masked = "[REDACTED]" if k.lower() in _SENSITIVE_KEYS else v
        args_lines.append(f"  {k}: {masked}")
    args_str = "\n".join(args_lines) if args_lines else "  (aucun)"

    content = (
        f"=== LYRA Error Log ===\n"
        f"Date       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Tool       : {tool_name}\n"
        f"Arguments  :\n{args_str}\n"
        f"\n"
        f"--- Erreur ---\n"
        f"Pipeline   : {pipeline_error or '(aucune)'}\n"
        f"MCP Error  : {mcp_error or '(aucune)'}\n"
        f"Duree (ms) : {duration_ms or '?'}\n"
        f"\n"
        f"--- Sortie MCP ---\n"
        f"{mcp_output or '(vide)'}\n"
    )

    log_path.write_text(content, encoding="utf-8")
    return log_path


def lyra_error_message(log_path: Path) -> str:
    """Genere un message LYRA friendly apres une erreur avec le chemin du log."""
    prefix = random.choice(_LYRA_ERROR_MESSAGES)
    return f"LYRA: {prefix}\n  {log_path}"


def is_execution_error(exec_result) -> bool:
    """Retourne True si l'execution a produit une erreur."""
    if getattr(exec_result, 'error', None):
        return True
    er = getattr(exec_result, 'execution_result', None)
    if er is not None and not getattr(er, 'success', True):
        return True
    return False
