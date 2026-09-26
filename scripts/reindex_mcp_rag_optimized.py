#!/usr/bin/env python3
"""
Script d'indexation optimisé pour RAG Enhanced.

Génère des documents RICHES en contexte naturel pour améliorer les scores RAG.
Au lieu de listes de mots-clés, crée des phrases naturelles avec exemples.

APPROCHE V2: Enrichissement côté INDEXATION (pas côté recherche)
- Documents enrichis avec synonymes intégrés
- Queries restent courtes et précises
- Meilleurs scores RAG

Usage:
    python scripts/reindex_mcp_rag_optimized.py
"""

import json
import os
import re
import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from lyra.hestia.executor import HestiaExecutor
from lyra.rag.keyword_retriever import KeywordRetriever
from lyra.rag.semantic_retriever import SemanticRetriever

# Charger le dictionnaire de synonymes
SYNONYM_MAPPINGS = None

def load_synonym_mappings():
    """Charge le dictionnaire de synonymes."""
    global SYNONYM_MAPPINGS
    if SYNONYM_MAPPINGS is None:
        mappings_path = Path(__file__).parent.parent / "data" / "synonym_mappings.json"
        with open(mappings_path) as f:
            SYNONYM_MAPPINGS = json.load(f)
    return SYNONYM_MAPPINGS

def expand_text_with_synonyms(text: str) -> list[str]:
    """Génère des variantes d'un texte avec synonymes en PHRASES NATURELLES.

    Au lieu de "allume/active les lumières/éclairages", génère:
    ["allume les lumières", "active les lumières", "allume les éclairages", "active les éclairages"]

    Args:
        text: Texte à enrichir

    Returns:
        Liste de variantes (max 6 pour éviter explosion combinatoire)
    """
    mappings = load_synonym_mappings()
    words = text.lower().split()

    # Identifier les mots remplaçables
    replacements = {}
    for i, word in enumerate(words):
        word_clean = word.strip(".,!?;:")

        # Chercher synonymes
        if word_clean in mappings.get("actions", {}):
            replacements[i] = [word_clean] + mappings["actions"][word_clean][:2]  # Max 3 variantes
        elif word_clean in mappings.get("entities", {}):
            replacements[i] = [word_clean] + mappings["entities"][word_clean][:2]

    # Générer variantes (limiter pour éviter explosion)
    variants = [text]  # Original toujours inclus

    # Si 1 mot remplaçable, générer toutes les variantes
    if len(replacements) == 1:
        pos = list(replacements.keys())[0]
        for synonym in replacements[pos][1:]:  # Skip original
            variant_words = words.copy()
            variant_words[pos] = synonym
            variants.append(" ".join(variant_words))

    # Si 2+ mots remplaçables, générer échantillon stratégique
    elif len(replacements) >= 2:
        positions = list(replacements.keys())[:2]  # Max 2 positions

        # Variantes 1: changer premier mot
        for synonym in replacements[positions[0]][1:2]:
            variant_words = words.copy()
            variant_words[positions[0]] = synonym
            variants.append(" ".join(variant_words))

        # Variantes 2: changer deuxième mot
        for synonym in replacements[positions[1]][1:2]:
            variant_words = words.copy()
            variant_words[positions[1]] = synonym
            variants.append(" ".join(variant_words))

        # Variante 3: changer les deux
        if len(replacements[positions[0]]) > 1 and len(replacements[positions[1]]) > 1:
            variant_words = words.copy()
            variant_words[positions[0]] = replacements[positions[0]][1]
            variant_words[positions[1]] = replacements[positions[1]][1]
            variants.append(" ".join(variant_words))

    return variants[:6]  # Max 6 variantes


# Limites du generateur. L'index de production est construit en 6 x 16 depuis
# le 2026-09-18 (83c202d, mediane 8 paraphrases par outil) ; les defauts
# etaient restes a 3 x 8, si bien qu'une reindexation « normale » degradait le
# RAG sans rien dire (constate 2026-09-26, lyra#24). Reglables pour la boucle
# d'amelioration.
TRIGGERS_MAX_DEFAUT = 6
VARIANTES_MAX_DEFAUT = 16
_TRIGGERS_MAX = int(os.environ.get("LYRA_TRIGGERS_MAX", str(TRIGGERS_MAX_DEFAUT)))
_VARIANTES_MAX = int(os.environ.get("LYRA_VARIANTES_MAX", str(VARIANTES_MAX_DEFAUT)))


# Avertissement que fedora-agents ajoute aux outils destructifs : du bruit pour
# la recherche (memes mots sur huit outils), le danger est porte par
# DANGEROUS_TOOLS / SENSITIVE_TOOLS, pas par l'index.
_AVERTISSEMENT_RE = re.compile(
    r"\s*(?:\u26a0\ufe0f?)?\s*\(?ATTENTION\s*:[^|()]*?(?:destructive|irr[ée]versible)\s*!?\)?", re.IGNORECASE)


def description_indexable(description: str) -> str:
    """Description d'outil sans l'avertissement de danger (sans effet sur la confirmation)."""
    return _AVERTISSEMENT_RE.sub("", description or "").strip()


