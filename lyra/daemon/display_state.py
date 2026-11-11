"""
Lyra Daemon - Etat reel pour le `display` des confirmations.

Reutilise les lectures que Lyra fait deja avant une confirmation
(core/validation.get_vm_state, get_hue_groups) et tv.get_state (lecture seule,
dans PERFORMANCE_TOOLS). AUCUNE action : uniquement des lectures, bornees par
un timeout court ; au moindre echec on rend None et la confirmation continue.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from typing import Any, Optional

from ..core.validation import get_hue_groups, get_vm_state

logger = logging.getLogger(__name__)

STATE_TIMEOUT = 1.5   # secondes ; au-dela, state=None
_VM_TARGET_KEYS = ("vm_name", "source_vm", "vm", "name")
_VOLUME_RE = re.compile(r"volume\D{0,12}(\d{1,3})", re.IGNORECASE)
_MUTE_RE = re.compile(r"mute[d]?\W{0,4}(true|false|on|off|oui|non|yes|no)", re.IGNORECASE)


def _parse_tv_state(content: Any) -> Optional[dict]:
    state: dict = {}
    data = None
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        pass
    if isinstance(data, dict):
        volume = data.get("volume")
        if isinstance(volume, int) and not isinstance(volume, bool):
            state["volume"] = volume
        for key in ("muted", "mute"):
            if isinstance(data.get(key), bool):
                state["muted"] = data[key]
                break
    elif isinstance(content, str):
        found = _VOLUME_RE.search(content)
        if found:
            state["volume"] = int(found.group(1))
        mute = _MUTE_RE.search(content)
        if mute:
            state["muted"] = mute.group(1).lower() in ("true", "on", "oui", "yes")
    return state or None


def _read_state(hestia: Any, tool: str, arguments: dict) -> Optional[dict]:
    parts = tool.split(".")
    server, short = (parts[0] if len(parts) > 1 else ""), parts[-1]
    if server == "tv" or short.startswith("tv_"):
        if not (short.startswith("volume") or short == "mute"):
            return None
        result = hestia.execute("tv.get_state", {})
        return _parse_tv_state(result.content) if result.success else None
    if short.startswith("vm_"):
        name = next((arguments[k] for k in _VM_TARGET_KEYS
                     if isinstance(arguments.get(k), str) and arguments[k]), None)
        if name is None:
            return None
        info = get_vm_state(hestia, name)
        return {"vms": [{"name": name,
                         "state": "running" if info.get("running") else "stopped"}]}
    if (server == "hue" or short.startswith("hue_")) and "light_id" not in arguments:
        groups = get_hue_groups(hestia)
        if not groups:
            return None
        return {"groups": {gid: {"name": name} for gid, name in groups.items()}}
    return None


def fetch_display_state(hestia: Any, tool: str, arguments: Optional[dict],
                        timeout: float = STATE_TIMEOUT) -> Optional[dict]:
    """Etat courant utile a `build_display`, ou None (echec, lenteur, inconnu).

    La lecture tourne dans un thread daemon : un MCP lent ne bloque jamais la
    confirmation au-dela de `timeout`.
    """
    if hestia is None or not isinstance(tool, str) or not tool:
        return None
    box: list[Optional[dict]] = []

    def work() -> None:
        try:
            box.append(_read_state(hestia, tool, arguments or {}))
        except Exception:  # noqa: BLE001 - decoratif, jamais bloquant
            logger.debug("lecture d'etat impossible pour %s", tool, exc_info=True)

    thread = threading.Thread(target=work, name="display-state", daemon=True)
    thread.start()
    thread.join(timeout)
    return box[0] if box and not thread.is_alive() else None


def make_state_provider(hestia: Any) -> Callable[[str, dict], Optional[dict]]:
    return lambda tool, arguments: fetch_display_state(hestia, tool, arguments)
