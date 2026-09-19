"""Lyra Rules - Registre de detection des outils MCP.

Chaque module expose detect(query) -> Optional[EphaistosAnalysis].
L'ordre dans _REGISTRY est identique a l'ancien _rule_based_detect() dans pipeline.py.
Premier match gagne.
"""


from .backup import detect as _backup
from .catt import detect as _catt
from .denon import detect as _denon
from .hue import detect as _hue
from .ironman import detect as _ironman
from .tracking import detect as _tracking
from .tv import detect as _tv
from .vm import detect as _vm

# Ordre critique - meme logique que l'ancien _rule_based_detect()
_REGISTRY = [
    _ironman,        # IRONMAN: triggers exacts "je suis iron man" etc. (priorite max, aucune collision)
    _backup,         # BACKUP: verifie AVANT vm (collision "verifie backup" / "verifie VM")
    _catt,           # CATT: cast_stop/pause/resume/youtube/volume/seek. AVANT vm, sinon
                     # "arrete la diffusion" tombe sur vm_stop. Le module existait mais
                     # n'etait pas enregistre : aucune commande de cast n'avait de regle.
    _vm,             # VM: clone, copy, verify, start, stop, destroy, exec, snapshot, status, export, import
    _tracking,       # TRACKING: dashboard, taches en cours
    _hue,            # HUE: scenes AVANT vm_start ("lance la scene X" sinon vm_start)
    _tv,             # TV: power, apps, volume, ambilight
    _denon,          # DENON: power, mute, volume, input (verifie AVANT TV sur "volume")
    # SCREEN-MANAGER (_screen_manager) retire le 2026-09-19 : le serveur n'est ni sur
    # le disque ni dans config.yaml ; dernier du registre, il attrapait les phrases
    # "ecran/application" et renvoyait un outil inexistant (lyra#24). A remettre
    # avec le serveur.
]


def detect(query: str):
    """Detection par regles : premier module qui match gagne."""
    for fn in _REGISTRY:
        result = fn(query)
        if result is not None:
            return result
    return None