def generate_rich_document(tool: dict) -> str:
    """Génère un document RICHE pour un outil MCP avec SYNONYMES INTÉGRÉS.

    APPROCHE V2: Enrichissement côté indexation
    - Synonymes intégrés dans le document (format: mot/syn1/syn2/syn3)
    - Triggers enrichis avec variantes
    - Exemples multipliés avec synonymes

    Exemple:
        "hue.turn_on_group (HUE): Allume/active/démarre un groupe de
         lumières/éclairages/lampes. Utilise pour: allumer/activer un groupe |
         éclairer/illuminer une pièce. Exemples: allume les lumières de la chambre |
         active l'éclairage du salon | démarre les lampes du bureau"
    """
    name = tool['name']
    desc = description_indexable(tool.get('description', ''))
    # Les tools HESTIA utilisent 'parameters' au lieu de 'inputSchema'
    schema = tool.get('parameters', tool.get('inputSchema', {}))

    # Extraire serveur et catégorie
    if '.' in name:
        server = name.split('.')[0].upper()
        short_name = name.split('.')[1]
    else:
        server = "UNKNOWN"
        short_name = name

    # Déterminer la catégorie
    category = categorize_tool(name, desc)

    # Générer exemples d'usage en français
    examples = generate_french_examples(name, category)

    # Générer phrases de trigger
    triggers = generate_trigger_phrases(name, category)

    # Construire le document riche
    parts = []

    # Signature de fonction avec paramètres (format EPHAISTOS)
    # IMPORTANT: Utiliser le nom COURT (sans préfixe serveur) pour la signature
    # EPHAISTOS attend "cast_youtube(url: string)" et pas "catt.cast_youtube(url: string)"
    # Ex: "cast_youtube(url: string)" ou "vm_clone(source_vm: string, new_vm_name: string, start?: boolean = true)"
    if schema and 'properties' in schema:
        params = schema['properties']
        required = schema.get('required', [])

        param_sigs = []
        for param_name, param_def in params.items():
            param_type = param_def.get('type', 'string')
            if param_name in required:
                # Paramètre requis
                param_sigs.append(f"{param_name}: {param_type}")
            else:
                # Paramètre optionnel avec "?"
                default = param_def.get('default', None)
                if default is not None:
                    param_sigs.append(f"{param_name}?: {param_type} = {default}")
                else:
                    param_sigs.append(f"{param_name}?: {param_type}")

        # Signature avec nom COURT
        signature = f"{short_name}({', '.join(param_sigs)})"
    else:
        # Pas de paramètres
        signature = f"{short_name}()"

    # LIGNE 1 : Nom complet + serveur (pour post-traitement du nom dans pipeline.py)
    # LIGNE 2 : Signature SEULE (format EPHAISTOS strict)
    # LIGNE 3 : Description
    # Format:
    #   catt.cast_youtube (CATT)
    #   Signature: cast_youtube(url: string)
    #   Caste une video YouTube sur la TV...
    parts.append(f"{name} ({server})")
    parts.append(f"Signature: {signature}")
    parts.append(desc)

    # Cas d'usage avec VARIANTES NATURELLES
    if triggers:
        # Générer variantes pour chaque trigger
        all_trigger_variants = []
        for trigger in triggers[:_TRIGGERS_MAX]:  # 6 par defaut (LYRA_TRIGGERS_MAX)
            variants = expand_text_with_synonyms(trigger)
            all_trigger_variants.extend(variants)

        if all_trigger_variants:
            parts.append(f"Utilise pour: {'. '.join(all_trigger_variants[:_VARIANTES_MAX])}")  # 16 par defaut (LYRA_VARIANTES_MAX)

    # Exemples concrets avec VARIANTES NATURELLES
    if examples:
        # Générer variantes pour chaque exemple
        all_example_variants = []
        for example in examples[:3]:  # Max 3 exemples de base
            variants = expand_text_with_synonyms(example)
            all_example_variants.extend(variants)

        if all_example_variants:
            parts.append(f"Exemples: {'. '.join(all_example_variants[:12])}")  # Max 12 variantes

    # Variantes du nom d'outil
    action_variants = get_action_variants(short_name)
    if action_variants:
        parts.append(f"Variantes: {' | '.join(action_variants)}")

    # Catégorie pour le contexte
    parts.append(f"Catégorie: {category}")

    return " ".join(parts)


def get_action_variants(tool_name: str) -> list[str]:
    """Génère des variantes du nom d'outil.

    Exemples:
        "turn_on_group" → ["turn_on", "switch_on", "power_on", "activate_group"]
        "vm_start" → ["start_vm", "boot_vm", "launch_vm"]
    """
    variants = []

    # Patterns communs
    patterns = {
        "turn_on": ["switch_on", "power_on", "activate", "enable"],
        "turn_off": ["switch_off", "power_off", "deactivate", "disable"],
        "set_": ["change_", "configure_", "adjust_", "modify_"],
        "get_": ["fetch_", "retrieve_", "read_", "show_"],
        "_start": ["_boot", "_launch", "_initialize", "_run"],
        "_stop": ["_halt", "_shutdown", "_terminate", "_kill"],
        "volume_up": ["increase_volume", "raise_volume", "louder"],
        "volume_down": ["decrease_volume", "lower_volume", "quieter"],
    }

    for pattern, synonyms in patterns.items():
        if pattern in tool_name:
            for syn in synonyms:
                variant = tool_name.replace(pattern, syn)
                if variant != tool_name:
                    variants.append(variant)

    return variants[:4]  # Max 4 variantes


def categorize_tool(name: str, desc: str) -> str:
    """Détermine la catégorie d'un outil."""
    name_lower = name.lower()

    # Catégories par serveur
    if name.startswith('fedora.vm_'):
        if 'backup' in name_lower or 'snapshot' in name_lower:
            return "vm_backup"
        elif 'clone' in name_lower:
            return "vm_management_advanced"
        else:
            return "vm_management_basic"
    elif name.startswith('fedora.backup_'):
        return "backup_management"
    elif name.startswith('hue.'):
        if 'color' in name_lower or 'rgb' in name_lower:
            return "hue_color"
        elif 'brightness' in name_lower:
            return "hue_brightness"
        elif 'scene' in name_lower:
            return "hue_scene"
        else:
            return "hue_control"
    elif name.startswith('tv.'):
        if 'volume' in name_lower or 'mute' in name_lower:
            return "tv_audio"
        elif 'ambilight' in name_lower:
            return "tv_ambilight"
        elif 'app' in name_lower or 'youtube' in name_lower:
            return "tv_apps"
        elif 'power' in name_lower:
            return "tv_power"
        else:
            return "tv_control"
    elif name.startswith('catt.'):
        return "cast_control"
    elif name.startswith('denon.'):
        if 'volume' in name_lower or 'mute' in name_lower:
            return "denon_audio"
        elif 'input' in name_lower or 'source' in name_lower:
            return "denon_input"
        else:
            return "denon_control"
    elif name.startswith('mermaid.'):
        return "diagram_generation"
    else:
        return "other"


