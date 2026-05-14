"""Lyra Rules - Registre de detection des outils MCP.

Chaque module expose detect(query) -> Optional[EphaistosAnalysis].
L'ordre dans _REGISTRY est identique a l'ancien _rule_based_detect() dans pipeline.py.
Premier match gagne.
"""

from typing import Optional

from .backup import detect as _backup
from .vm import detect as _vm
from .tracking import detect as _tracking
from .hue import detect as _hue
from .tv import detect as _tv
from .denon import detect as _denon
from .screen_manager import detect as _screen_manager
from .ironman import detect as _ironman

# Ordre critique - meme logique que l'ancien _rule_based_detect()
_REGISTRY = [
    _ironman,        # IRONMAN: triggers exacts "je suis iron man" etc. (priorite max, aucune collision)
    _backup,         # BACKUP: verifie AVANT vm (collision "verifie backup" / "verifie VM")
    _vm,             # VM: clone, copy, verify, start, stop, destroy, exec, snapshot, status, export, import
    _tracking,       # TRACKING: dashboard, taches en cours
    _hue,            # HUE: scenes AVANT vm_start ("lance la scene X" sinon vm_start)
    _tv,             # TV: power, apps, volume, ambilight
    _denon,          # DENON: power, mute, volume, input (verifie AVANT TV sur "volume")
    _screen_manager, # SCREEN-MANAGER: open_app, open_url, list_screens, list_apps, setup, update
]


def detect(query: str):
    """Detection par regles : premier module qui match gagne."""
    for fn in _REGISTRY:
        result = fn(query)
        if result is not None:
            return result
    return None
