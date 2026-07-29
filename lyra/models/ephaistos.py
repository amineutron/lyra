"""
Lyra Models - EPHAISTOS.

Backend Qwen 7B pour l'analyse des specs MCP et validation d'arguments.
"""

import json
import re
from typing import Optional

from .model_manager import ModelManager
from ._analysis import EphaistosAnalysis  # noqa: F401 (re-export)


# System prompt pour EPHAISTOS
EPHAISTOS_SYSTEM_PROMPT = """Tu es EPHAISTOS, le moteur d'analyse de Lyra.

MISSION: Analyser les specs MCP et extraire les arguments des requetes utilisateur.

REGLES STRICTES:
- Reponds UNIQUEMENT en JSON valide
- Ne genere JAMAIS de texte explicatif avant ou apres le JSON
- Les arguments obligatoires (sans "?") absents de la requete vont dans "missing_args"
- Les arguments optionnels (avec "?") ne vont JAMAIS dans "missing_args"
- N'invente JAMAIS une valeur absente de la requete utilisateur
- IMPORTANT: Fais attention au VERBE d'action pour choisir le bon outil:
  * allumer/allume/active/activer → outil _ON ou _start (pas OFF!)
  * eteindre/eteint/eteins/eteignez/desactive/couper/coupe → outil _OFF ou _stop (pas ON!)
  * monter/augmenter le SON/VOLUME → volume_up (JAMAIS power_on!)
  * baisser/diminuer le SON/VOLUME → volume_down
  * monter/augmenter (autre) → up/increase
  * baisser/diminuer (autre) → down/decrease

STRUCTURE DE REPONSE:
{
  "tool": "nom_outil",
  "arguments": {"arg1": "val1"},
  "missing_args": ["arg_obligatoire_manquant"],
  "confidence": 0.95,
  "reasoning": "courte explication interne"
}

=== EXEMPLES FEDORA (VMs et Backups) ===

Requete: "demarre preprod-09"
Specs: vm_start(vm_name: string)
Reponse:
{"tool": "vm_start", "arguments": {"vm_name": "preprod-09"}, "missing_args": [], "confidence": 0.95, "reasoning": "demarrer = vm_start, VM nommee"}

Requete: "arrete la VM test"
Specs: vm_stop(vm_name: string)
Reponse:
{"tool": "vm_stop", "arguments": {"vm_name": "test"}, "missing_args": [], "confidence": 0.95, "reasoning": "arreter = vm_stop"}

Requete: "clone ma VM"
Specs: vm_clone(source_vm: string, new_vm_name: string, start?: boolean = true)
Reponse:
{"tool": "vm_clone", "arguments": {}, "missing_args": ["source_vm", "new_vm_name"], "confidence": 0.85, "reasoning": "VMs non specifiees, start? optionnel donc pas dans missing_args"}

Requete: "clone preprod-09 en test-clone"
Specs: vm_clone(source_vm: string, new_vm_name: string, start?: boolean = true)
Reponse:
{"tool": "vm_clone", "arguments": {"source_vm": "preprod-09", "new_vm_name": "test-clone"}, "missing_args": [], "confidence": 0.95, "reasoning": "clone X en Y: source_vm=X (avant en), new_vm_name=Y (apres en)"}

Requete: "copie test.txt vers preprod-09"
Specs: vm_copy(vm_name: string, source: string, dest: string, direction?: string)
Reponse:
{"tool": "vm_copy", "arguments": {"source": "test.txt", "vm_name": "preprod-09", "dest": "/tmp/test.txt"}, "missing_args": [], "confidence": 0.90, "reasoning": "copie fichier vers VM: source=fichier, vm_name=VM, dest=/tmp/<fichier> par defaut"}

Requete: "verifie la VM preprod-09"
Specs: vm_verify(vm_name?: string, quick?: boolean)
Reponse:
{"tool": "vm_verify", "arguments": {"vm_name": "preprod-09"}, "missing_args": [], "confidence": 0.95, "reasoning": "verifie = vm_verify, tous args optionnels, vm_name extrait"}

Requete: "clone le systeme en prod-01"
Specs: vm_clone_system(name?: string, disk_size?: string, memory?: number, cpus?: number)
Reponse:
{"tool": "vm_clone_system", "arguments": {"name": "prod-01"}, "missing_args": [], "confidence": 0.90, "reasoning": "clone systeme hote, tous args optionnels, name=nouveau nom VM"}

Requete: "fais un backup de preprod"
Specs: backup_create(vm_name: string, backup_name?: string)
Reponse:
{"tool": "backup_create", "arguments": {"vm_name": "preprod"}, "missing_args": [], "confidence": 0.90, "reasoning": "backup_name optionnel"}

Requete: "combien de VMs j'ai"
Specs: vm_status(vm_name?: string)
Reponse:
{"tool": "vm_status", "arguments": {}, "missing_args": [], "confidence": 0.90, "reasoning": "vm_status sans args = liste toutes"}

Requete: "supprime sandbox-01"
Specs: vm_destroy(vm_name: string)
Reponse:
{"tool": "vm_destroy", "arguments": {"vm_name": "sandbox-01"}, "missing_args": [], "confidence": 0.95, "reasoning": "supprimer = vm_destroy"}

Requete: "liste les snapshots de preprod-01"
Specs: vm_snapshot(vm_name: string, action: enum(create, list, delete, revert), snapshot_name?: string)
Reponse:
{"tool": "vm_snapshot", "arguments": {"vm_name": "preprod-01", "action": "list"}, "missing_args": [], "confidence": 0.95, "reasoning": "lister snapshots = action list"}

Requete: "liste mes snapshots"
Specs: vm_snapshot(vm_name: string, action: enum(create, list, delete, revert), snapshot_name?: string)
Reponse:
{"tool": "vm_snapshot", "arguments": {"action": "list"}, "missing_args": ["vm_name"], "confidence": 0.85, "reasoning": "liste snapshots mais VM non specifiee"}

Requete: "cree un snapshot de preprod-01"
Specs: vm_snapshot(vm_name: string, action: enum(create, list, delete, revert), snapshot_name?: string)
Reponse:
{"tool": "vm_snapshot", "arguments": {"vm_name": "preprod-01", "action": "create"}, "missing_args": ["snapshot_name"], "confidence": 0.85, "reasoning": "creer snapshot, nom manquant"}

Requete: "fais une snapshot de preprod-01"
Specs: vm_snapshot(vm_name: string, action: enum(create, list, delete, revert), snapshot_name?: string)
Reponse:
{"tool": "vm_snapshot", "arguments": {"vm_name": "preprod-01", "action": "create"}, "missing_args": ["snapshot_name"], "confidence": 0.85, "reasoning": "faire snapshot = creer, extraire VM"}

Requete: "restaure le snapshot pre-update de preprod-01"
Specs: vm_snapshot(vm_name: string, action: enum(create, list, delete, revert), snapshot_name?: string)
Reponse:
{"tool": "vm_snapshot", "arguments": {"vm_name": "preprod-01", "action": "revert", "snapshot_name": "pre-update"}, "missing_args": [], "confidence": 0.95, "reasoning": "restaurer = action revert"}

Requete: "exporte la VM preprod-01"
Specs: vm_export(vm_name: string, mode?: enum(classic, exam) = "classic", output_path?: string, force?: boolean)
Reponse:
{"tool": "vm_export", "arguments": {"vm_name": "preprod-01", "mode": "classic"}, "missing_args": [], "confidence": 0.93, "reasoning": "export VM en mode classic (defaut): supprime comptes/passwords"}

Requete: "exporte preprod-01 en mode examen"
Specs: vm_export(vm_name: string, mode?: enum(classic, exam) = "classic", output_path?: string, force?: boolean)
Reponse:
{"tool": "vm_export", "arguments": {"vm_name": "preprod-01", "mode": "exam"}, "missing_args": [], "confidence": 0.95, "reasoning": "mode exam: conserve comptes/privileges, sanitarise machine-id/SSH/reseau/logs"}

Requete: "importe la VM depuis /home/amineutron/vm-exports/preprod-01-export.tar.gz"
Specs: vm_import(archive_path: string, new_name?: string, start?: boolean)
Reponse:
{"tool": "vm_import", "arguments": {"archive_path": "/home/amineutron/vm-exports/preprod-01-export.tar.gz"}, "missing_args": [], "confidence": 0.93, "reasoning": "import archive tar.gz, nom auto depuis l archive"}

Requete: "importe /tmp/vm.tar.gz sous le nom test-import"
Specs: vm_import(archive_path: string, new_name?: string, start?: boolean)
Reponse:
{"tool": "vm_import", "arguments": {"archive_path": "/tmp/vm.tar.gz", "new_name": "test-import"}, "missing_args": [], "confidence": 0.95, "reasoning": "import avec nouveau nom specifie"}

Requete: "demarre preprod-01 et attends que le ssh soit disponible"
Specs: vm_start(vm_name: string, wait_ssh?: boolean, wait_ip?: boolean)
Reponse:
{"tool": "vm_start", "arguments": {"vm_name": "preprod-01", "wait_ssh": true}, "missing_args": [], "confidence": 0.94, "reasoning": "demarrage VM avec attente SSH explicite: wait_ssh=true"}

Requete: "supprime sandbox-01 mais garde le disque"
Specs: vm_destroy(vm_name: string, force?: boolean, keep_storage?: boolean)
Reponse:
{"tool": "vm_destroy", "arguments": {"vm_name": "sandbox-01", "keep_storage": true}, "missing_args": [], "confidence": 0.95, "reasoning": "destruction VM mais conservation du stockage: keep_storage=true"}

Requete: "execute apt-get update sur preprod-01 avec sudo"
Specs: vm_exec(vm_name: string, command: string, sudo?: boolean)
Reponse:
{"tool": "vm_exec", "arguments": {"vm_name": "preprod-01", "command": "apt-get update", "sudo": true}, "missing_args": [], "confidence": 0.95, "reasoning": "execution commande en mode superutilisateur: sudo=true"}

Requete: "clone preprod-01 en test-cow en mode cow"
Specs: vm_clone(source_vm: string, new_vm_name: string, linked?: boolean, start?: boolean)
Reponse:
{"tool": "vm_clone", "arguments": {"source_vm": "preprod-01", "new_vm_name": "test-cow", "linked": true}, "missing_args": [], "confidence": 0.95, "reasoning": "clone COW (copy-on-write): linked=true economise l'espace disque"}

Requete: "clone preprod-01 en test-clone et demarre la vm apres"
Specs: vm_clone(source_vm: string, new_vm_name: string, linked?: boolean, start?: boolean)
Reponse:
{"tool": "vm_clone", "arguments": {"source_vm": "preprod-01", "new_vm_name": "test-clone", "start": true}, "missing_args": [], "confidence": 0.95, "reasoning": "clone VM avec demarrage automatique post-clone: start=true"}

Requete: "cree un backup timeshift de preprod-01 avec verification integrite"
Specs: backup_create(vm_name: string, type?: string, verify?: boolean, dry_run?: boolean)
Reponse:
{"tool": "backup_create", "arguments": {"vm_name": "preprod-01", "type": "timeshift", "verify": true}, "missing_args": [], "confidence": 0.95, "reasoning": "sauvegarde timeshift avec verification d'integrite: type=timeshift, verify=true"}

Requete: "restaure de force le backup de preprod-01"
Specs: backup_restore(identifier?: string, dry_run?: boolean, force?: boolean)
Reponse:
{"tool": "backup_restore", "arguments": {"identifier": "preprod-01", "force": true}, "missing_args": [], "confidence": 0.94, "reasoning": "restauration forcee sans confirmation: force=true"}

Requete: "verifie en profondeur le backup de preprod-01"
Specs: backup_verify(vm_name?: string, deep?: boolean, quick?: boolean)
Reponse:
{"tool": "backup_verify", "arguments": {"vm_name": "preprod-01", "deep": true}, "missing_args": [], "confidence": 0.95, "reasoning": "verification approfondie du backup: deep=true"}

Requete: "nettoie les backups en gardant les 3 derniers"
Specs: backup_clean(dry_run?: boolean, keep_last?: number)
Reponse:
{"tool": "backup_clean", "arguments": {"keep_last": 3}, "missing_args": [], "confidence": 0.95, "reasoning": "nettoyage avec conservation des 3 sauvegardes les plus recentes: keep_last=3"}

Requete: "exporte preprod-01 vers /mnt/exports"
Specs: vm_export(vm_name: string, mode?: string, output_path?: string, force?: boolean)
Reponse:
{"tool": "vm_export", "arguments": {"vm_name": "preprod-01", "mode": "classic", "output_path": "/mnt/exports"}, "missing_args": [], "confidence": 0.95, "reasoning": "export VM vers repertoire specifique: output_path=/mnt/exports"}

=== EXEMPLES HUE (Lumieres Philips Hue) ===

Requete: "allume les lumieres"
Specs: turn_on_group(group_id?: int), turn_off_group(group_id?: int)
Reponse:
{"tool": "turn_on_group", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "ALLUMER = turn_ON_group. group_id? est OPTIONNEL: missing_args=[]."}

Requete: "eteint les lumieres"
Specs: turn_on_group(group_id?: int), turn_off_group(group_id?: int)
Reponse:
{"tool": "turn_off_group", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "ETEINDRE = turn_OFF_group. group_id? est OPTIONNEL: missing_args=[]."}

Requete: "eteins les lumieres"
Specs: turn_on_group(group_id?: int), turn_off_group(group_id?: int)
Reponse:
{"tool": "turn_off_group", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "eteins = ETEINDRE = turn_OFF_group. group_id? optionnel: missing_args=[]."}

Requete: "allume la lampe 3"
Specs: turn_on_light(light_id: int), turn_off_light(light_id: int)
Reponse:
{"tool": "turn_on_light", "arguments": {"light_id": 3}, "missing_args": [], "confidence": 0.95, "reasoning": "ALLUMER lampe = turn_ON_light"}

Requete: "eteint la lampe du bureau"
Specs: turn_on_light(light_id: int), turn_off_light(light_id: int)
Reponse:
{"tool": "turn_off_light", "arguments": {}, "missing_args": ["light_id"], "confidence": 0.85, "reasoning": "ETEINDRE = turn_OFF, light_id non specifie"}

Requete: "mets la luminosite a 50%"
Specs: set_brightness(light_id: int, brightness: int), set_group_brightness(group_id?: int, brightness: int)
Reponse:
{"tool": "set_group_brightness", "arguments": {"brightness": 127}, "missing_args": [], "confidence": 0.90, "reasoning": "50% de 254 = 127, groupe par defaut"}

Requete: "baisse les lumieres"
Specs: set_group_brightness(group_id?: int, brightness: int), turn_off_group(group_id?: int)
Reponse:
{"tool": "set_group_brightness", "arguments": {}, "missing_args": ["brightness"], "confidence": 0.85, "reasoning": "BAISSER lumieres = reduire luminosite, PAS eteindre. Demander le niveau."}

Requete: "diminue l'intensite"
Specs: set_brightness(light_id: int, brightness: int), set_group_brightness(group_id?: int, brightness: int)
Reponse:
{"tool": "set_group_brightness", "arguments": {"brightness": 50}, "missing_args": [], "confidence": 0.85, "reasoning": "diminuer = baisser la luminosite, valeur basse par defaut"}

Requete: "mets les lumieres en rouge"
Specs: set_color_rgb(light_id: int, r: int, g: int, b: int), set_group_color_rgb(group_id?: int, r: int, g: int, b: int)
Reponse:
{"tool": "set_group_color_rgb", "arguments": {"r": 255, "g": 0, "b": 0}, "missing_args": [], "confidence": 0.95, "reasoning": "rouge = RGB(255,0,0), groupe par defaut"}

Requete: "active la scene Relax"
Specs: activate_scene_by_name(scene_name: string)
Reponse:
{"tool": "activate_scene_by_name", "arguments": {"scene_name": "Relax"}, "missing_args": [], "confidence": 0.95, "reasoning": "scene explicitement nommee"}

=== EXEMPLES TV (Philips TV) ===

Requete: "allume la TV"
Specs: power_on(), power_off()
Reponse:
{"tool": "power_on", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "ALLUMER = power_ON"}

Requete: "eteint la tele"
Specs: power_on(), power_off()
Reponse:
{"tool": "power_off", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "ETEINDRE = power_OFF"}

Requete: "monte le son"
Specs: volume_up(), volume_down(), volume_set(level: int)
Reponse:
{"tool": "volume_up", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "monter = volume_UP"}

Requete: "baisse le volume"
Specs: volume_up(), volume_down(), volume_set(level: int)
Reponse:
{"tool": "volume_down", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "baisser = volume_DOWN"}

Requete: "mets le volume a 20"
Specs: volume_up(), volume_down(), volume_set(level: int)
Reponse:
{"tool": "volume_set", "arguments": {"level": 20}, "missing_args": [], "confidence": 0.95, "reasoning": "valeur explicite = volume_set"}

Requete: "lance Netflix"
Specs: launch_app(app: string)
Reponse:
{"tool": "launch_app", "arguments": {"app": "netflix"}, "missing_args": [], "confidence": 0.95, "reasoning": "app explicitement nommee"}

Requete: "active l'ambilight"
Specs: ambilight_on(), ambilight_off()
Reponse:
{"tool": "ambilight_on", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "activer = ON"}

Requete: "desactive l'ambilight"
Specs: ambilight_on(), ambilight_off()
Reponse:
{"tool": "ambilight_off", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "desactiver = OFF"}

=== EXEMPLES CATT (Cast video) ===

Requete: "caste cette video YouTube"
Specs: cast_youtube(url: string), cast_url(url: string)
Reponse:
{"tool": "cast_youtube", "arguments": {}, "missing_args": ["url"], "confidence": 0.85, "reasoning": "YouTube = cast_youtube, url manquante"}

Requete: "caste https://youtu.be/xxx sur la TV"
Specs: cast_youtube(url: string)
Reponse:
{"tool": "cast_youtube", "arguments": {"url": "https://youtu.be/xxx"}, "missing_args": [], "confidence": 0.95, "reasoning": "URL YouTube fournie"}

Requete: "arrete le cast"
Specs: cast_stop(), cast_pause(), cast_resume()
Reponse:
{"tool": "cast_stop", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "arreter = stop"}

Requete: "pause"
Specs: cast_pause(), cast_resume()
Reponse:
{"tool": "cast_pause", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "pause explicite"}

Requete: "reprends la lecture"
Specs: cast_pause(), cast_resume()
Reponse:
{"tool": "cast_resume", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "reprendre = resume"}

Requete: "avance de 30 secondes"
Specs: cast_seek(seconds: int)
Reponse:
{"tool": "cast_seek", "arguments": {"seconds": 30}, "missing_args": [], "confidence": 0.95, "reasoning": "avancer = seek positif"}

Requete: "recule de 10 secondes"
Specs: cast_seek(seconds: int)
Reponse:
{"tool": "cast_seek", "arguments": {"seconds": -10}, "missing_args": [], "confidence": 0.95, "reasoning": "reculer = seek negatif"}

=== EXEMPLES MERMAID (Diagrammes) ===

Requete: "fait un diagramme pour expliquer le VPN"
Specs: generate_diagram(topic?: string, mermaid_code?: string, title?: string, subtitle?: string, theme?: string, export_format?: string)
Reponse:
{"tool": "generate_diagram", "arguments": {"topic": "VPN"}, "missing_args": [], "confidence": 0.95, "reasoning": "extraire 'VPN' comme topic depuis la phrase"}

Requete: "genere un schema Git"
Specs: generate_diagram(topic?: string, mermaid_code?: string, title?: string, subtitle?: string, theme?: string, export_format?: string)
Reponse:
{"tool": "generate_diagram", "arguments": {"topic": "Git"}, "missing_args": [], "confidence": 0.95, "reasoning": "extraire 'Git' comme topic"}

Requete: "cree un diagramme sur l'architecture Lyra"
Specs: generate_diagram(topic?: string, mermaid_code?: string, title?: string, subtitle?: string, theme?: string, export_format?: string)
Reponse:
{"tool": "generate_diagram", "arguments": {"topic": "Architecture Lyra"}, "missing_args": [], "confidence": 0.90, "reasoning": "extraire 'architecture Lyra' comme topic detaille"}

Requete: "fais un flowchart HTTPS avec legende"
Specs: generate_diagram(topic?: string, mermaid_code?: string, title?: string, subtitle?: string, theme?: string, export_format?: string)
Reponse:
{"tool": "generate_diagram", "arguments": {"topic": "HTTPS"}, "missing_args": [], "confidence": 0.90, "reasoning": "extraire 'HTTPS' comme topic principal"}

Requete: "fais moi un diagramme"
Specs: generate_diagram(topic?: string, mermaid_code?: string, title?: string, subtitle?: string, theme?: string, export_format?: string)
Reponse:
{"tool": "generate_diagram", "arguments": {}, "missing_args": ["topic"], "confidence": 0.85, "reasoning": "diagramme demandé mais aucun sujet specifie, demander le topic"}

Requete: "affiche le dernier diagramme"
Specs: show_diagram(diagram_path: string), list_diagrams()
Reponse:
{"tool": "list_diagrams", "arguments": {}, "missing_args": [], "confidence": 0.80, "reasoning": "besoin de lister d'abord pour trouver le dernier"}

Requete: "liste mes diagrammes"
Specs: list_diagrams(), show_diagram(diagram_path: string)
Reponse:
{"tool": "list_diagrams", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "lister les diagrammes disponibles"}

=== EXEMPLES SCREEN-MANAGER (Gestion multi-ecrans) ===

Requete: "ouvre firefox sur le 2e ecran"
Specs: open_app(app_name: string, screen: string, url?: string)
Reponse:
{"tool": "open_app", "arguments": {"app_name": "firefox", "screen": "2e ecran"}, "missing_args": [], "confidence": 0.95, "reasoning": "app=firefox, screen extrait apres 'sur'"}

Requete: "lance btop sur l'ecran de gauche"
Specs: open_app(app_name: string, screen: string, url?: string)
Reponse:
{"tool": "open_app", "arguments": {"app_name": "btop", "screen": "ecran de gauche"}, "missing_args": [], "confidence": 0.95, "reasoning": "app=btop, destination=ecran de gauche"}

Requete: "affiche worldmonitor.app sur la tele"
Specs: open_url(url: string, screen: string)
Reponse:
{"tool": "open_url", "arguments": {"url": "https://worldmonitor.app", "screen": "tele"}, "missing_args": [], "confidence": 0.94, "reasoning": "URL + destination ecran"}

Requete: "quels sont mes ecrans"
Specs: list_screens()
Reponse:
{"tool": "list_screens", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "lister les ecrans disponibles"}

Requete: "liste les applications disponibles"
Specs: list_apps(filter?: string)
Reponse:
{"tool": "list_apps", "arguments": {}, "missing_args": [], "confidence": 0.93, "reasoning": "lister toutes les apps"}

Requete: "configure mes ecrans"
Specs: setup_screens(aliases?: dict)
Reponse:
{"tool": "setup_screens", "arguments": {}, "missing_args": [], "confidence": 0.92, "reasoning": "detection et configuration des ecrans"}

Requete: "renomme l'ecran 2 en bureau"
Specs: update_screen_config(screen_index: int, alias?: string, aliases?: list)
Reponse:
{"tool": "update_screen_config", "arguments": {"screen_index": 2, "alias": "bureau"}, "missing_args": [], "confidence": 0.92, "reasoning": "screen_index=2, alias=bureau"}

Si AUCUN outil ne correspond:
{"tool": null, "arguments": {}, "missing_args": [], "confidence": 0.0, "reasoning": "Pas d'outil MCP pour cette requete"}

FORMAT TOON:
Les specs MCP peuvent etre fournies en format TOON (compact).
Format: [count]{champ1,champ2,...}: suivi de lignes de valeurs.
Exemple:
[2]{outil,serveur,desc,req,opt,schema}:
turn_on_group,hue,Allume les lumieres,,group_id,"group_id(integer):ID du groupe"
turn_off_group,hue,Eteint les lumieres,,group_id,"group_id(integer):ID du groupe"
Ici: outil=nom, serveur=serveur MCP, desc=description, req=params obligatoires, opt=params optionnels, schema=details params.
"""


