"""
Lyra Core - Formateurs et enrichisseurs.

Fonctions d'enrichissement des specs MCP pour le RAG francais,
enrichissement des arguments optionnels, et formatage des resultats.
"""

import json
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models._analysis import EphaistosAnalysis


# Traductions francaises pour enrichir les specs MCP dans ChromaDB/BM25
FRENCH_ENRICHMENTS: dict[str, str] = {
    # Verbes d'action
    "turn_on": "allumer allume activer active",
    "turn_off": "eteindre eteins eteint desactiver desactive fermer ferme",
    "turn_on_group": "lumieres lampes groupe toutes ensemble",
    "turn_off_group": "lumieres lampes groupe toutes ensemble",
    "start": "demarrer demarre lancer lance",
    "stop": "arreter arrete stopper stoppe",
    "create": "creer cree nouveau nouvelle",
    "delete": "supprimer supprime effacer efface detruire",
    "destroy": "detruire detruit supprimer supprime",
    "clone": "cloner clone copier copie dupliquer",
    "list": "lister liste afficher affiche montrer montre quels quelles combien donne donner",
    "get": "obtenir recuperer afficher montrer voir quels quelles",
    "set": "definir regler configurer mettre changer modifier",
    "status": "status statut etat quels quelles combien liste lister",
    "backup": "sauvegarde sauvegarder sauvegardes backup backups",
    "backup_create": "sauvegarde sauvegarder creer backup faire",
    "restore": "restaurer restaure recuperer",
    "snapshot": "snapshot instantane capture",
    "exec": "executer execute lancer lance commande cmd",
    "copy": "copier copie transferer transfert envoyer",
    "launch": "lancer lance ouvrir ouvre demarrer demarre",
    "seek": "avancer avance reculer recule sauter",
    # Objets
    "light": "lumiere lampe eclairage ampoule",
    "lights": "lumieres lampes ampoules eclairages",
    "get_all_lights": "liste lister lumieres lampes ampoules toutes quelles",
    "group": "groupe piece salle",
    "scene": "scene ambiance atmosphere",
    "brightness": "luminosite intensite baisse baisser diminue diminuer",
    "set_brightness": "luminosite intensite baisse baisser diminue diminuer lumiere lampe",
    "set_group_brightness": "luminosite intensite baisse baisser diminue diminuer lumieres lampes groupe",
    "color": "couleur",
    "volume": "volume son",
    "tv": "television tele ecran",
    "vm": "machine virtuelle vm serveur",
    "video": "video film",
    "youtube": "youtube video",
    "ambilight": "ambilight retroeclairage",
    "app": "application appli programme",
    "launch_app": "lancer lance ouvrir ouvre netflix youtube spotify app application",
    "vm_copy": "copier copie fichier fichiers transferer scp",
    # VM specifiques
    "vm_snapshot": "snapshot instantane capture sauvegarde etat",
    # Listing HUE
    "get_all_scenes": "liste lister scenes ambiances quelles",
    "get_all_groups": "liste lister groupes pieces quels",
    # TV power + ambilight + YouTube
    "power_on": "allumer allume demarrer demarre reveiller reveille ouvrir",
    "power_off": "eteindre eteins arreter arrete fermer veille standby",
    "ambilight_on": "allumer allume activer active ambilight retroeclairage",
    "ambilight_off": "eteindre eteins desactiver desactive ambilight",
    "ambilight_color": "couleur ambilight retroeclairage bleu rouge vert violet mettre changer",
    "youtube_video": "youtube video jouer joue url lien youtu diffuser",
    # HUE complementaire
    "turn_on_light": "allumer allume lumiere lampe ampoule chevet bureau salon",
    "set_color_rgb": "couleur rouge vert bleu violet orange jaune rose blanc ambiance mettre changer",
    # Screen-manager
    "open_app": "ouvrir lancer demarrer afficher application app programme ecran moniteur bureau",
    "open_url": "ouvrir afficher naviguer url lien site web ecran moniteur tele affichage",
    "list_screens": "liste lister ecrans affichages moniteurs displays quels combien disponibles",
    "list_apps": "liste lister applications applis programmes logiciels quelles disponibles",
    "setup_screens": "configurer parametrer setup detecter initialiser ecrans moniteurs displays",
    "update_screen_config": "modifier renommer changer alias nom ecran moniteur index",
}

