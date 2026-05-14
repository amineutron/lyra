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

import sys
import json
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.core.config import RAGConfig
from lyra.rag.semantic_retriever import SemanticRetriever
from lyra.rag.keyword_retriever import KeywordRetriever
from lyra.hestia.executor import HestiaExecutor
import yaml

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
    desc = tool.get('description', '')
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
        for trigger in triggers[:3]:  # Max 3 triggers de base
            variants = expand_text_with_synonyms(trigger)
            all_trigger_variants.extend(variants)

        if all_trigger_variants:
            parts.append(f"Utilise pour: {'. '.join(all_trigger_variants[:8])}")  # Max 8 variantes

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
    desc_lower = desc.lower()

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
            "régler la luminosité", "changer l'intensité lumineuse",
            "règle la luminosité", "ajuste la lumière", "baisse la luminosité",
            "monte la luminosité",
        ],
        "set_group_brightness": [
            "régler la luminosité d'un groupe", "tamiser les lumières",
            "baisse les lumières", "tamise les lumières", "monte les lumières",
            "règle l'intensité des lumières", "baisser les lumières",
        ],
        "set_color_rgb": [
            "changer la couleur d'une lumière", "mettre en rouge/bleu/vert",
            "change la couleur", "mets en rouge", "mets en bleu", "lumière colorée",
        ],
        "set_group_color_rgb": [
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
        "tv.ambilight_color": [
            "changer la couleur de l'ambilight",
            "change la couleur des LEDs", "mets l'ambilight en bleu",
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
        ],
        "fedora.backup_list": [
            "liste les backups", "quels backups sont disponibles",
            "affiche les sauvegardes",
        ],

        # HUE
        "turn_on_light": [
            "allume la lampe du bureau",
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
        "tv.ambilight_color": ["change l'ambilight en bleu", "mets l'ambilight en rouge"],
        "tv.launch_app": [
            "lance Netflix", "ouvre YouTube sur la télé",
            "lance Prime Video",
        ],
        "tv.youtube_video": ["lance cette vidéo YouTube sur la télé"],

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
        "catt.cast_pause": ["mets le cast en pause", "pause le cast"],
        "cast_pause": ["mets le cast en pause"],
        "catt.cast_volume": ["monte le volume du cast à 50", "baisse le volume du cast"],
        "cast_volume": ["monte le volume du cast à 50"],
        "catt.cast_status": [
            "quel est le statut du cast", "qu'est-ce qui est casté",
            "qu'est-ce qui joue en ce moment",
        ],

        # DENON
        "denon.power_on": ["allume le Denon", "démarre l'ampli", "allume le home cinéma"],
        "denon.power_off": ["éteins le Denon", "coupe l'ampli"],
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
        category = categorize_tool(name, tool.get('description', ''))

        meta = {
            'name': name,
            'server_name': server,
            'category': category,
            'description': tool.get('description', '')
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
            print(f"    ✗ Aucun résultat")

    print("\n" + "=" * 80)
    print("RÉINDEXATION TERMINÉE")
    print("=" * 80)


if __name__ == "__main__":
    main()