def generate_trigger_phrases(name: str, category: str) -> list[str]:
    """Génère les phrases de trigger en français."""
    # Enlever le préfixe serveur pour la recherche
    short_name = name.split('.')[-1] if '.' in name else name

    triggers_map = {
        # Outils sans paraphrase jusqu'au 2026-09-18 (34/88) : formulations generiques,
        # jamais une phrase du jeu hors regles (scripts/controle_hors_regles.py).
        "catt.cast_browser": [
            "caster l'onglet du navigateur",
            "diffuse ce que je regarde dans firefox sur la tele",
            "envoie l'onglet actif sur la tele",
        ],
        "catt.cast_browser_dual": [
            "lecture synchronisee pc et tele",
            "lance la video sur le pc et la tele en meme temps",
            "dual cast pc tele",
        ],
        "catt.cast_dual_offset": [
            "ajuste le decalage entre pc et tele",
            "la tele est en avance, corrige le decalage",
            "decale la tele de deux secondes",
        ],
        "catt.cast_dual_resync": [
            "resynchronise pc et tele",
            "remets la tele au meme endroit que le pc",
            "recale la video sur la tele",
        ],
        "catt.cast_dual_stop": [
            "arrete le dual cast",
            "stoppe la lecture synchronisee",
            "coupe la synchro pc tele",
        ],
        "catt.cast_info": [
            "quel media est en cours sur le chromecast",
            "infos sur ce qui est diffuse",
            "c'est quoi qui joue sur la tele",
        ],
        "catt.cast_scan": [
            "trouve les chromecast",
            "scanne les appareils de diffusion",
            "quels chromecast sont disponibles",
        ],
        "fedora.help": [
            "quels outils tu as",
            "liste tes commandes",
            "aide sur les outils",
        ],
        "fedora.vm_export": [
            "exporte la vm dans une archive",
            "sauvegarde la vm dans une archive portable",
            "sors la vm en tar.gz",
        ],
        "fedora.vm_import": [
            "importe une vm depuis l'archive",
            "recharge la vm exportee",
            "restaure une vm depuis un tar.gz",
        ],
        "alert_light": [
            "identifie la lampe en la faisant clignoter",
            "signale une lumiere",
            "fais clignoter une ampoule",
        ],
        "create_group": [
            "cree un groupe de lumieres",
            "regroupe les lampes",
            "nouveau groupe hue",
        ],
        "find_light_by_name": [
            "cherche la lampe qui s'appelle",
            "trouve une lumiere par son nom",
            "quelle lampe s'appelle",
        ],
        "get_all_groups": [
            "liste les groupes de lumieres",
            "quels groupes hue",
            "montre les pieces hue",
        ],
        "get_all_lights": [
            "liste les lumieres",
            "quelles lampes sont connectees",
            "inventaire des ampoules",
        ],
        "get_all_scenes": [
            "liste les scenes",
            "quelles ambiances sont disponibles",
            "montre les scenes hue",
        ],
        "get_group": [
            "infos sur le groupe",
            "etat des lumieres du salon",
            "detail d'un groupe",
        ],
        "get_light": [
            "infos sur la lampe",
            "etat d'une lumiere",
            "detail d'une ampoule",
        ],
        "hue_beat_set": [
            "change le mode de la synchro musicale",
            "regle la palette du beat",
            "modifie les parametres de hue beat",
        ],
        "hue_beat_start": [
            "synchronise les lumieres avec la musique",
            "demarre hue beat",
            "les lumieres au rythme de la musique",
        ],
        "hue_beat_status": [
            "etat de la synchro musicale",
            "hue beat tourne-t-il",
            "la synchro musicale est active",
        ],
        "hue_beat_stop": [
            "arrete la synchro musicale",
            "stoppe hue beat",
            "coupe les lumieres au rythme",
        ],
        "quick_scene": [
            "scene rapide pour le salon",
            "configure une ambiance dans une piece",
            "ambiance rapide",
        ],
        "refresh_lights": [
            "rafraichis la liste des lumieres",
            "actualise les lampes",
            "recharge le cache hue",
        ],
        "set_color_preset": [
            "applique un preset de couleur a la lampe",
            "lampe en mode coucher de soleil",
            "couleur predefinie sur la lampe",
        ],
        "set_color_temperature": [
            "regle la temperature de couleur",
            "lumiere plus chaude",
            "blanc froid sur la lampe",
        ],
        "set_group_color_preset": [
            "applique un preset de couleur au salon",
            "ambiance predefinie pour les lumieres",
            "les lumieres en preset",
        ],
        "set_light_effect": [
            "mets un effet sur la lampe",
            "effet dynamique sur la lumiere",
            "fais boucler les couleurs",
        ],
        "set_scene": [
            "applique la scene au groupe",
            "mets la scene sur le salon",
            "active une scene pour la piece",
        ],
        "tv.get_state": [
            "la tele est-elle allumee",
            "etat de la tv",
            "la television est en veille ou allumee",
        ],
        "tv.list_apps": [
            "quelles applications sur la tele",
            "liste les applis de la tv",
            "montre les apps de la television",
        ],
        "tv.screen_off": [
            "eteins l'ecran mais garde le son",
            "ecran noir sur la tele",
            "image off son on",
        ],
        "tv.screen_on": [
            "rallume l'ecran de la tele",
            "remets l'image",
            "ecran de la tv en marche",
        ],
        "tv.send_key": [
            "appuie sur une touche de la telecommande",
            "envoie la touche ok",
            "touche retour sur la tele",
        ],
        # VM
        "fedora.vm_start": [
            "démarrer une VM", "lancer une machine virtuelle", "booter un serveur",
            "démarre la VM", "lance la machine", "boot le serveur", "démarrage machine virtuelle",
        ],
        "fedora.vm_stop": [
            "arrêter une VM", "stopper une machine virtuelle", "éteindre un serveur",
            "arrête la VM", "stoppe la machine", "coupe le serveur", "éteins la VM",
        ],
        "fedora.vm_status": [
            "voir l'état d'une VM", "lister les VMs", "afficher les machines virtuelles",
            "liste mes VMs", "quelles machines sont actives", "état des machines virtuelles",
            "quelles VMs j'ai", "liste les serveurs", "voir mes machines",
        ],
        "fedora.vm_clone": [
            "cloner une VM", "dupliquer une machine virtuelle", "copier un serveur",
            "clone la VM", "fais un clone", "duplique la machine", "copie le serveur",
        ],
        "fedora.vm_snapshot": [
            "créer un snapshot", "prendre un instantané", "sauvegarder l'état d'une VM",
            "fais un snapshot", "snapshot de la VM", "liste les snapshots", "voir les snapshots",
            "créer un point de restauration",
        ],
        "fedora.vm_exec": [
            "exécuter une commande dans une VM", "lancer un script sur une machine",
            "exécute dans la VM", "lance une commande sur la machine",
        ],
        "fedora.vm_destroy": [
            "supprimer une VM", "détruire une machine virtuelle",
            "supprime la VM", "détruis la machine", "efface la VM",
        ],
        "fedora.vm_copy": [
            "copier un fichier vers une VM", "transférer des données",
            "copie le fichier dans la VM", "envoie le fichier sur la machine",
        ],
        "fedora.vm_verify": [
            "vérifier une VM clonée", "comparer un clone",
            "vérifie le clone", "valide la VM clonée",
        ],
        "fedora.vm_clone_system": [
            "cloner le système hôte", "créer une VM depuis l'hôte",
            "clone le système complet",
        ],

        # Backup
        "fedora.backup_create": [
            "créer un backup", "faire une sauvegarde", "sauvegarder une VM",
            "fais un backup", "sauvegarde la machine", "crée une sauvegarde",
        ],
        "fedora.backup_restore": [
            "restaurer un backup", "récupérer une sauvegarde",
            "restaure le backup", "recharge la sauvegarde", "récupère le backup",
        ],
        "fedora.backup_list": [
            "lister les backups", "voir les sauvegardes",
            "liste les sauvegardes", "quels backups disponibles", "affiche les backups",
        ],
        "fedora.backup_status": [
            "voir l'état des backups", "dashboard des sauvegardes",
            "statut des sauvegardes", "état des backups",
        ],
        "fedora.backup_verify": [
            "vérifier un backup", "valider une sauvegarde",
            "vérifie le backup", "valide la sauvegarde",
        ],
        "fedora.backup_clean": [
            "nettoyer les backups", "supprimer les vieux sauvegardes",
            "nettoie les sauvegardes", "purge les anciens backups",
        ],

        # HUE
        "turn_on_light": [
            "allume la lampe de chevet", "allume la lumière du chevet",
            "allumer une lumière", "activer une lampe", "éclairer",
            "allume la lumière", "allume la lampe", "mets la lumière", "éclaire la pièce",
        ],
        "turn_off_light": [
            "éteindre une lumière", "couper une lampe",
            "éteins la lumière", "éteins la lampe", "coupe la lumière",
            "éteindre la lumière",
        ],
        "turn_on_group": [
            "allumer un groupe de lumières", "activer les lumières d'une pièce",
            "allume les lumières", "allumer les lumières", "mets les lumières",
            "éclaire la chambre", "allume l'éclairage",
        ],
        "turn_off_group": [
            "éteindre les lumières", "éteins les lumières", "couper les lumières",
            "éteindre un groupe de lumières", "couper les lumières d'une pièce",
            "éteindre l'éclairage", "coupe les lumières", "plonge dans le noir",
            "éteindre les lampes", "toutes les lumières éteintes",
        ],
        "set_brightness": [
            "mets la lumière plus forte", "rends la lampe plus faible",
            "régler la luminosité", "changer l'intensité lumineuse",
            "règle la luminosité", "ajuste la lumière", "baisse la luminosité",
            "monte la luminosité",
        ],
        "set_group_brightness": [
            "mets les lumières plus fortes", "rends les lumières plus faibles",
            "régler la luminosité d'un groupe", "tamiser les lumières",
            "baisse les lumières", "tamise les lumières", "monte les lumières",
            "règle l'intensité des lumières", "baisser les lumières",
        ],
        "set_color_rgb": [
            "mets une ambiance bleue", "mets la lampe en bleu",
            "changer la couleur d'une lumière", "mettre en rouge/bleu/vert",
            "change la couleur", "mets en rouge", "mets en bleu", "lumière colorée",
        ],
        "set_group_color_rgb": [
            "mets une ambiance bleue dans la pièce", "mets les lumières en bleu",
            "changer la couleur d'un groupe", "mettre les lumières en rouge",
            "change la couleur des lumières", "mets les lumières en bleu",
        ],
        "activate_scene_by_name": [
            "activer une scène", "lancer un preset de lumières",
            "active la scène", "lance l'ambiance", "mode cinéma", "mode détente",
        ],

        # TV
        "tv.power_on": [
            "allumer la télé", "démarrer la TV",
            "allume la télévision", "mets la télé en marche", "enclenche la TV",
        ],
        "tv.power_off": [
            "mets la télé en veille", "mets la TV en veille",
            "éteindre la télé", "couper la TV",
            "éteins la télévision", "coupe la télé", "arrête la TV",
        ],
        "tv.volume_up": [
            "monter le volume de la télé", "augmenter le son",
            "monte le volume", "augmente le son de la télé", "plus fort",
        ],
        "tv.volume_down": [
            "baisser le volume de la télé", "diminuer le son",
            "baisse le volume", "diminue le son de la télé", "moins fort",
        ],
        "tv.volume_set": [
            "régler le volume de la télé à X",
            "règle le volume", "mets le volume à", "fixe le son à",
        ],
        "tv.mute": [
            "mettre la télé en mute", "couper le son de la TV",
            "mute la télé", "coupe le son", "sourdine TV", "silence télévision",
        ],
        "tv.ambilight_on": [
            "activer l'ambilight", "allumer les LEDs",
            "active le rétroéclairage", "allume l'ambilight",
        ],
        "tv.ambilight_off": [
            "désactiver l'ambilight", "éteindre les LEDs",
            "éteins l'ambilight", "coupe le rétroéclairage",
        ],
        "tv.ambilight_mode": [
            "changer le mode ambilight", "passe l'ambilight en mode lounge",
            "mets l'ambilight en mode vidéo", "ambilight mode audio",
        ],
        "tv.launch_app": [
            "lancer une application", "ouvrir Netflix/YouTube",
            "lance Netflix", "ouvre YouTube", "démarre l'appli", "ouvre l'application",
        ],
        "tv.youtube_video": [
            "regarder une vidéo YouTube sur la télé",
            "lance la vidéo YouTube", "diffuse YouTube sur la TV",
        ],

        # CAST
        "catt.cast_youtube": [
            "caster une vidéo YouTube", "diffuser YouTube sur la télé",
            "caste YouTube", "envoie la vidéo sur la télé", "cast YouTube",
        ],
        "cast_youtube": [
            "caster une vidéo YouTube", "diffuser YouTube sur la télé",
            "caste YouTube", "envoie la vidéo sur la télé",
        ],
        "catt.cast_url": [
            "caster une URL", "diffuser une vidéo",
            "caste l'URL", "envoie la vidéo", "diffuse cette vidéo",
        ],
        "cast_url": [
            "caster une URL", "diffuser une vidéo",
            "caste l'URL", "envoie la vidéo",
        ],
        "catt.cast_stop": [
            "arrêter le cast", "stopper la diffusion",
            "arrête le cast", "coupe la diffusion", "stoppe le cast",
        ],
        "cast_stop": [
            "arrêter le cast", "stopper la diffusion",
            "arrête la diffusion", "coupe le cast",
        ],
        "catt.cast_pause": [
            "mettre le cast en pause",
            "pause le cast", "mets en pause", "stop temporaire cast",
        ],
        "cast_pause": ["mettre le cast en pause", "pause le cast", "mets en pause"],
        "catt.cast_resume": [
            "reprendre le cast", "relancer la diffusion",
            "reprends le cast", "continue la diffusion",
        ],
        "cast_resume": ["reprendre le cast", "relancer la diffusion"],
        "catt.cast_volume": [
            "régler le volume du cast",
            "monte le volume du cast", "baisse le volume du cast",
        ],
        "cast_volume": ["régler le volume du cast"],
        "catt.cast_seek": [
            "avancer/reculer dans la vidéo",
            "avance de 30 secondes", "recule dans la vidéo",
        ],
        "cast_seek": ["avancer/reculer dans la vidéo", "avance dans la vidéo"],
        "catt.cast_status": [
            "voir l'état du cast", "statut de la diffusion",
            "qu'est-ce qui joue", "cast en cours", "statut cast",
        ],

        # DENON
        "denon.power_on": [
            "allumer l'ampli", "démarrer le Denon", "allumer le home cinema",
            "allume l'amplificateur", "démarre le home cinéma",
        ],
        "denon.power_off": [
            "mets l'ampli en veille",
            "éteindre l'ampli", "couper le Denon",
            "éteins l'amplificateur", "coupe le home cinéma",
        ],
        "denon.volume_up": [
            "monter le volume de l'ampli", "augmenter le son du Denon",
            "monte le volume de l'ampli", "plus fort home cinéma",
        ],
        "denon.volume_down": [
            "baisser le volume de l'ampli",
            "baisse le son du Denon", "moins fort ampli",
        ],
        "denon.volume_set": [
            "régler le volume de l'ampli à X",
            "fixe le volume du Denon", "règle le son de l'ampli",
        ],
        "denon.mute_on": [
            "mettre l'ampli en mute", "couper le son du Denon",
            "sourdine ampli", "coupe le son du home cinéma",
        ],
        "denon.mute_off": [
            "désactiver le mute de l'ampli",
            "réactive le son de l'ampli", "enlève le mute",
        ],
        "denon.mute_toggle": [
            "inverse le mute de l'ampli", "bascule la sourdine",
            "basculer le mute de l'ampli",
            "toggle mute ampli",
        ],
        "denon.set_input": [
            "changer la source de l'ampli", "mettre en Bluray/TV/GAME",
            "change la source", "mets sur Bluray", "passe en mode TV",
        ],
        "denon.get_status": [
            "voir l'état du Denon", "statut de l'ampli",
            "état du home cinéma", "volume du Denon",
            # un seul outil lit l'ampli (marche, volume, source) : la description
            # serveur, liste de champs techniques, ne suffit plus (2026-09-26)
            "le Denon est-il en veille", "réglages actuels de l'ampli",
        ],

        # MERMAID
        "mermaid.generate_diagram": [
            "générer un diagramme", "créer un schéma",
            "fais un diagramme", "dessine un graphique", "crée un organigramme",
        ],
    }

    # Chercher d'abord avec le nom complet, sinon avec le short_name
    return triggers_map.get(name, triggers_map.get(short_name, []))


