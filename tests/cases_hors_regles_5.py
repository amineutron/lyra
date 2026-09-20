"""Sixieme jeu, tenu a l'ecart : 50 formulations, 5 serveurs.

Ecrit le 2026-09-20 AVANT la boucle "99 % sur chaque jeu" (iterations 17 et
suivantes, qui travaillent sur les jeux 1 a 5). Il reste scelle : une seule
mesure de la configuration finale, jamais d'iteration dessus.

Noms de machines reels : arch-base, ubuntu-base, fedora-base, test-vm,
windows-11-test. Controle : scripts/controle_hors_regles.py --jeu 5.
"""

TESTS_HORS_REGLES_5 = [
    # ---------------- TV ----------------
    ("TV/power", "allume", "tu allumes la tele ?", "tv.power_on", {}, {}),
    ("TV/power", "coupe", "coupe la tele, on sort", "tv.power_off", {}, {}),
    ("TV/volume", "fort", "monte un peu la tele", "tv.volume_up", {}, {}),
    ("TV/volume", "baisse", "baisse la tele, les voisins", "tv.volume_down", {}, {}),
    ("TV/volume", "vingt-cinq", "regle la tele sur vingt-cinq", "tv.volume_set", {}, {}),
    ("TV/apps", "prime", "prime video sur la tele", "tv.launch_app", {}, {}),
    ("TV/ambilight", "off", "eteins les leds de la tele", "tv.ambilight_off", {}, {}),
    ("TV/ambilight", "lounge", "les leds de la tele en ambiance lounge", "tv.ambilight_mode", {}, {}),
    ("TV/state", "en marche ?", "est-ce que la tele est en marche", "tv.get_state", {}, {}),
    ("TV/apps", "quoi", "quelles applis il y a sur la tele", "tv.list_apps", {}, {}),
    # ---------------- CATT ----------------
    ("CATT/youtube", "regarde", "regarde ca sur le chromecast https://youtu.be/ZxCvBn67890", "catt.cast_youtube", {"url": "https://youtu.be/ZxCvBn67890"}, {}),
    ("CATT/pause", "fige", "fige le chromecast", "catt.cast_pause", {}, {}),
    ("CATT/resume", "continue", "continue la lecture sur le chromecast", "catt.cast_resume", {}, {}),
    ("CATT/stop", "termine", "termine la diffusion du chromecast", "catt.cast_stop", {}, {}),
    ("CATT/volume", "a fond", "le chromecast a fond", "catt.cast_volume", {}, {}),
    ("CATT/seek", "cinq minutes", "avance de cinq minutes sur le chromecast", "catt.cast_seek", {}, {}),
    ("CATT/info", "titre", "quel titre passe sur le chromecast", "catt.cast_info", {}, {}),
    ("CATT/status", "tourne ?", "le chromecast tourne toujours ?", "catt.cast_status", {}, {}),
    ("CATT/scan", "trouve", "trouve les chromecast de la maison", "catt.cast_scan", {}, {}),
    ("CATT/browser", "onglet", "cast l'onglet courant sur la tele", "catt.cast_browser", {}, {}),
    # ---------------- HUE ----------------
    ("HUE/light", "couloir on", "allume le couloir", "hue.turn_on_light", {}, {}),
    ("HUE/light", "chevet off", "eteins la lampe de chevet", "hue.turn_off_light", {}, {}),
    ("HUE/brightness", "bureau 40", "le bureau a quarante pour cent", "hue.set_group_brightness", {}, {}),
    ("HUE/color", "violet", "le salon en violet", "hue.set_group_color_rgb", {}, {}),
    ("HUE/scene", "cinema", "mets l'ambiance cinema", "hue.activate_scene_by_name", {}, {}),
    ("HUE/scenes", "liste", "quelles scenes j'ai", "hue.get_all_scenes", {}, {}),
    ("HUE/groups", "pieces", "quelles pieces sont configurees dans hue", "hue.get_all_groups", {}, {}),
    ("HUE/temperature", "froid", "lumiere plus froide dans le bureau", "hue.set_color_temperature", {}, {}),
    ("HUE/alert", "signale", "fais clignoter la lampe du salon", "hue.alert_light", {}, {}),
    ("HUE/beat", "status", "la synchro musicale des lampes tourne ?", "hue.hue_beat_status", {}, {}),
    # ---------------- DENON ----------------
    ("DENON/power", "on", "reveille l'ampli", "denon.power_on", {}, {}),
    ("DENON/power", "off", "coupe l'ampli", "denon.power_off", {}, {}),
    ("DENON/input", "game", "l'ampli sur game", "denon.set_input", {}, {}),
    ("DENON/input", "bd", "l'ampli sur le bluray", "denon.set_input", {}, {}),
    ("DENON/volume", "plus", "l'ampli un peu plus fort", "denon.volume_up", {}, {}),
    ("DENON/volume", "moins", "l'ampli moins fort", "denon.volume_down", {}, {}),
    ("DENON/volume", "45", "l'ampli a 45", "denon.volume_set", {}, {}),
    ("DENON/mute", "chut", "chut, l'ampli", "denon.mute_on", {}, {}),
    ("DENON/mute", "remets", "remets le son sur l'ampli", "denon.mute_off", {}, {}),
    ("DENON/status", "volume ?", "l'ampli est a combien", "denon.get_status", {}, {}),
    # ---------------- FEDORA ----------------
    ("FEDORA/vm_start", "ubuntu", "lance ubuntu-base", "fedora.vm_start", {"vm_name": "ubuntu-base"}, {}),
    ("FEDORA/vm_stop", "test-vm", "coupe test-vm", "fedora.vm_stop", {"vm_name": "test-vm"}, {}),
    ("FEDORA/vm_status", "arch", "arch-base tourne ?", "fedora.vm_status", {"vm_name": "arch-base"}, {}),
    ("FEDORA/vm_destroy", "windows", "supprime windows-11-test pour de bon", "fedora.vm_destroy", {"vm_name": "windows-11-test"}, {}),
    ("FEDORA/vm_clone", "copie", "fais une copie de fedora-base nommee fedora-lab", "fedora.vm_clone", {"source_vm": "fedora-base"}, {}),
    ("FEDORA/vm_exec", "ls", "lance ls /tmp sur arch-base", "fedora.vm_exec", {"vm_name": "arch-base"}, {}),
    ("FEDORA/vm_export", "archive", "archive test-vm", "fedora.vm_export", {"vm_name": "test-vm"}, {}),
    ("FEDORA/backup_create", "maintenant", "fais une sauvegarde maintenant", "fedora.backup_create", {}, {}),
    ("FEDORA/backup_status", "ou en est", "ou en est la sauvegarde", "fedora.backup_status", {}, {}),
    ("FEDORA/backup_clean", "vieux", "supprime les vieux backups", "fedora.backup_clean", {}, {}),
]
