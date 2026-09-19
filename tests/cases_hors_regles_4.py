"""Cinquieme jeu, tenu a l'ecart : 50 formulations, 5 serveurs.

Ecrit le 2026-09-19 AVANT l'iteration 16 (questions d'etat, nombres, verbes
de telecommande), le quatrieme jeu (cases_hors_regles_3.py) ayant ete mesure
une fois ; il reste scelle lui aussi tant qu'il ne sert pas a une iteration.
Regle d'usage : une seule mesure par configuration, jamais de boucle dessus.

Noms de machines reels : arch-base, ubuntu-base, fedora-base, test-vm,
windows-11-test. Controle : scripts/controle_hors_regles.py --jeu 4.
"""

TESTS_HORS_REGLES_4 = [
    # ---------------- TV ----------------
    ("TV/power", "matin", "allume-moi la tele, c'est l'heure des infos", "tv.power_on", {}, {}),
    ("TV/power", "dodo", "tele en veille, je vais me coucher", "tv.power_off", {}, {}),
    ("TV/volume", "un peu plus", "un peu plus de son sur la tele", "tv.volume_up", {}, {}),
    ("TV/volume", "trente", "tele a trente", "tv.volume_set", {}, {}),
    ("TV/mute", "sonnette", "on sonne, coupe le son de la tele", "tv.mute", {}, {}),
    ("TV/apps", "twitch", "lance twitch sur la tele", "tv.launch_app", {}, {}),
    ("TV/ambilight", "audio", "l'ambilight qui suit la musique", "tv.ambilight_mode", {}, {}),
    ("TV/screen", "musique", "garde le son de la tele mais eteins l'image", "tv.screen_off", {}, {}),
    ("TV/state", "eteinte ?", "est-ce que la tele est eteinte ?", "tv.get_state", {}, {}),
    ("TV/key", "menu", "appuie sur menu sur la tele", "tv.send_key", {}, {}),
    # ---------------- CATT ----------------
    ("CATT/youtube", "balance", "balance ca sur le chromecast https://youtu.be/QwErTy12345", "catt.cast_youtube", {"url": "https://youtu.be/QwErTy12345"}, {}),
    ("CATT/pause", "stop deux sec", "mets le chromecast en pause deux secondes", "catt.cast_pause", {}, {}),
    ("CATT/resume", "relance", "relance la lecture du chromecast", "catt.cast_resume", {}, {}),
    ("CATT/stop", "eteins", "arrete la diffusion sur le chromecast", "catt.cast_stop", {}, {}),
    ("CATT/volume", "vingt", "le chromecast a vingt pour cent", "catt.cast_volume", {}, {}),
    ("CATT/seek", "dix secondes", "recule de dix secondes sur le chromecast", "catt.cast_seek", {}, {}),
    ("CATT/info", "qu'est-ce qui passe", "qu'est-ce qui passe sur le chromecast", "catt.cast_info", {}, {}),
    ("CATT/status", "en pause ?", "le chromecast est en pause ?", "catt.cast_status", {}, {}),
    ("CATT/scan", "combien", "combien de chromecast tu vois", "catt.cast_scan", {}, {}),
    ("CATT/url", "radio", "mets cette radio sur le chromecast https://example.net/radio.mp3", "catt.cast_url", {"url": "https://example.net/radio.mp3"}, {}),
    # ---------------- HUE ----------------
    ("HUE/light", "entree on", "allume l'entree", "hue.turn_on_light", {}, {}),
    ("HUE/off", "bureau", "eteins les lampes du bureau", "hue.turn_off_group", {}, {}),
    ("HUE/brightness", "salon 70", "le salon a soixante-dix pour cent", "hue.set_group_brightness", {}, {}),
    ("HUE/color", "vert", "mets la chambre en vert", "hue.set_group_color_rgb", {}, {}),
    ("HUE/scene", "soiree", "active la scene soiree", "hue.activate_scene_by_name", {}, {}),
    ("HUE/lights", "liste", "liste-moi toutes les lampes", "hue.get_all_lights", {}, {}),
    ("HUE/group", "etat salon", "dans quel etat sont les lumieres du salon", "hue.get_group", {}, {}),
    ("HUE/temperature", "chaude", "une lumiere plus chaude dans la chambre", "hue.set_color_temperature", {}, {}),
    ("HUE/beat", "musique on", "les lampes en rythme avec la musique", "hue.hue_beat_start", {}, {}),
    ("HUE/beat", "musique off", "arrete la synchro des lampes avec la musique", "hue.hue_beat_stop", {}, {}),
    # ---------------- DENON ----------------
    ("DENON/power", "on", "allume l'ampli", "denon.power_on", {}, {}),
    ("DENON/power", "off", "l'ampli en veille pour ce soir", "denon.power_off", {}, {}),
    ("DENON/input", "tele", "passe l'ampli sur l'entree tele", "denon.set_input", {}, {}),
    ("DENON/input", "lecteur", "l'ampli sur le lecteur", "denon.set_input", {}, {}),
    ("DENON/volume", "monte", "monte l'ampli", "denon.volume_up", {}, {}),
    ("DENON/volume", "descends", "descends un peu l'ampli", "denon.volume_down", {}, {}),
    ("DENON/volume", "cinquante", "l'ampli a cinquante", "denon.volume_set", {}, {}),
    ("DENON/mute", "sourdine", "l'ampli en sourdine", "denon.mute_on", {}, {}),
    ("DENON/mute", "off", "remets le son de l'ampli", "denon.mute_off", {}, {}),
    ("DENON/status", "entree ?", "l'ampli est sur quelle entree", "denon.get_status", {}, {}),
    # ---------------- FEDORA ----------------
    ("FEDORA/vm_start", "windows", "allume windows-11-test", "fedora.vm_start", {"vm_name": "windows-11-test"}, {}),
    ("FEDORA/vm_stop", "fedora-base", "eteins fedora-base", "fedora.vm_stop", {"vm_name": "fedora-base"}, {}),
    ("FEDORA/vm_status", "allumee ?", "est-ce que test-vm est allumee", "fedora.vm_status", {"vm_name": "test-vm"}, {}),
    ("FEDORA/vm_status", "liste", "quelles machines virtuelles tournent", "fedora.vm_status", {}, {}),
    ("FEDORA/vm_clone", "arch", "duplique arch-base en arch-test", "fedora.vm_clone", {"source_vm": "arch-base"}, {}),
    ("FEDORA/vm_exec", "free", "execute free -m sur fedora-base", "fedora.vm_exec", {"vm_name": "fedora-base"}, {}),
    ("FEDORA/vm_snapshot", "avant maj", "snapshot de ubuntu-base avant la mise a jour", "fedora.vm_snapshot", {"vm_name": "ubuntu-base"}, {}),
    ("FEDORA/backup_create", "borg", "lance une sauvegarde borg", "fedora.backup_create", {}, {}),
    ("FEDORA/backup_list", "quoi", "qu'est-ce qu'on a comme sauvegardes", "fedora.backup_list", {}, {}),
    ("FEDORA/backup_verify", "ok ?", "les sauvegardes sont ok ?", "fedora.backup_verify", {}, {}),
]