def generate_french_examples(name: str, category: str) -> list[str]:
    """Génère des exemples concrets en français."""
    # Enlever le préfixe serveur pour la recherche
    short_name = name.split('.')[-1] if '.' in name else name

    examples_map = {
        # VM
        "fedora.vm_start": [
            "démarre preprod-09", "lance la VM de test", "boot le serveur sandbox",
            "lance preprod-01", "démarre la machine virtuelle",
        ],
        "fedora.vm_stop": [
            "arrête preprod-09", "stoppe la VM sandbox", "éteins le serveur test",
            "coupe preprod-01", "arrête la machine",
        ],
        "fedora.vm_status": [
            "liste mes VMs", "état de preprod-09", "quelles machines sont actives",
            "liste les machines virtuelles", "affiche les VMs", "mes machines",
        ],
        "fedora.vm_clone": [
            "clone preprod-09 en test-clone", "duplique ma VM en backup",
            "fais un clone de preprod-09", "copie la VM",
        ],
        "fedora.vm_snapshot": [
            "fais un snapshot de preprod-09", "prends un instantané", "liste les snapshots",
            "snapshot de la machine", "crée un point de restauration pour preprod-09",
        ],
        "fedora.vm_exec": [
            "exécute 'uptime' sur preprod-09", "lance systemctl status dans la VM",
            "tape une commande dans sandbox-01",
        ],
        "fedora.vm_destroy": [
            "supprime sandbox-01", "détruis la VM test", "efface la machine sandbox",
        ],

        # Backup
        "fedora.backup_create": [
            "fais un backup de preprod-09", "crée une sauvegarde",
            "sauvegarde la machine preprod-09",
        ],
        "fedora.backup_restore": [
            "restaure le backup backup-001", "récupère la sauvegarde d'hier",
            "reviens à la sauvegarde de la VM",
        ],
        "fedora.backup_list": [
            "liste les backups", "quels backups sont disponibles",
            "affiche les sauvegardes",
        ],

        # HUE
        "turn_on_light": [
            "allume la lampe de chevet",
            "mets la lumière dans le bureau", "éclaire la pièce",
        ],
        "turn_off_light": [
            "éteins la lumière de la chambre",
            "coupe la lampe du bureau", "éteins la lampe",
        ],
        "turn_on_group": [
            "allume les lumières de la chambre", "active l'éclairage du salon",
            "allume les lumières", "mets les lumières dans le salon",
            "éclaire la chambre",
        ],
        "turn_off_group": [
            "éteins toutes les lumières", "coupe l'éclairage de la cuisine",
            "éteins les lumières de la chambre", "éteins les lumières",
            "coupe les lumières", "plus de lumières",
        ],
        "set_brightness": [
            "règle la luminosité à 50%", "tamise la lumière",
            "baisse la luminosité de la lampe",
        ],
        "set_group_brightness": [
            "baisse la luminosité à 20%", "mets les lumières à 80%",
            "tamise les lumières", "baisse les lumières à 30%",
        ],
        "set_color_rgb": [
            "mets la lumière en rouge", "change la couleur en bleu",
            "lumière bleue dans le bureau",
        ],
        "set_group_color_rgb": [
            "mets les lumières en rouge", "passe le salon en bleu",
            "change la couleur des lumières",
        ],
        "activate_scene_by_name": [
            "active la scène détente", "lance le preset soirée", "active la scène cinéma",
            "mets le mode détente", "ambiance cinéma",
        ],

        # TV
        "tv.power_on": [
            "allume la télé", "démarre la TV",
            "mets la télé en marche",
        ],
        "tv.power_off": [
            "éteins la télé", "coupe la TV",
            "arrête la télévision",
        ],
        "tv.volume_up": [
            "monte le volume de la télé", "augmente le son",
            "plus fort la télé",
        ],
        "tv.volume_down": [
            "baisse le volume", "diminue le son de la télé",
            "moins fort",
        ],
        "tv.mute": [
            "mets la télé en mute", "coupe le son",
            "silence la télé",
        ],
        "tv.launch_app": [
            "lance Netflix", "ouvre YouTube sur la télé",
            "lance Prime Video",
        ],
        "tv.youtube_video": ["lance cette vidéo YouTube sur la télé", "ouvre ce lien YouTube sur la TV", "joue cette vidéo YouTube sur le téléviseur"],

        # CAST
        "catt.cast_youtube": [
            "caste cette vidéo YouTube", "diffuse YouTube sur la télé",
            "envoie la vidéo sur la TV",
        ],
        "cast_youtube": [
            "caste cette vidéo YouTube", "diffuse YouTube sur la télé",
        ],
        "catt.cast_stop": [
            "arrête le cast", "stoppe la diffusion",
            "coupe le cast",
        ],
        "cast_stop": ["arrête le cast", "stoppe la diffusion"],
        "catt.cast_pause": ["mets le cast en pause", "pause le cast", "fige la vidéo sur le Chromecast"],
        "cast_pause": ["mets le cast en pause"],
        "catt.cast_volume": ["monte le volume du cast à 50", "baisse le volume du cast", "son du Chromecast à 30"],
        "cast_volume": ["monte le volume du cast à 50"],
        "catt.cast_status": [
            "quel est le statut du cast", "qu'est-ce qui est casté",
            "qu'est-ce qui joue en ce moment",
        ],

        # DENON
        "denon.power_on": ["allume le Denon", "démarre l'ampli", "réveille l'amplificateur"],
        "denon.power_off": ["éteins le Denon", "arrête l'amplificateur", "mets le Denon en veille"],
        "denon.volume_up": [
            "monte le volume de l'ampli", "augmente le son du Denon",
            "plus fort l'ampli",
        ],
        "denon.mute_on": [
            "mets l'ampli en mute", "coupe le son du home cinema",
            "silence l'ampli",
        ],
        "denon.set_input": [
            "change la source en Bluray", "mets l'ampli sur TV",
            "passe en mode GAME",
        ],
        "denon.get_status": [
            "quel est le statut du Denon", "état de l'ampli",
            "volume actuel du Denon",
        ],
        "denon.volume_down": ["baisse le son de l'ampli", "moins fort sur le Denon", "diminue le volume du home cinéma"],
        "denon.volume_set": ["mets l'ampli à 40", "règle le Denon sur 35", "volume du home cinéma à 50"],
        "denon.mute_off": ["rends le son au Denon", "enlève le mute du Denon", "réactive le son du home cinéma"],
        "denon.mute_toggle": ["change l'état du mute du Denon", "inverse la sourdine du Denon", "mute ou démute le home cinéma"],

        # CAST (suite)
        "catt.cast_browser": ["partage l'onglet du navigateur sur la TV", "caste la vidéo du navigateur", "mets la vidéo de Firefox sur la TV"],
        "catt.cast_browser_dual": ["lance la vidéo sur le PC et la télé en même temps", "double diffusion synchronisée pour LightBeat", "joue la vidéo Firefox sur les deux écrans"],
        "catt.cast_dual_offset": ["décale la télé de 200 millisecondes", "la télé est en retard, ajuste le décalage", "règle l'offset du double cast"],
        "catt.cast_dual_resync": ["resynchronise le PC et la télé", "les deux écrans sont décalés, recale-les", "remets la télé à la position de Firefox"],
        "catt.cast_dual_stop": ["arrête la double diffusion", "coupe le cast synchronisé", "stoppe le dual cast"],
        "catt.cast_info": ["infos sur la vidéo castée", "titre et durée du média diffusé", "détails du média en cours de diffusion"],
        "catt.cast_resume": ["reprends le cast", "relance la lecture sur le Chromecast", "continue la diffusion"],
        "catt.cast_scan": ["cherche les appareils de cast du réseau", "quels récepteurs de diffusion sont disponibles", "scanne les appareils DLNA"],
        "catt.cast_seek": ["avance de 30 secondes", "recule d'une minute dans la vidéo", "saute 2 minutes plus loin dans le cast"],
        "catt.cast_url": ["caste ce lien sur la télé", "mets ce flux radio sur le cast", "diffuse cette adresse http sur la TV"],

        # BACKUP / VM (suite)
        "fedora.backup_clean": ["nettoie les vieux backups", "applique la rétention des sauvegardes", "supprime les anciennes sauvegardes borg"],
        "fedora.backup_status": ["tableau de bord des sauvegardes", "espace utilisé par les backups", "où en sont mes sauvegardes"],
        "fedora.backup_verify": ["vérifie l'intégrité des backups", "contrôle la sauvegarde borg", "les sauvegardes sont-elles intactes"],
        "fedora.help": ["quels outils VM as-tu", "aide sur la gestion des machines virtuelles", "liste les commandes fedora disponibles"],
        "fedora.vm_clone_system": ["clone mon système entier dans une VM", "fais une VM bootable à partir de l'hôte", "copie tout le PC dans une machine virtuelle"],
        "fedora.vm_copy": ["copie ce fichier dans la VM preprod-09", "récupère le dossier logs depuis la VM", "envoie le script sur sandbox-01 par scp"],
        "fedora.vm_export": ["exporte preprod-09 en archive", "fais une archive portable de la VM", "exporte la machine en mode examen"],
        "fedora.vm_import": ["importe l'archive de VM", "restaure la VM depuis l'archive exportée", "importe preprod-09 sous un nouveau nom"],
        "fedora.vm_verify": ["vérifie que le clone est fidèle", "contrôle la VM clonée", "compare la VM clonée avec l'hôte"],

        # HUE (suite)
        "hue.alert_light": ["fais clignoter la lampe 3", "identifie la lampe du bureau en la faisant flasher", "quelle lampe est la numéro 5, fais-la clignoter"],
        "hue.create_group": ["crée un groupe lecture avec les lampes 2 et 4", "regroupe les lampes du salon", "nouveau groupe de lumières pour le bureau"],
        "hue.find_light_by_name": ["trouve la lampe qui s'appelle bureau", "cherche la lumière nommée plafond", "quelle lampe porte le nom chevet"],
        "hue.get_all_groups": ["liste les groupes de lumières", "quelles pièces ont des lampes", "montre les groupes Hue"],
        "hue.get_all_lights": ["liste toutes les lampes", "quelles lumières sont connectées au pont", "inventaire des ampoules Hue"],
        "hue.get_all_scenes": ["liste les scènes Hue", "quelles ambiances sont disponibles", "montre les scènes enregistrées"],
        "hue.get_group": ["état du groupe salon", "infos sur le groupe 81", "quelles lampes dans le groupe chambre"],
        "hue.get_light": ["état de la lampe 3", "infos sur la lumière du bureau", "la lampe du chevet est-elle allumée"],
        "hue.hue_beat_set": ["passe hue beat en palette feu", "rends hue beat plus sensible aux basses", "baisse la luminosité de hue beat"],
        "hue.hue_beat_start": ["lance hue beat", "fais danser les lumières sur la musique", "lumières en rythme avec le son"],
        "hue.hue_beat_status": ["hue beat tourne-t-il", "état de hue beat", "quel BPM détecte hue beat"],
        "hue.hue_beat_stop": ["arrête hue beat", "stoppe les lumières musicales", "plus de lumières en rythme"],
        "hue.quick_scene": ["enregistre une nouvelle scène rouge tamisée", "fais une scène douce à 30 pour cent", "prépare une scène lecture en blanc chaud"],
        "hue.refresh_lights": ["rafraîchis la liste des lampes", "j'ai ajouté une ampoule, mets à jour", "recharge les lumières du pont"],
        "hue.set_color_preset": ["mets la lampe 3 en blanc chaud", "lampe du bureau en lumière du jour", "passe la lampe 2 en preset concentration"],
        "hue.set_color_temperature": ["règle la lampe 3 à 2700 kelvins", "lumière plus chaude sur le bureau", "température de couleur froide sur la lampe 2"],
        "hue.set_group_color_preset": ["passe la pièce en blanc chaud", "lumière du jour dans toute la pièce", "blanc froid sur toutes les lampes"],
        "hue.set_light_effect": ["effet boucle de couleurs sur la lampe 3", "lance l'effet colorloop", "arrête l'effet de la lampe du bureau"],
        "hue.set_scene": ["applique la scène 5 au salon", "mets la scène enregistrée sur le groupe", "active la scène par son identifiant"],

        # TV (suite)
        "tv.ambilight_mode": ["mets l'ambilight en mode audio", "ambilight qui suit la vidéo", "passe l'ambilight en lounge"],
        "tv.ambilight_off": ["éteins l'ambilight", "coupe les lumières derrière la télé", "désactive l'ambilight"],
        "tv.ambilight_on": ["allume l'ambilight", "active les lumières de la télé", "remets l'ambilight"],
        "tv.get_state": ["état de la télé", "la télé est-elle allumée", "quel volume sur la TV"],
        "tv.list_apps": ["quelles applis sur la télé", "liste les applications de la TV", "montre les apps installées sur la télé"],
        "tv.screen_off": ["écran noir mais le son continue", "mode musique, image coupée", "coupe juste l'écran, pas le son"],
        "tv.screen_on": ["rallume l'écran seul", "remets l'image, le son tourne déjà", "sors du mode écran noir"],
        "tv.send_key": ["appuie sur retour sur la télécommande", "touche accueil de la télé", "envoie la touche pause à la TV"],
        "tv.volume_set": ["mets la télé à 20", "règle le son de la TV sur 15", "volume de la télé à 10"],
    }

    # Chercher d'abord avec le nom complet, sinon avec le short_name
    return examples_map.get(name, examples_map.get(short_name, []))