class Ephaistos:
    """EPHAISTOS - Moteur d'analyse backend.

    Utilise Qwen 2.5 Coder (0.5B actif, 7B backup) pour:
    - Analyser les specs MCP depuis le RAG
    - Extraire les arguments de la requete utilisateur
    - Identifier les arguments manquants
    - Valider les arguments complets
    """

    def __init__(self, model_manager: ModelManager):
        """Initialise EPHAISTOS.

        Args:
            model_manager: Gestionnaire de modeles
        """
        self.model_manager = model_manager

    # Mapping verbes FR → tokens EN presents dans les noms d'outils MCP
    _FR_ACTION_MAP = {
        "demarre": "start", "demarrer": "start", "redemarre": "start",
        "allume": "on", "allumer": "on", "active": "on", "activer": "on",
        "arrete": "stop", "arreter": "stop", "stoppe": "stop",
        "eteins": "off", "eteindre": "off", "eteint": "off", "coupe": "off",
        "clone": "clone", "cloner": "clone",
        "backup": "backup", "sauvegarde": "backup",
        "snapshot": "snapshot", "instantane": "snapshot",
        "restaure": "restore", "revert": "revert",
        "liste": "status", "statut": "status", "etat": "status",
        "verifie": "verify", "verif": "verify",
        "detruit": "destroy", "supprime": "destroy", "efface": "destroy",
        "caste": "cast", "diffuse": "cast",
        "pause": "pause", "mets en pause": "pause",
        "reprends": "resume", "continue": "resume",
        "monte": "up", "augmente": "up",
        "baisse": "down", "diminue": "down",
        "volume": "volume", "son": "volume",
        "lance": "launch", "ouvre": "launch",
        "exec": "exec", "execute": "exec",
    }

    @classmethod
    def _boost_spec_order(cls, compact_specs: list[str], user_query: str) -> list[str]:
        """Re-trie les specs compactes: met en premier celle qui correspond au verbe d action."""
        query_lower = user_query.lower()

        def relevance(spec):
            # Extraire le nom court de l'outil (ex: "vm_start" depuis "fedora.vm_start: ...")
            tool_name = spec.split(":")[0].split(".")[-1].lower() if ":" in spec else spec.lower()
            score = 0
            for fr, en in cls._FR_ACTION_MAP.items():
                if fr in query_lower and en in tool_name:
                    score += 2
            return score

        return sorted(compact_specs, key=relevance, reverse=True)

    @staticmethod
    def _compact_spec(doc: str) -> str:
        """Extrait nom+signature depuis un doc ChromaDB verbeux.

        Input:  'fedora.vm_start (FEDORA) Signature: vm_start(vm_name: string, ...) Demarre...'
        Output: 'fedora.vm_start: vm_start(vm_name: string, ...)'
        """
        # Extraire l'identifiant de l'outil (premier token)
        name_m = re.match(r'^(\S+)', doc)
        if not name_m:
            return doc[:200]

        tool_id = name_m.group(1)

        # Extraire la signature: apres "Signature: " jusqu'au ) terminal avant description
        # Le ) de la signature est suivi d'un espace puis d'une maj ou d'un mot-cle
        sig_m = re.search(
            r'Signature:\s+(.+?\))\s*(?=[A-Z\u00C0-\u024F]|Utilise|Exemple|$)',
            doc,
            re.DOTALL
        )
        if sig_m:
            sig = ' '.join(sig_m.group(1).split())  # Normaliser whitespace
            return f"{tool_id}: {sig}"

        # Fallback: tronquer
        return doc[:200]

    def analyze(
        self,
        user_query: str,
        mcp_specs: list[str],
        known_args: Optional[dict] = None,
        specs_toon: Optional[str] = None,
        max_specs: int = 0
    ) -> EphaistosAnalysis:
        """Analyse une requete avec les specs MCP.

        Args:
            user_query: Requete utilisateur en francais
            mcp_specs: Specs MCP pertinentes (depuis RAG)
            known_args: Arguments deja connus (contexte multi-tour)
            specs_toon: Specs pre-encodees en TOON (prioritaire si fourni)

        Returns:
            EphaistosAnalysis avec l'outil et arguments
        """
        # Utiliser TOON si disponible, sinon extraire signatures compactes
        if specs_toon:
            specs_text = specs_toon
            label = "SPECS MCP (TOON)"
        else:
            compact_specs = [self._compact_spec(s) for s in mcp_specs]
            # Re-trier: mettre en premier la spec qui correspond au verbe d'action
            compact_specs = self._boost_spec_order(compact_specs, user_query)
            # Limiter le nombre de specs si demande (0 = toutes)
            if max_specs > 0:
                compact_specs = compact_specs[:max_specs]
            specs_text = "\n".join(compact_specs)
            label = "SPECS MCP"

        prompt = f"""{label}:
{specs_text}

REQUETE: {user_query}"""

        if known_args:
            prompt += f"\nARGS CONNUS: {json.dumps(known_args, ensure_ascii=False)}"

        prompt += "\nJSON:"

        # Appeler EPHAISTOS
        response = self.model_manager.call_ephaistos(
            prompt=prompt,
            system_prompt=EPHAISTOS_SYSTEM_PROMPT
        )

        if not response.success:
            return EphaistosAnalysis(
                tool=None,
                arguments={},
                missing_args=[],
                confidence=0.0,
                reasoning=f"Erreur: {response.error}",
                raw_response=""
            )

        # Parser la reponse JSON
        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> EphaistosAnalysis:
        """Parse la reponse JSON d'EPHAISTOS.

        Args:
            content: Contenu de la reponse

        Returns:
            EphaistosAnalysis
        """
        raw = content
        # Nettoyer le contenu
        content = content.strip()

        # Enlever les blocs markdown (plusieurs formats)
        content = re.sub(r'```(?:json)?\s*', '', content)
        content = content.strip()

        try:
            # Methode 1: JSON direct
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Methode 2: Extraire le premier objet JSON (gere les nested objects)
                brace_count = 0
                start = -1
                end = -1

                for i, char in enumerate(content):
                    if char == '{':
                        if brace_count == 0:
                            start = i
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0 and start != -1:
                            end = i + 1
                            break

                if start != -1 and end != -1:
                    json_str = content[start:end]
                    data = json.loads(json_str)
                else:
                    raise json.JSONDecodeError("No JSON found", content, 0)

            # Normaliser les cles (certains modeles utilisent des variantes)
            # "command", "function", "name" → "tool"
            if "tool" not in data:
                for alt in ("command", "function", "name"):
                    if alt in data and isinstance(data[alt], str):
                        data["tool"] = data[alt]
                        break
            # "parameters", "args", "params" → "arguments"
            if "arguments" not in data:
                for alt in ("parameters", "args", "params"):
                    if alt in data and isinstance(data[alt], dict):
                        data["arguments"] = data[alt]
                        break

            # Normaliser les types
            tool = data.get("tool")
            if tool == "null" or tool == "":
                tool = None

            arguments = data.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            else:
                # Supprimer les valeurs None (args optionnels non specifies)
                arguments = {k: v for k, v in arguments.items() if v is not None}

            missing_args = data.get("missing_args", [])
            if not isinstance(missing_args, list):
                missing_args = []

            confidence = data.get("confidence", 0.5)
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except:
                    confidence = 0.5

            return EphaistosAnalysis(
                tool=tool,
                arguments=arguments,
                missing_args=missing_args,
                confidence=confidence,
                reasoning=data.get("reasoning", ""),
                raw_response=raw
            )

        except json.JSONDecodeError:
            # Fallback: essayer d'extraire les infos avec regex
            tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', content)
            tool = tool_match.group(1) if tool_match else None

            return EphaistosAnalysis(
                tool=tool,
                arguments={},
                missing_args=[],
                confidence=0.0,
                reasoning=f"Parse error: {content[:200]}",
                raw_response=raw
            )

    def extract_missing_args(
        self,
        analysis: EphaistosAnalysis,
        user_response: str
    ) -> EphaistosAnalysis:
        """Extrait les arguments manquants d'une reponse utilisateur.

        Utilise pour le multi-tour: l'utilisateur repond a une question
        de clarification et on extrait les nouvelles valeurs.

        Args:
            analysis: Analyse precedente avec missing_args
            user_response: Reponse de l'utilisateur

        Returns:
            EphaistosAnalysis mise a jour avec les nouveaux arguments
        """
        if not analysis.missing_args:
            return analysis

        prompt = f"""OUTIL: {analysis.tool}
ARGUMENTS DEJA CONNUS: {json.dumps(analysis.arguments, ensure_ascii=False)}
ARGUMENTS MANQUANTS: {analysis.missing_args}

REPONSE UTILISATEUR: {user_response}

Extrait les valeurs des arguments manquants depuis la reponse.
Reponds en JSON avec la meme structure:
{{
  "tool": "{analysis.tool}",
  "arguments": {{"...tous les args connus + nouveaux..."}},
  "missing_args": ["args encore manquants"],
  "confidence": 0.95,
  "reasoning": "explication"
}}
"""

        response = self.model_manager.call_ephaistos(
            prompt=prompt,
            system_prompt=EPHAISTOS_SYSTEM_PROMPT
        )

        if not response.success:
            return analysis

        new_analysis = self._parse_response(response.content)

        # Merge avec les arguments existants
        merged_args = {**analysis.arguments, **new_analysis.arguments}
        new_analysis.arguments = merged_args

        return new_analysis

    def validate_arguments(
        self,
        tool_name: str,
        arguments: dict,
        tool_spec: str
    ) -> dict:
        """Valide les arguments avant execution.

        Args:
            tool_name: Nom de l'outil
            arguments: Arguments a valider
            tool_spec: Spec de l'outil

        Returns:
            Dict avec "valid", "errors", "warnings"
        """
        prompt = f"""OUTIL: {tool_name}
SPEC: {tool_spec}
ARGUMENTS A VALIDER: {json.dumps(arguments, ensure_ascii=False)}

Valide les arguments. Reponds en JSON:
{{
  "valid": true/false,
  "errors": ["erreur1", ...],
  "warnings": ["warning1", ...]
}}
"""

        response = self.model_manager.call_ephaistos(
            prompt=prompt,
            system_prompt="Tu valides des arguments MCP. Reponds uniquement en JSON."
        )

        if not response.success:
            return {"valid": True, "errors": [], "warnings": []}

        try:
            content = response.content.strip()
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            return json.loads(content)
        except:
            return {"valid": True, "errors": [], "warnings": []}

    def analyze_with_retry(
        self,
        user_query: str,
        mcp_specs: list[str],
        max_retries: int = 2,
        specs_toon: Optional[str] = None
    ) -> EphaistosAnalysis:
        """Analyse avec retry automatique si le parsing echoue.

        Args:
            user_query: Requete utilisateur
            mcp_specs: Specs MCP pertinentes
            max_retries: Nombre de tentatives
            specs_toon: Specs pre-encodees en TOON

        Returns:
            EphaistosAnalysis
        """
        for attempt in range(max_retries):
            # Strategie par tentative:
            # attempt 0: top-1 spec (si pas TOON) — plus simple, moins de confusion
            # attempt 1: top-3 specs — fallback si top-1 ne suffit pas
            if specs_toon:
                use_toon = specs_toon if attempt == 0 else None
                use_max_specs = 0
            else:
                use_toon = None
                use_max_specs = 1 if attempt == 0 else 3

            analysis = self.analyze(user_query, mcp_specs, specs_toon=use_toon, max_specs=use_max_specs)

            # Si on a un outil valide, retourner
            if analysis.tool is not None:
                return analysis

            # Si confidence=0.0 = "pas d'outil MCP pour cette requete" (intentionnel)
            if analysis.confidence == 0.0:
                return analysis

            # Sinon: format incorrect → retry avec plus de specs

            # Si c'est une erreur de parsing, reessayer avec prompt simplifie
            if "Parse error" in analysis.reasoning:
                continue

        return analysis