# Descriptions francaises des serveurs MCP pour l'enrichissement
_SERVER_NAMES: dict[str, str] = {
    "hue": "philips hue lumieres lampes eclairage domotique",
    "tv": "television philips tele ecran domotique",
    "fedora": "vm machine virtuelle kvm backup sauvegarde serveur",
    "screen-manager": "ecran ecrans moniteur moniteurs display affichage application app bureau multi-ecran",
    "screen_manager": "ecran ecrans moniteur moniteurs display affichage application app bureau multi-ecran",
}


def enrich_description(name: str, description: str, server: str) -> str:
    """Enrichit une description MCP avec des termes francais pour le RAG.

    Args:
        name: Nom de l'outil (ex: "hue.turn_on_light")
        description: Description originale en anglais
        server: Nom du serveur MCP (ex: "hue")

    Returns:
        Description enrichie avec mots-cles francais
    """
    enrichments = []

    # Nom court sans prefixe serveur
    short_name = name.split(".")[-1] if "." in name else name

    # 1. Enrichissement par nom exact de l'outil
    if short_name in FRENCH_ENRICHMENTS:
        enrichments.append(FRENCH_ENRICHMENTS[short_name])

    # 2. Enrichissements bases sur le nom et la description
    text = f"{name} {description}".lower()
    for en_term, fr_terms in FRENCH_ENRICHMENTS.items():
        if en_term in text:
            enrichments.append(fr_terms)

    # 3. Nom du serveur en francais
    if server.lower() in _SERVER_NAMES:
        enrichments.append(_SERVER_NAMES[server.lower()])

    enrichment_text = " ".join(enrichments)
    return f"{description}\n\nMots-cles: {enrichment_text}" if enrichment_text else description


def enrich_optional_args(query: str, analysis: "EphaistosAnalysis") -> "EphaistosAnalysis":
    """Enrichit les arguments optionnels d'une analyse apres _rule_based_detect.

    Extrait les parametres avances non captures par les regles de base.
    Modifie analysis.arguments en place et retourne l'analyse.
    """
    if not analysis.tool:
        return analysis

    # Normaliser (meme methode que _rule_based_detect)
    q = unicodedata.normalize('NFD', query.lower())
    q = ''.join(c for c in q if unicodedata.category(c) != 'Mn')

    short = analysis.tool.split('.')[-1]
    args = analysis.arguments  # mutation en place

    if short == "vm_start":
        if re.search(r'\battends?\b.*\bssh\b', q):
            args["wait_ssh"] = True
        if re.search(r'\battends?\b.*\bip\b', q):
            args["wait_ip"] = True

    elif short == "vm_destroy":
        keep_disk_re = (
            r'\bgardes?\s+(?:le\s+|les\s+)?disques?\b'
            r'|\bsans\s+(?:effacer|supprimer)\b.*\bdisques?\b'
        )
        if re.search(keep_disk_re, q):
            args["keep_storage"] = True

    elif short == "vm_exec":
        if re.search(r'\b(?:en\s+)?sudo\b', q):
            args["sudo"] = True

    elif short == "vm_copy":
        if re.search(r'\b(?:recursifs?|recursive)\b', q):
            args["recursive"] = True

    elif short == "vm_clone":
        if re.search(r'\b(?:cow|linked|avec\s+cow|en\s+cow|mode\s+linked|mode\s+cow)\b', q):
            args["linked"] = True
        if re.search(r'\b(?:demarre|lance|start)\b.*\bapres\b|\bet\s+(?:demarre|lance|start)\b', q):
            args["start"] = True

    elif short == "vm_clone_system":
        if re.search(r'\bdry.?run\b|\bmode\s+test\b|\bsimule\b|\bsans\s+executer\b', q):
            args["dry_run"] = True

    elif short == "vm_verify":
        if re.search(r'\brapidement\b|\bvite\b|\bquick\b', q):
            args["quick"] = True
        if re.search(r'\bverbeux\b|\bverbose\b|\ben\s+detail\b|\bdetaille\b', q):
            args["verbose"] = True
        if re.search(r'\bcomparaison\s+des\s+paquets\b|\bpaquets\s+installes\b', q):
            args["compare_packages"] = True

    elif short == "vm_export":
        m_path = re.search(r'\bvers\s+(/\S+)', q)
        if m_path:
            args["output_path"] = m_path.group(1)
        if re.search(r'\bdry.?run\b|\bsans\s+vraiment\s+exporter\b', q):
            args["dry_run"] = True

    elif short == "vm_import":
        if re.search(r'\b(?:demarre|lance|start)\b.*\bapres\b|\bet\s+(?:demarre|lance|start)\b', q):
            args["start"] = True
        if re.search(r'\bdry.?run\b|\bmode\s+test\b', q):
            args["dry_run"] = True

    elif short == "backup_list":
        m_type = re.search(r'\b(timeshift|borg|rsync)\b', q)
        if m_type:
            args["type"] = m_type.group(1)
        if re.search(r'\ben\s+detail\b|\bdetaille\b', q):
            args["detailed"] = True

    elif short == "backup_create":
        m_type = re.search(r'\b(timeshift|borg|rsync)\b', q)
        if m_type:
            args["type"] = m_type.group(1)
        if re.search(r'\bavec\s+verification\b|\ben\s+verifiant\b|\bintegrite\b|\bverifie\b', q):
            args["verify"] = True
        if re.search(r'\bdry.?run\b', q):
            args["dry_run"] = True

    elif short == "backup_restore":
        if re.search(r'\bde\s+force\b|\bforce\b', q):
            args["force"] = True
        if re.search(r'\bdry.?run\b', q):
            args["dry_run"] = True

    elif short == "backup_verify":
        if re.search(r'\ben\s+profondeur\b|\bprofonde\b|\bdeep\b', q):
            args["deep"] = True
        if re.search(r'\brapidement\b|\bvite\b|\bquick\b', q):
            args["quick"] = True

    elif short == "backup_clean":
        if re.search(r'\bdry.?run\b|\bsans\s+supprimer\s+vraiment\b', q):
            args["dry_run"] = True
        m_keep = re.search(
            r'\b(?:gardant|conservant|gardes?)\s+les\s+(\d+)(?:\s+plus)?\s+'
            r'(?:derniers?e?s?|recents?e?s?)\b',
            q
        )
        if m_keep:
            args["keep_last"] = int(m_keep.group(1))

    return analysis


