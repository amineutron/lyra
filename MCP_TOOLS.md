# Lyra - Liste des Outils MCP

Liste complète des 85 outils MCP disponibles dans Lyra.

## FEDORA (17 outils) - VM KVM et Backups

### VM Controller

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `vm_start` | Démarre une VM KVM | `vm_name` (string) |
| `vm_stop` | Arrête une VM KVM | `vm_name` (string), `force` (bool, optionnel) |
| `vm_destroy` | Supprime définitivement une VM | `vm_name` (string) |
| `vm_status` | Affiche le statut d'une ou toutes les VMs | `vm_name` (string, optionnel) |
| `vm_exec` | Exécute une commande dans une VM | `vm_name` (string), `command` (string) |
| `vm_copy` | Copie des fichiers vers/depuis une VM | `vm_name` (string), `local_path` (string), `remote_path` (string) |
| `vm_snapshot` | Crée un snapshot d'une VM | `vm_name` (string), `snapshot_name` (string) |
| `vm_clone` | Clone une VM | `source_vm` (string), `new_vm_name` (string), `start` (bool, optionnel) |
| `vm_clone_system` | Clone le PC hote vers une VM (defaut: LEGER — interface/configs sans ~/dev, modeles IA ni secrets) | `name` (string), `full` (bool, optionnel: clone complet) |
| `vm_verify` | Vérifie l'intégrité d'une VM | `vm_name` (string) |

### Backup Manager

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `backup_create` | Crée un backup d'une VM | `vm_name` (string) |
| `backup_list` | Liste les backups disponibles | `vm_name` (string, optionnel) |
| `backup_restore` | Restaure un backup | `vm_name` (string), `backup_name` (string) |
| `backup_verify` | Vérifie l'intégrité d'un backup | `backup_name` (string) |
| `backup_clean` | Nettoie les anciens backups | `vm_name` (string), `keep` (int) |
| `backup_status` | Dashboard global des backups | - |

---

## TV (14 outils) - Philips 55OLED705/12

### Power

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `tv.power_on` | Allume la TV | - |
| `tv.power_off` | Éteint la TV (standby) | - |

### Volume

**IMPORTANT:** Avec HDMI ARC actif, les commandes volume sont automatiquement redirigées vers le Denon.

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `tv.volume_set` | Règle le volume | `level` (int, 0-60 pour TV, 0-98 pour Denon) |
| `tv.volume_up` | Augmente le volume | `step` (int, default: 5) |
| `tv.volume_down` | Baisse le volume | `step` (int, default: 5) |
| `tv.mute` | Toggle mute | - |

### Ambilight

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `tv.ambilight_on` | Active l'Ambilight | - |
| `tv.ambilight_off` | Désactive l'Ambilight | - |
| `tv.ambilight_set_color` | Change la couleur Ambilight | `r` (int), `g` (int), `b` (int) |
| `tv.ambilight_set_mode` | Change le mode Ambilight | `mode` (string: internal, manual, expert) |

### Applications

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `tv.launch_app` | Lance une application | `app_id` (string) |
| `tv.youtube_video` | Lance une vidéo YouTube | `video_id` (string) |
| `tv.get_state` | Statut de la TV | - |

---

## HUE (24 outils) - Philips Hue Bridge @ 192.168.1.51

### Lumières individuelles

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `hue.turn_on_light` | Allume une lumière | `light_id` (int ou string) |
| `hue.turn_off_light` | Éteint une lumière | `light_id` (int ou string) |
| `hue.set_brightness` | Règle la luminosité | `light_id` (int/string), `brightness` (int, 0-254) |
| `hue.set_color_rgb` | Change la couleur RGB | `light_id` (int/string), `r`, `g`, `b` (int, 0-255) |
| `hue.set_color_temp` | Règle la température de couleur | `light_id` (int/string), `temp` (int, 153-500) |
| `hue.get_light_state` | État d'une lumière | `light_id` (int ou string) |

### Groupes

Groupe par défaut : **81** (Chambre à coucher)

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `hue.turn_on_group` | Allume un groupe | `group_id` (int ou string) |
| `hue.turn_off_group` | Éteint un groupe | `group_id` (int ou string) |
| `hue.set_group_brightness` | Luminosité du groupe | `group_id` (int/string), `brightness` (int, 0-254) |
| `hue.set_group_color_rgb` | Couleur RGB du groupe | `group_id` (int/string), `r`, `g`, `b` (int, 0-255) |
| `hue.set_group_color_temp` | Température du groupe | `group_id` (int/string), `temp` (int, 153-500) |
| `hue.get_group_state` | État d'un groupe | `group_id` (int ou string) |

### Scènes

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `hue.activate_scene` | Active une scène (par ID) | `scene_id` (string) |
| `hue.activate_scene_by_name` | Active une scène (par nom) | `scene_name` (string) |
| `hue.list_scenes` | Liste toutes les scènes | - |

### Listing

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `hue.get_all_lights` | Liste toutes les lumières | - |
| `hue.get_all_groups` | Liste tous les groupes | - |
| `hue.get_bridge_info` | Infos du bridge | - |

