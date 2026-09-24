# Lyra - Liste des outils MCP

Genere le 2026-09-24 par `scripts/gen_mcp_tools_md.py` depuis les serveurs configures (88 outils, 5 serveurs). Ne pas editer a la main : relancer le script.

Colonne confirmation (source : `lyra/core/constants.py`) :

- **DESTRUCTIF** : perte ou ecrasement irreversible ; banniere rouge, `o`/`oui` obligatoire, jamais auto-confirme (`-y`, `-p`).
- **SENSIBLE** : ecrit, execute une commande ou coupe une machine ; `o`/`oui` obligatoire, jamais auto-confirme.
- **sans confirmation en mode performance** : domotique reversible ; en mode par defaut, confirmation `[O/n]`.
- **confirmation [O/n]** : Entree vaut oui.

## FEDORA - VM KVM et sauvegardes (fedora-agents) (19 outils)

| Outil | Description | Arguments | Confirmation |
|---|---|---|---|
| `fedora.backup_clean` | Applique les politiques de rétention et supprime les anciens backups ⚠️ ATTENTION: Opération potentiellement... | `type` (string: timeshift/borg/vm/manual/all), `dry_run` (boolean, opt), `force` (boolean, opt), `keep_last` (number, opt) | DESTRUCTIF : oui explicite, jamais auto-confirme |
| `fedora.backup_create` | Crée un backup (timeshift, borg, vm-snapshot, ou manual) | `type` (string: timeshift/borg/vm-snapshot/manual), `comment` (string, opt), `verify` (boolean, opt), `notify` (boolean, opt), `dry_run` (boolean, opt), `vm` (string, opt), `live` (boolean, opt), `source` (string, opt), `dest` (string, opt), `timeout_ms` (number, opt) | confirmation [O/n] |
| `fedora.backup_list` | Liste tous les backups disponibles (par type ou tous) | `all` (boolean, opt), `type` (string: timeshift/borg/vm-snapshot/manual, opt), `detailed` (boolean, opt), `limit` (number, opt), `sort` (string: date/type/size, opt) | confirmation [O/n] |
| `fedora.backup_restore` | Restaure un backup (ATTENTION: opération destructive!) ⚠️ ATTENTION: Opération potentiellement destructive! | `type` (string: timeshift/borg/vm-snapshot/manual), `identifier` (string), `dry_run` (boolean, opt), `force` (boolean, opt), `partial` (string, opt), `target` (string, opt), `skip_pre_snapshot` (boolean, opt) | DESTRUCTIF : oui explicite, jamais auto-confirme |
| `fedora.backup_status` | Affiche le dashboard global des backups (status, espace, alertes) | `watch` (boolean, opt), `compact` (boolean, opt) | confirmation [O/n] |
| `fedora.backup_verify` | Vérifie l'intégrité des backups | `type` (string: timeshift/borg/vm/all, opt), `deep` (boolean, opt), `quick` (boolean, opt), `backup_id` (string, opt), `timeout_ms` (number, opt) | confirmation [O/n] |
| `fedora.help` | Liste tous les outils disponibles avec leurs descriptions. Appelle cet outil en premier pour savoir ce que tu... | - | confirmation [O/n] |
| `fedora.vm_clone` | Clone une VM KVM existante (complet ou lié) | `source_vm` (string), `new_vm_name` (string), `start` (boolean, opt), `autostart` (boolean, opt), `linked` (boolean, opt), `network` (string, opt), `timeout_ms` (number, opt), `tracking_session_id` (string, opt) | confirmation [O/n] |
| `fedora.vm_clone_system` | Clone le système hôte entier vers une VM KVM bootable ⚠️ ATTENTION: Opération potentiellement destructive! | `name` (string, opt), `disk_size` (string, opt), `memory` (number, opt), `cpus` (number, opt), `hostname` (string, opt), `username` (string, opt), `dry_run` (boolean, opt), `timeout_ms` (number, opt) | SENSIBLE : oui explicite, jamais auto-confirme |
| `fedora.vm_copy` | Copie des fichiers entre l'hôte et une VM via SCP ⚠️ ATTENTION: Opération potentiellement destructive! | `vm_name` (string), `source` (string), `dest` (string), `direction` (string: to_vm/from_vm, opt), `recursive` (boolean, opt), `checksum` (boolean, opt), `preserve` (boolean, opt) | SENSIBLE : oui explicite, jamais auto-confirme |
| `fedora.vm_destroy` | Supprime complètement une VM KVM (définition + stockage) ⚠️ ATTENTION: Opération potentiellement destructive! | `vm_name` (string), `force` (boolean, opt), `keep_storage` (boolean, opt) | DESTRUCTIF : oui explicite, jamais auto-confirme |
| `fedora.vm_exec` | Exécute une commande dans une VM via SSH ⚠️ ATTENTION: Opération potentiellement destructive! | `vm_name` (string), `command` (string), `user` (string, opt), `sudo` (boolean, opt), `timeout` (number, opt), `capture` (boolean, opt) | SENSIBLE : oui explicite, jamais auto-confirme |
| `fedora.vm_export` | Exporte une VM KVM dans une archive portable (.tar.gz) avec sanitarisation des donnees sensibles. Mode... | `vm_name` (string), `mode` (string: classic/exam/custom, opt), `output_path` (string, opt), `force` (boolean, opt), `dry_run` (boolean, opt), `operations` (array, opt), `firstboot` (boolean, opt) | confirmation [O/n] |
| `fedora.vm_import` | Importe une VM KVM depuis une archive exportee par vm_export. Effectue un test pre-import (integrite archive... | `archive_path` (string), `new_name` (string, opt), `pool_dir` (string, opt), `start` (boolean, opt), `dry_run` (boolean, opt) | SENSIBLE : oui explicite, jamais auto-confirme |
| `fedora.vm_snapshot` | Gère les snapshots d'une VM (create, list, restore, delete) ⚠️ ATTENTION: Opération potentiellement... | `vm_name` (string), `action` (string: create/list/restore/delete/delete-all), `snapshot_name` (string, opt), `description` (string, opt), `live` (boolean, opt), `yes` (boolean, opt) | SENSIBLE : oui explicite, jamais auto-confirme |
| `fedora.vm_start` | Démarre une VM KVM et attend optionnellement que SSH soit accessible | `vm_name` (string), `wait_ssh` (boolean, opt), `wait_ip` (boolean, opt), `timeout` (number, opt) | confirmation [O/n] |
| `fedora.vm_status` | Affiche le status et les informations d'une VM (IP, SSH, ressources). Sans vm_name, liste toutes les VMs. | `vm_name` (string, opt), `detailed` (boolean, opt), `json` (boolean, opt) | confirmation [O/n] |
| `fedora.vm_stop` | Arrête une VM KVM proprement (ou force l'arrêt avec --force) ⚠️ ATTENTION: Opération potentiellement... | `vm_name` (string), `force` (boolean, opt), `wait` (boolean, opt), `timeout` (number, opt) | SENSIBLE : oui explicite, jamais auto-confirme |
| `fedora.vm_verify` | Vérifie qu'une VM clonée est une copie fidèle du système hôte | `vm_name` (string, opt), `ip` (any, opt), `user` (string, opt), `self_check` (boolean, opt), `verbose` (boolean, opt), `quick` (boolean, opt), `save_report` (boolean, opt), `compare_packages` (boolean, opt), `compare_content` (boolean, opt) | confirmation [O/n] |

## TV - Philips Android TV (pylips-mcp) (16 outils)

| Outil | Description | Arguments | Confirmation |
|---|---|---|---|
| `tv.ambilight_mode` | Change le mode Ambilight | `mode` (string: follow_video/follow_audio/lounge_light/manual/video_immersive/audio_spectrum) | sans confirmation en mode performance (-p) |
| `tv.ambilight_off` | Desactive l'Ambilight de la TV | - | sans confirmation en mode performance (-p) |
| `tv.ambilight_on` | Active l'Ambilight de la TV | - | sans confirmation en mode performance (-p) |
| `tv.get_state` | Retourne l'etat actuel de la TV : powerstate (On/Standby), volume, muted, ambilight_on, ambilight_mode | - | sans confirmation en mode performance (-p) |
| `tv.launch_app` | Lance une application sur la TV | `app` (string: netflix/youtube/plex/disney/prime) | sans confirmation en mode performance (-p) |
| `tv.list_apps` | Liste les applications disponibles sur la TV | - | sans confirmation en mode performance (-p) |
| `tv.mute` | Coupe ou remet le son de la TV | - | sans confirmation en mode performance (-p) |
| `tv.power_off` | Eteint la TV Philips (standby) | - | sans confirmation en mode performance (-p) |
| `tv.power_on` | Allume la TV Philips | - | sans confirmation en mode performance (-p) |
| `tv.screen_off` | Eteint l'ecran de la TV tout en gardant le son actif (mode musique). Note: fonctionne principalement en... | - | sans confirmation en mode performance (-p) |
| `tv.screen_on` | Rallume l'ecran de la TV apres un screen_off | - | sans confirmation en mode performance (-p) |
| `tv.send_key` | Envoie une touche de telecommande | `key` (string) | confirmation [O/n] |
| `tv.volume_down` | Baisse le volume de la TV (default -5) | `step` (integer, opt) | sans confirmation en mode performance (-p) |
| `tv.volume_set` | Regle le volume a un niveau specifique | `level` (integer) | sans confirmation en mode performance (-p) |
| `tv.volume_up` | Augmente le volume de la TV (default +5) | `step` (integer, opt) | sans confirmation en mode performance (-p) |
| `tv.youtube_video` | Lance YouTube sur une video specifique (URL youtube ou ID de video) | `video` (string) | sans confirmation en mode performance (-p) |

## HUE - Lumieres Philips Hue (hue-mcp) (28 outils)

| Outil | Description | Arguments | Confirmation |
|---|---|---|---|
| `hue.activate_scene_by_name` | Find and activate a scene by its name (partial match, accent-insensitive). Args: scene_name: Name of the... | `scene_name` (string), `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.alert_light` | Make a light flash briefly to identify it. Args: light_id: The ID of the light to alert Returns: Confirmation... | `light_id` (integer) | sans confirmation en mode performance (-p) |
| `hue.create_group` | Create a new group of lights. Args: name: Name for the new group light_ids: List of light IDs to include in... | `name` (string), `light_ids` (array) | confirmation [O/n] |
| `hue.find_light_by_name` | Find lights by searching their names. Args: name: Partial or full name to search for Returns: JSON string... | `name` (string) | sans confirmation en mode performance (-p) |
| `hue.get_all_groups` | Get information about all light groups. Returns: JSON string containing information about all groups | - | sans confirmation en mode performance (-p) |
| `hue.get_all_lights` | Get information about all lights connected to the Hue bridge. Returns: JSON string containing information... | - | sans confirmation en mode performance (-p) |
| `hue.get_all_scenes` | Get information about all scenes. Returns: JSON string containing information about all scenes | - | sans confirmation en mode performance (-p) |
| `hue.get_group` | Get information about a specific light group. Args: group_id: The ID of the group Returns: JSON string... | `group_id` (integer) | sans confirmation en mode performance (-p) |
| `hue.get_light` | Get detailed information about a specific light. Args: light_id: The ID of the light Returns: JSON string... | `light_id` (integer) | sans confirmation en mode performance (-p) |
| `hue.hue_beat_set` | Modifie les parametres de hue_beat a chaud (sans redemarrage). Args: palette: ironman / fire / neon / cool /... | `palette` (string, opt), `mode` (string, opt), `brightness` (number, opt), `floor` (number, opt), `sensitivity` (number, opt) | sans confirmation en mode performance (-p) |
| `hue.hue_beat_start` | Lance hue_beat.py en arriere-plan (Entertainment API DTLS ~5ms). Pendant que hue_beat tourne, les commandes... | `mode` (string, opt), `palette` (string, opt), `bass_only` (boolean, opt) | sans confirmation en mode performance (-p) |
| `hue.hue_beat_status` | Retourne l'etat de hue_beat (actif/inactif, mode, palette, BPM). | - | sans confirmation en mode performance (-p) |
| `hue.hue_beat_stop` | Arrete hue_beat proprement (SIGTERM → stop_entertainment → REST reprend). | - | sans confirmation en mode performance (-p) |
| `hue.quick_scene` | Quickly set up a lighting scene for a group. Args: name: Name for the scene rgb: Optional RGB values [r, g,... | `name` (string), `rgb` (any, opt), `temperature` (any, opt), `brightness` (any, opt), `group_id` (integer, opt) | confirmation [O/n] |
| `hue.refresh_lights` | Refresh the light information cache. This is useful if lights have been added or removed, or if their state... | - | confirmation [O/n] |
| `hue.set_brightness` | Set the brightness of a light. Args: light_id: The ID of the light brightness: Brightness level (0-254)... | `light_id` (integer), `brightness` (integer) | sans confirmation en mode performance (-p) |
| `hue.set_color_preset` | Apply a color preset to a light. Args: light_id: The ID of the light preset: Color preset name (warm, cool,... | `light_id` (integer), `preset` (string) | sans confirmation en mode performance (-p) |
| `hue.set_color_rgb` | Set light color using RGB values. Args: light_id: The ID of the light red: Red value (0-255) green: Green... | `light_id` (integer), `red` (integer), `green` (integer), `blue` (integer) | sans confirmation en mode performance (-p) |
| `hue.set_color_temperature` | Set the color temperature of a light in Kelvin. Color temperature controls the warmth or coolness of white... | `light_id` (integer), `temperature` (integer) | sans confirmation en mode performance (-p) |
| `hue.set_group_brightness` | Set the brightness of all lights in a group. Args: brightness: Brightness level (0-254) group_id: The ID of... | `brightness` (integer), `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.set_group_color_preset` | Apply a color preset to a group. Args: preset: Color preset name (warm, cool, daylight, concentration, relax,... | `preset` (string), `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.set_group_color_rgb` | Set color for all lights in a group using RGB values. Args: red: Red value (0-255) green: Green value (0-255)... | `red` (integer), `green` (integer), `blue` (integer), `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.set_light_effect` | Set a dynamic effect on a light. Args: light_id: The ID of the light effect: Effect type ('none' or... | `light_id` (integer), `effect` (string) | sans confirmation en mode performance (-p) |
| `hue.set_scene` | Apply a scene to a group. Args: scene_id: The ID of the scene group_id: The ID of the group (default: 81 =... | `scene_id` (string), `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.turn_off_group` | Turn off all lights in a specific group. Args: group_id: The ID of the group (default: 81 = Chambre a... | `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.turn_off_light` | Turn off a specific light by ID or by name. Args: light_id: The numeric ID of the light (priority over... | `light_id` (integer, opt), `light_name` (string, opt) | sans confirmation en mode performance (-p) |
| `hue.turn_on_group` | Turn on all lights in a specific group. Args: group_id: The ID of the group (default: 81 = Chambre a coucher)... | `group_id` (integer, opt) | sans confirmation en mode performance (-p) |
| `hue.turn_on_light` | Turn on a specific light by ID or by name. Args: light_id: The numeric ID of the light (priority over... | `light_id` (integer, opt), `light_name` (string, opt) | sans confirmation en mode performance (-p) |

## DENON - Home cinema Denon AVR (denon-mcp) (10 outils)

| Outil | Description | Arguments | Confirmation |
|---|---|---|---|
| `denon.get_status` | Retourne le statut du Denon : volume, power (on/standby/unknown), muted, source (BD, TV, GAME...), reachable. | - | sans confirmation en mode performance (-p) |
| `denon.mute_off` | Desactive le mute du Denon. | - | sans confirmation en mode performance (-p) |
| `denon.mute_on` | Active le mute du Denon. | - | sans confirmation en mode performance (-p) |
| `denon.mute_toggle` | Toggle le mute du Denon (on/off). | - | sans confirmation en mode performance (-p) |
| `denon.power_off` | Eteint le Denon AVR (standby). | - | sans confirmation en mode performance (-p) |
| `denon.power_on` | Allume le Denon AVR. | - | sans confirmation en mode performance (-p) |
| `denon.set_input` | Change la source d'entree du Denon (BD, TV, GAME, SAT/CBL, DVD, MPLAY). | `source` (string) | sans confirmation en mode performance (-p) |
| `denon.volume_down` | Baisse le volume du Denon. | `step` (integer, opt) | sans confirmation en mode performance (-p) |
| `denon.volume_set` | Regle le volume du Denon a un niveau specifique (0-98). 80 = 0dB reference. | `level` (integer) | sans confirmation en mode performance (-p) |
| `denon.volume_up` | Augmente le volume du Denon. | `step` (integer, opt) | sans confirmation en mode performance (-p) |

## CATT - Chromecast et cast navigateur (catt-mcp) (15 outils)

| Outil | Description | Arguments | Confirmation |
|---|---|---|---|
| `catt.cast_browser` | Caste la video de l'onglet actif de Firefox sur la TV (YouTube, Twitch, etc.) | - | sans confirmation en mode performance (-p) |
| `catt.cast_browser_dual` | Lance la video sur PC (Firefox) ET TV simultanement avec synchronisation (pour LightBeat) | - | sans confirmation en mode performance (-p) |
| `catt.cast_dual_offset` | Ajuste le decalage TV (positif=TV en avance, negatif=TV en retard) | `offset` (number) | sans confirmation en mode performance (-p) |
| `catt.cast_dual_resync` | Resynchronise PC et TV en relancant la TV a la position Firefox | - | sans confirmation en mode performance (-p) |
| `catt.cast_dual_stop` | Arrete le dual cast et le watcher de synchronisation | - | sans confirmation en mode performance (-p) |
| `catt.cast_info` | Retourne les infos detaillees du media en cours | - | sans confirmation en mode performance (-p) |
| `catt.cast_pause` | Met en pause le cast en cours | - | sans confirmation en mode performance (-p) |
| `catt.cast_resume` | Reprend la lecture du cast | - | sans confirmation en mode performance (-p) |
| `catt.cast_scan` | Scanne les devices Chromecast/DLNA disponibles sur le reseau | - | sans confirmation en mode performance (-p) |
| `catt.cast_seek` | Avance ou recule dans la video | `seconds` (integer) | sans confirmation en mode performance (-p) |
| `catt.cast_status` | Retourne le statut du cast en cours | - | sans confirmation en mode performance (-p) |
| `catt.cast_stop` | Arrete le cast en cours sur la TV | - | sans confirmation en mode performance (-p) |
| `catt.cast_url` | Caste une URL quelconque (video, audio, stream) sur la TV | `url` (string) | sans confirmation en mode performance (-p) |
| `catt.cast_volume` | Regle le volume du cast (0-100) | `level` (integer) | sans confirmation en mode performance (-p) |
| `catt.cast_youtube` | Caste une video YouTube sur la TV (URL ou ID de video) | `url` (string) | sans confirmation en mode performance (-p) |

## Hors MCP

- `tracking.*` et `ironman.run_scene` sont interceptes par HESTIA avant tout serveur (lyra/hestia/executor.py).
- `mermaid-mcp` (mcp-servers/) n'est pas branche dans config.yaml : ses outils ne sont pas appelables par Lyra.