def main():
    print("=" * 80)
    print("RÉINDEXATION RAG OPTIMISÉE")
    print("=" * 80)

    # Charger config
    print("\n[*] Chargement configuration...")
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    rag_cfg = cfg.get("rag", {})

    # Initialiser HESTIA pour récupérer tous les outils
    print("[*] Initialisation HESTIA...")
    # HESTIA attend un dict, pas un RAGConfig
    executor = HestiaExecutor(cfg)  # cfg est déjà chargé en tant que dict

    # Récupérer TOUS les outils (85 total)
    print("[*] Récupération des 85 outils MCP...")
    tools = executor.get_available_tools()
    print(f"    -> {len(tools)} outils trouvés")

    # Grouper par serveur
    by_server = {}
    for tool in tools:
        server = tool['name'].split('.')[0] if '.' in tool['name'] else 'unknown'
        if server not in by_server:
            by_server[server] = []
        by_server[server].append(tool)

    for server, server_tools in sorted(by_server.items()):
        print(f"    - {server.upper()}: {len(server_tools)} outils")

    # Générer documents RICHES
    print("\n[*] Génération des documents RAG optimisés...")
    documents = []
    metadatas = []
    ids = []

    for tool in tools:
        # Générer document riche
        doc = generate_rich_document(tool)

        # Metadata
        name = tool['name']
        server = name.split('.')[0] if '.' in name else 'unknown'
        category = categorize_tool(name, description_indexable(tool.get('description', '')))

        meta = {
            'name': name,
            'server_name': server,
            'category': category,
            'description': description_indexable(tool.get('description', ''))
        }

        documents.append(doc)
        metadatas.append(meta)
        ids.append(name)

        print(f"    [{server.upper()}] {name} ({category})")

    # Créer les retrievers
    print("\n[*] Initialisation des retrievers...")
    semantic = SemanticRetriever(
        persist_directory=rag_cfg["chromadb"]["persist_directory"],
        collection_name=rag_cfg["chromadb"]["collection_name"],
        embedding_model=rag_cfg["chromadb"]["embedding_model"]
    )
    keyword = KeywordRetriever()

    semantic.initialize()

    # EFFACER l'ancien index
    print("[*] Effacement de l'ancien index...")
    semantic.clear()
    keyword.clear()

    if not documents:
        # Aucun MCP selectionne/joignable : rien a indexer. ChromaDB refuse
        # un add() avec une liste d'embeddings vide -- s'arreter proprement
        # plutot que de laisser remonter la ValueError.
        print("\n[i] Aucun outil MCP disponible, index laisse vide.")
        print("\n" + "=" * 80)
        print("RÉINDEXATION TERMINÉE")
        print("=" * 80)
        return

    # Indexer
    print("[*] Indexation dans ChromaDB (semantic)...")
    semantic.add_documents(documents, metadatas, ids)

    print("[*] Indexation dans BM25 (keyword)...")
    keyword.add_documents(documents, metadatas, ids)

    print(f"\n[+] SUCCÈS: {len(tools)} outils indexés avec documents riches!")

    # Tests rapides
    print("\n" + "=" * 80)
    print("TESTS RAPIDES")
    print("=" * 80)

    test_queries = [
        "allume les lumières de la chambre",
        "démarre preprod-09",
        "clone preprod-09 en test-clone",
        "arrête le cast"
    ]

    for query in test_queries:
        print(f"\n[?] Query: '{query}'")
        results = semantic.search(query, top_k=1)
        if results:
            r = results[0]
            print(f"    ✓ Score: {r.score:.3f} - Tool: {r.metadata.get('name', 'N/A')}")
        else:
            print("    ✗ Aucun résultat")

    print("\n" + "=" * 80)
    print("RÉINDEXATION TERMINÉE")
    print("=" * 80)


if __name__ == "__main__":
    main()