### Autres

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `hue.turn_on_all` | Allume toutes les lumières | - |
| `hue.turn_off_all` | Éteint toutes les lumières | - |
| `hue.set_brightness_all` | Luminosité globale | `brightness` (int, 0-254) |
| `hue.set_color_rgb_all` | Couleur RGB globale | `r`, `g`, `b` (int, 0-255) |
| `hue.toggle_light` | Toggle une lumière | `light_id` (int ou string) |
| `hue.toggle_group` | Toggle un groupe | `group_id` (int ou string) |

---

## CATT (15 outils) - Cast YouTube/Video vers TV

Device : **55OLED705/12** (Chromecast/DLNA)

### Cast

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `cast_browser` | Caste l'onglet actif Firefox | - |
| `cast_youtube` | Caste une vidéo YouTube | `url` (string) |
| `cast_url` | Caste une URL vidéo/audio | `url` (string) |

### Contrôle

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `cast_stop` | Arrête le cast | - |
| `cast_pause` | Met en pause | - |
| `cast_resume` | Reprend la lecture | - |
| `cast_volume` | Règle le volume du cast | `level` (int, 0-100) |
| `cast_seek` | Avance/recule (secondes) | `seconds` (int, négatif = reculer) |

### Info

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `cast_status` | Statut du cast en cours | - |
| `cast_scan` | Liste les devices disponibles | - |

---

## DENON (10 outils) - Home Cinema AVR-X1700H DAB @ 192.168.1.52

**IMPORTANT:** Les commandes `tv.volume_*` sont automatiquement redirigées vers le Denon quand HDMI ARC est actif.

### Volume

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `denon.volume_set` | Règle le volume (0-98, 80 = 0dB) | `level` (int, 0-98) |
| `denon.volume_up` | Augmente le volume | `step` (int, default: 1) |
| `denon.volume_down` | Baisse le volume | `step` (int, default: 1) |

### Mute

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `denon.mute_on` | Active le mute | - |
| `denon.mute_off` | Désactive le mute | - |
| `denon.mute_toggle` | Toggle le mute | - |

### Power

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `denon.power_on` | Allume le Denon | - |
| `denon.power_off` | Éteint le Denon (standby) | - |

### Source

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `denon.set_input` | Change la source | `source` (string: BD, TV, GAME, SAT/CBL, DVD, MPLAY) |

### Info

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `denon.get_status` | Statut du Denon | - |

---

## Récapitulatif

| Serveur MCP | Nombre d'outils | Catégories |
|-------------|-----------------|------------|
| **FEDORA** | 17 | VM (10) + Backup (7) |
| **TV** | 14 | Power (2) + Volume (4) + Ambilight (4) + Apps (4) |
| **HUE** | 24 | Lumières (6) + Groupes (6) + Scènes (3) + Listing (3) + Autres (6) |
| **CATT** | 15 | Cast (3) + Contrôle (6) + Info (2) |
| **DENON** | 10 | Volume (3) + Mute (3) + Power (2) + Source (1) + Info (1) |
| **TOTAL** | **80** | - |

---

## Notes importantes

### HDMI ARC et redirection automatique

Quand un home cinéma Denon est connecté en **HDMI ARC/eARC** à la TV :
- Le volume de la TV est désactivé (sortie audio via HDMI)
- Les commandes `tv.volume_*` et `tv.mute` sont **automatiquement redirigées** vers `denon.*`
- Vous pouvez utiliser indifféremment `tv.volume_set 44` ou `denon.volume_set 44`

### Échelles de volume

- **TV Philips** : 0-60
- **Denon AVR** : 0-98 (où 80 = 0dB référence)
- **Cast (CATT)** : 0-100

### Mode Performance

En mode performance (`./run.sh -p`), les outils domotique (TV, Hue, Catt, Denon) s'exécutent **sans confirmation**. Les outils VM/Backup dangereux gardent la confirmation obligatoire.

### Groupes Hue par défaut

- **Groupe 81** : Chambre à coucher (groupe principal)
- **Groupe 0** : Toutes les lumières (n'existe pas, utiliser `hue.turn_on_all` à la place)

---

## MERMAID (5 outils) - Génération de diagrammes

### Génération

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `generate_diagram` | Génère un diagramme Mermaid avec template HTML | `mermaid_code` (string), `title` (string), `subtitle` (string, opt), `colors` (object, opt), `extra_content` (string, opt), `theme` (string, opt), `export_format` (string, opt: html/png/svg) |
| `validate_diagram` | Valide la syntaxe d'un code Mermaid | `mermaid_code` (string) |

### Affichage

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `show_diagram` | Affiche un diagramme dans le navigateur | `diagram_path` (string) |
| `set_display_mode` | Configure l'affichage auto des diagrammes | `mode` (string: ask/always/never) |
| `list_diagrams` | Liste tous les diagrammes générés | - |

### Exemples d'utilisation

```
"Génère-moi un diagramme de l'architecture Lyra"
"Fais-moi un flowchart avec légende"
"Crée un diagramme Mermaid de la structure du projet"
"Liste mes diagrammes"
"Affiche le dernier diagramme"
```

### Fonctionnalités

- **Template HTML** : Diagrammes professionnels avec Mermaid.js intégré
- **Légendes automatiques** : Couleurs et composants expliqués
- **Export multiple** : HTML (interactif), PNG, SVG
- **Validation** : Vérification de syntaxe avant génération
- **Bonnes pratiques** : Applique automatiquement les règles de `MERMAID_BEST_PRACTICES.md`
- **Gestion de session** : Mode d'affichage configurable (ask/always/never)