def format_listing_result(tool_name: str, content: str) -> str:
    """Formate le resultat d'un outil de listing.

    Extrait les informations essentielles (noms, etats) du JSON brut.

    Args:
        tool_name: Nom de l'outil
        content: Contenu JSON brut

    Returns:
        Resultat formate lisiblement
    """
    short_name = tool_name.split(".")[-1] if "." in tool_name else tool_name

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content

    if not isinstance(data, dict):
        return content

    lines = []

    if short_name == "get_all_scenes":
        lines.append(f"**{len(data)} scenes disponibles:**")
        for scene_id, scene in data.items():
            name = scene.get("name", "?")
            group = scene.get("group", "?")
            lines.append(f"  - {name} (groupe {group})")

    elif short_name == "get_all_lights":
        lines.append(f"**{len(data)} lumieres:**")
        for light_id, light in data.items():
            name = light.get("name", "?")
            on = "allumee" if light.get("on") else "eteinte"
            bri = light.get("brightness", "?")
            lines.append(f"  - [{light_id}] {name}: {on}, luminosite {bri}")

    elif short_name == "get_all_groups":
        lines.append(f"**{len(data)} groupes:**")
        for group_id, group in data.items():
            name = group.get("name", "?")
            on = "allume" if group.get("on") or group.get("any_on") else "eteint"
            lights = group.get("lights", [])
            lines.append(f"  - [{group_id}] {name}: {on}, {len(lights)} lumieres")

    elif short_name == "list_apps":
        lines.append(f"**{len(data)} applications:**")
        for app_id, app in data.items():
            name = app.get("label", app.get("name", "?"))
            lines.append(f"  - {name}")

    elif short_name in ("vm_status", "backup_list", "backup_status", "vm_snapshot"):
        # Garder le format original pour ces outils (deja bien formates)
        return content

    else:
        # Format generique: extraire les noms
        lines.append(f"**{len(data)} elements:**")
        for item_id, item in data.items():
            if isinstance(item, dict):
                name = item.get("name", item.get("label", item_id))
                lines.append(f"  - [{item_id}] {name}")
            else:
                lines.append(f"  - {item_id}: {item}")

    return "\n".join(lines) if lines else content
