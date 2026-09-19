"""Quatrieme jeu, tenu a l'ecart : 50 formulations d'usage quotidien, 5 serveurs.

Ecrit le 2026-09-19 AVANT de construire les leviers generiques (inventaire
reel des machines, lexique de langue courante, verbes courants du tri), pour
mesurer une seule fois ce qu'ils valent sur des phrases jamais vues. Le
troisieme jeu (cases_hors_regles_2.py) sert desormais de jeu de developpement
pour la boucle ; celui-ci ne doit servir a aucune iteration.

Noms de machines reels (virsh list --all) : arch-base, ubuntu-base,
fedora-base, test-vm, windows-11-test. Entrees Denon : BD, TV, GAME, MPLAY.
Dix outils jamais mesures par les trois premiers jeux y figurent
(hue.get_all_groups, hue.get_light, hue.find_light_by_name,
hue.set_group_color_preset, fedora.backup_restore, fedora.backup_clean...).

Meme format et meme controle que cases_hors_regles.py
(scripts/controle_hors_regles.py --jeu 3).
"""

TESTS_HORS_REGLES_3 = [
    # ---------------- TV ----------------
    ("TV/power", "allumer", "la tele, tu me l'allumes ?", "tv.power_on", {}, {}),
    ("TV/power", "tard", "on eteint la tele, il est tard", "tv.power_off", {}, {}),
    ("TV/volume", "entends rien", "monte le son de la tele, j'entends rien", "tv.volume_up", {}, {}),
    ("TV/volume", "quinze", "mets la tele a quinze", "tv.volume_set", {}, {}),
    ("TV/apps", "youtube", "lance youtube sur la tele", "tv.launch_app", {}, {}),
    ("TV/ambilight", "mode video", "l'ambilight, tu le passes en mode video", "tv.ambilight_mode", {}, {}),
    ("TV/screen", "juste ecouter", "coupe l'image de la tele, je veux juste ecouter", "tv.screen_off", {}, {}),
    ("TV/key", "pause", "appuie sur pause sur la tele", "tv.send_key", {}, {}),
    ("TV/state", "allumee ?", "la tele est allumee la ?", "tv.get_state", {}, {}),
    ("TV/ambilight", "vire les leds", "vire les leds de la tele", "tv.ambilight_off", {}, {}),
    # ---------------- CATT ----------------
    ("CATT/youtube", "passe-moi ca", "passe-moi ca sur le chromecast https://youtu.be/xYzAbC12345", "catt.cast_youtube", {"url": "https://youtu.be/xYzAbC12345"}, {}),
    ("CATT/pause", "en pause", "mets la lecture en pause sur le chromecast", "catt.cast_pause", {}, {}),
    ("CATT/resume", "reprends", "reprends la lecture sur le chromecast", "catt.cast_resume", {}, {}),
    ("CATT/stop", "stoppe", "stoppe ce qui passe sur le chromecast", "catt.cast_stop", {}, {}),
    ("CATT/volume", "soixante", "le chromecast a soixante pour cent de volume", "catt.cast_volume", {}, {}),
    ("CATT/seek", "une minute", "saute une minute en avant sur le chromecast", "catt.cast_seek", {}, {}),
    ("CATT/info", "titre en cours", "quel est le titre en cours sur le chromecast", "catt.cast_info", {}, {}),
    ("CATT/status", "en train de lire", "le chromecast est en train de lire ?", "catt.cast_status", {}, {}),
    ("CATT/scan", "reseau", "cherche les chromecast sur le reseau", "catt.cast_scan", {}, {}),
    ("CATT/url", "flux live", "envoie ce flux sur le chromecast https://example.com/live.m3u8", "catt.cast_url", {"url": "https://example.com/live.m3u8"}, {}),
    # ---------------- HUE ----------------
    ("HUE/light", "bureau on", "allume la lampe du bureau", "hue.turn_on_light", {}, {}),
    ("HUE/off", "chambre", "eteins tout dans la chambre", "hue.turn_off_group", {}, {}),
    ("HUE/brightness", "moitie", "la chambre a moitie", "hue.set_group_brightness", {}, {}),
    ("HUE/color", "orange", "passe le salon en orange", "hue.set_group_color_rgb", {}, {}),
    ("HUE/scene", "detente", "lance la scene detente", "hue.activate_scene_by_name", {}, {}),
    ("HUE/groups", "quels groupes", "quels groupes de lampes j'ai", "hue.get_all_groups", {}, {}),
    ("HUE/light", "etat chevet", "c'est quoi l'etat de la lampe de chevet", "hue.get_light", {}, {}),
    ("HUE/find", "nommee couloir", "y a-t-il une lampe nommee couloir", "hue.find_light_by_name", {}, {}),
    ("HUE/preset", "relax", "la chambre en preset relax", "hue.set_group_color_preset", {}, {}),
    ("HUE/alert", "clignoter", "fais clignoter la lampe de l'entree", "hue.alert_light", {}, {}),
    # ---------------- DENON ----------------
    ("DENON/power", "home cinema on", "allume le home cinema", "denon.power_on", {}, {}),
    ("DENON/power", "ampli off", "eteins l'ampli", "denon.power_off", {}, {}),
    ("DENON/input", "tele", "l'ampli sur la tele", "denon.set_input", {}, {}),
    ("DENON/input", "bluray", "bascule l'ampli sur le bluray", "denon.set_input", {}, {}),
    ("DENON/volume", "plus fort", "plus fort sur l'ampli", "denon.volume_up", {}, {}),
    ("DENON/volume", "baisse", "baisse un peu l'ampli", "denon.volume_down", {}, {}),
    ("DENON/volume", "quarante", "l'ampli a quarante", "denon.volume_set", {}, {}),
    ("DENON/mute", "coupe le son", "coupe le son de l'ampli", "denon.mute_on", {}, {}),
    ("DENON/status", "allume ?", "l'ampli est allume ?", "denon.get_status", {}, {}),
    ("DENON/input", "playstation", "l'ampli sur la playstation", "denon.set_input", {}, {}),
    # ---------------- FEDORA ----------------
    ("FEDORA/vm_start", "arch-base", "demarre arch-base", "fedora.vm_start", {"vm_name": "arch-base"}, {}),
    ("FEDORA/vm_stop", "ubuntu-base", "arrete ubuntu-base", "fedora.vm_stop", {"vm_name": "ubuntu-base"}, {}),
    ("FEDORA/vm_status", "en route ?", "fedora-base est en route ?", "fedora.vm_status", {"vm_name": "fedora-base"}, {}),
    ("FEDORA/vm_clone", "fedora-test", "clone fedora-base en fedora-test", "fedora.vm_clone", {"source_vm": "fedora-base"}, {}),
    ("FEDORA/vm_destroy", "plus besoin", "supprime test-vm, j'en ai plus besoin", "fedora.vm_destroy", {"vm_name": "test-vm"}, {}),
    ("FEDORA/vm_exec", "uptime", "lance uptime sur ubuntu-base", "fedora.vm_exec", {"vm_name": "ubuntu-base"}, {}),
    ("FEDORA/vm_snapshot", "windows", "fais une snapshot de windows-11-test", "fedora.vm_snapshot", {"vm_name": "windows-11-test"}, {}),
    ("FEDORA/vm_export", "exporte", "exporte arch-base", "fedora.vm_export", {"vm_name": "arch-base"}, {}),
    ("FEDORA/backup_restore", "hier", "restaure la sauvegarde d'hier", "fedora.backup_restore", {}, {}),
    ("FEDORA/backup_clean", "menage", "fais le menage dans les vieilles sauvegardes", "fedora.backup_clean", {}, {}),
]
