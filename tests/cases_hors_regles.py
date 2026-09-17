"""Jeu « hors regles » : 50 formulations inedites, 5 serveurs, tenues a l'ecart.

Aucune de ces phrases ne doit apparaitre dans les regles (`lyra/rules/`) ni
dans les paraphrases indexees (`triggers_map`) : elles mesurent ce que le
modele generalise, pas ce que le banc a memorise. Un script de controle
(`scripts/controle_hors_regles.py`) verifie les deux proprietes.

Format identique a TESTS_LLM : (categorie, description, requete, outil attendu,
args obligatoires, args optionnels). Les args restent minimaux : on mesure
d'abord le choix de l'outil.
"""

TESTS_HORS_REGLES = [
    # ---------------- TV (pylips-mcp) ----------------
    ("TV/power", "en route", "la tele, mets-la en route", "tv.power_on", {}, {}),
    ("TV/screen", "ecran off son actif", "la tele, image noire mais garde le son", "tv.screen_off", {}, {}),
    ("TV/screen", "ecran on", "rends-moi l'image sur la tele", "tv.screen_on", {}, {}),
    ("TV/state", "etat", "la tele est allumee la ?", "tv.get_state", {}, {}),
    ("TV/apps", "liste", "qu'est-ce qu'il y a comme applis sur la tele", "tv.list_apps", {}, {}),
    ("TV/apps", "ouvrir appli", "je veux regarder disney plus", "tv.launch_app", {}, {}),
    ("TV/volume", "niveau", "le son de la tele a vingt", "tv.volume_set", {}, {}),
    ("TV/volume", "moins fort", "un peu moins fort la tele", "tv.volume_down", {}, {}),
    ("TV/key", "touche", "appuie sur ok sur la telecommande de la tele", "tv.send_key", {}, {}),
    ("TV/ambilight", "mode musique", "les leds derriere la tele, en mode qui suit la musique", "tv.ambilight_mode", {}, {}),
    # ---------------- CATT (catt-mcp) ----------------
    ("CATT/youtube", "envoie sur chromecast", "regarde-moi ca sur le chromecast https://youtu.be/dQw4w9WgXcQ", "catt.cast_youtube", {"url": "https://youtu.be/dQw4w9WgXcQ"}, {}),
    ("CATT/url", "lien quelconque", "balance ce lien sur la tele https://example.org/film.mp4", "catt.cast_url", {"url": "https://example.org/film.mp4"}, {}),
    ("CATT/pause", "pause", "fige la lecture du chromecast", "catt.cast_pause", {}, {}),
    ("CATT/resume", "reprise", "c'est bon, remets la video sur le chromecast", "catt.cast_resume", {}, {}),
    ("CATT/seek", "reculer", "recule de dix secondes sur le chromecast", "catt.cast_seek", {}, {}),
    ("CATT/status", "ou en est", "ou en est la lecture sur le chromecast", "catt.cast_status", {}, {}),
    ("CATT/info", "quoi en cours", "qu'est-ce qui passe sur le chromecast en ce moment", "catt.cast_info", {}, {}),
    ("CATT/scan", "scan", "y a quoi comme chromecast chez moi", "catt.cast_scan", {}, {}),
    ("CATT/stop", "couper lecture", "le chromecast, coupe la lecture", "catt.cast_stop", {}, {}),
    ("CATT/volume", "niveau", "le chromecast a trente pour cent", "catt.cast_volume", {}, {}),
    # ---------------- HUE (hue-mcp) ----------------
    ("HUE/alert", "reperer", "fais clignoter la lampe du salon pour que je la repere", "hue.alert_light", {}, {}),
    ("HUE/list", "inventaire", "quelles lumieres j'ai a la maison", "hue.get_all_lights", {}, {}),
    ("HUE/temperature", "teinte chaude", "mets une teinte chaude dans le salon", "hue.set_color_temperature", {}, {}),
    ("HUE/scene", "scene", "ambiance cinema dans le salon", "hue.activate_scene_by_name", {}, {}),
    ("HUE/brightness", "tamiser", "tamise la chambre de moitie", "hue.set_group_brightness", {}, {}),
    ("HUE/color", "violet", "la lampe du bureau en mauve, juste celle-la", "hue.set_color_rgb", {}, {}),
    ("HUE/off", "tout eteindre piece", "plus rien dans la chambre, tout en noir", "hue.turn_off_group", {}, {}),
    ("HUE/beat", "synchro musique", "lance la synchro des lumieres sur la musique", "hue.hue_beat_start", {}, {}),
    ("HUE/beat", "arret synchro", "stoppe la synchro lumiere", "hue.hue_beat_stop", {}, {}),
    ("HUE/beat", "etat synchro", "la synchro lumiere tourne encore ?", "hue.hue_beat_status", {}, {}),
    # ---------------- DENON (denon-mcp) ----------------
    ("DENON/power", "en route", "mets l'ampli en route", "denon.power_on", {}, {}),
    ("DENON/power", "veille", "l'ampli en veille", "denon.power_off", {}, {}),
    ("DENON/mute", "couper son", "coupe le son de l'ampli", "denon.mute_on", {}, {}),
    ("DENON/mute", "remettre son", "remets le son sur l'ampli", "denon.mute_off", {}, {}),
    ("DENON/mute", "bascule", "bascule le mute de l'ampli", "denon.mute_toggle", {}, {}),
    ("DENON/input", "console", "l'ampli sur l'entree de la console", "denon.set_input", {}, {}),
    ("DENON/input", "tele", "bascule l'entree de l'ampli vers la tele", "denon.set_input", {}, {}),
    ("DENON/volume", "un cran", "l'ampli, un cran plus fort", "denon.volume_up", {}, {}),
    ("DENON/volume", "niveau", "regle l'ampli a 40", "denon.volume_set", {}, {}),
    ("DENON/status", "etat", "l'ampli est allume ?", "denon.get_status", {}, {}),
    # ---------------- FEDORA (fedora-agents) ----------------
    ("FEDORA/vm_start", "en route", "mets en route la machine preprod-01", "fedora.vm_start", {"vm_name": "preprod-01"}, {}),
    ("FEDORA/vm_stop", "couper", "coupe sandbox-02", "fedora.vm_stop", {"vm_name": "sandbox-02"}, {}),
    ("FEDORA/vm_status", "ip", "c'est quoi l'ip de preprod-01", "fedora.vm_status", {"vm_name": "preprod-01"}, {}),
    ("FEDORA/vm_clone", "copie nommee", "je veux un double de preprod-01, nomme preprod-02", "fedora.vm_clone", {"source_vm": "preprod-01"}, {}),
    ("FEDORA/vm_exec", "commande", "regarde l'espace disque dans sandbox-02 avec df -h", "fedora.vm_exec", {"vm_name": "sandbox-02"}, {}),
    ("FEDORA/vm_copy", "envoyer fichier", "depose le fichier rapport.txt sur preprod-01", "fedora.vm_copy", {}, {}),
    ("FEDORA/vm_snapshot", "point de restauration", "fais-moi un point de restauration de preprod-01", "fedora.vm_snapshot", {"vm_name": "preprod-01"}, {}),
    ("FEDORA/vm_export", "archive", "fais-moi un tar de preprod-01 pour l'emporter", "fedora.vm_export", {"vm_name": "preprod-01"}, {}),
    ("FEDORA/backup_status", "etat", "ou en sont les sauvegardes", "fedora.backup_status", {}, {}),
    ("FEDORA/backup_verify", "integrite", "les sauvegardes sont saines ?", "fedora.backup_verify", {}, {}),
    ("FEDORA/backup_clean", "menage", "vire les anciennes sauvegardes", "fedora.backup_clean", {}, {}),
]
