"""
Lyra Core - Types et constantes partagees.

Centralise les enumerations, dataclasses et constantes
utilisees par le pipeline et ses modules derives.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..hestia.executor import ExecutionResult


class QueryType(Enum):
    """Type de requete utilisateur."""
    KNOWLEDGE = "knowledge"  # Question sur le systeme
    ACTION = "action"        # Demande d'action MCP


@dataclass
class PipelineResult:
    """Resultat du pipeline."""
    response: str                        # Reponse a afficher
    query_type: QueryType               # Type de requete
    tool_call: Optional[dict] = None    # Tool call si action
    pending_args: list = field(default_factory=list)  # Args manquants
    executed: bool = False              # Action executee?
    error: Optional[str] = None
    execution_result: Optional["ExecutionResult"] = None
    analysis_meta: Optional[dict] = None  # {"source": "rule|ephaistos", "confidence": float, "reasoning": str}


# Descriptions des serveurs MCP
SERVER_DESCRIPTIONS: dict[str, str] = {
    "fedora": "VM KVM et backups",
    "tv": "Controle TV Philips",
    "hue": "Lumieres Philips Hue",
    "catt": "Cast video",
    "screen-manager": "Gestion multi-ecrans et applications",
}

# Mots-cles pour pre-filtrage par categorie/serveur
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "hue": [
        "lumiere", "lumieres", "lampe", "lampes", "eclairage",
        "hue", "ampoule", "ampoules", "philips hue", "luminosite",
        "couleur", "rgb", "scene", "ambiance", "intensite", "brightness"
    ],
    "tv": [
        "tv", "tele", "television", "volume", "chaine", "ecran",
        "ambilight", "philips tv", "telecommande", "hdmi",
        "netflix", "app", "application"
    ],
    "catt": [
        "cast", "caste", "caster", "chromecast", "diffuser", "diffuse",
        "streamer", "video", "film", "musique", "url"
    ],
    "fedora": [
        "vm", "vms", "machine virtuelle", "serveur", "backup",
        "sauvegarde", "snapshot", "clone", "kvm", "virtuel"
    ],
    "screen-manager": [
        "ecran", "ecrans", "moniteur", "moniteurs", "display", "affichage",
        "multi-ecran", "application", "app", "apps", "bureau", "tele",
        "open_app", "open_url", "list_screens", "list_apps", "setup_screens",
    ],
}

# Mots-cles pour pre-filtrage par type d'outil (plus specifique)
TOOL_TYPE_KEYWORDS: dict[str, list[str]] = {
    "backup": ["backup", "sauvegarde", "sauvegarder", "sauvegardes"],
    "vm": ["vm", "vms", "machine", "virtuelle", "virtuelles"],
}

# Verbes d'action (francais)
ACTION_VERBS: list[str] = [
    "demarre", "arrete", "clone", "supprime", "cree", "liste",
    "status", "snapshot", "backup", "restore", "verifie",
    "allume", "eteint", "monte", "baisse", "active", "desactive",
    "lance", "execute", "copie", "detruit", "montre", "affiche",
    "fais", "fait", "sauvegarde", "donne", "dis"
]

# Patterns de questions de connaissance EXPLICITES (vraies questions)
# Ces patterns indiquent que l'utilisateur veut une explication, pas une action
EXPLICIT_KNOWLEDGE_PATTERNS: list[str] = [
    "qu'est-ce que", "qu'est ce que", "c'est quoi", "c est quoi",
    "comment fonctionne", "comment marche", "comment faire",
    "comment on", "comment je", "comment demarrer", "comment arreter",
    "comment cloner", "comment sauvegarder", "comment restaurer",
    "explique", "decris", "definition de", "a quoi sert",
    "pourquoi", "difference entre"
]

# Patterns de questions qui PEUVENT etre des actions implicites
# Ex: "quels sont mes vm" -> ACTION, pas KNOWLEDGE
KNOWLEDGE_PATTERNS: list[str] = [
    "qu'est-ce que", "c'est quoi", "comment", "pourquoi",
    "explique", "decris", "qu'est ce", "quoi", "quel est",
    "quelle est", "quels sont", "quelles sont", "definition"
]

# Entites qui indiquent une action implicite meme avec un mot interrogatif
# "quels sont mes vm" -> contient "vm" -> ACTION
ACTION_ENTITIES: list[str] = [
    # VMs
    "vm", "vms", "machine", "machines", "virtuelle", "virtuelles",
    # Backups
    "backup", "backups", "sauvegarde", "sauvegardes",
    # TV
    "tv", "tele", "television", "volume", "chaine",
    # Hue / Lumieres
    "lumiere", "lumieres", "lampe", "lampes", "hue", "ambilight",
    # Cast
    "cast", "chromecast", "video", "youtube",
    # Etats
    "status", "statut", "etat", "etats",
    # Screen
    "ecran", "moniteur", "display",
]
