"""Troisieme jeu, tenu a l'ecart : 100 formulations nouvelles, 5 serveurs.

Ecrit le 2026-09-19 APRES la boucle d'amelioration, pour mesurer ce que vaut
la configuration finale sur des phrases qu'elle n'a jamais vues. Regle
d'usage : une seule mesure par configuration, jamais de boucle dessus --
sinon il perd sa valeur comme le jeu precedent (onze iterations).

Meme format et meme controle que cases_hors_regles.py
(scripts/controle_hors_regles.py --jeu 2).
"""

TESTS_HORS_REGLES_2 = [
    # ---------------- TV ----------------
    ("TV/power", "en marche", "tu peux me mettre la tele ?", "tv.power_on", {}, {}),
    ("TV/state", "en veille ?", "la tele, elle dort ou quoi ?", "tv.get_state", {}, {}),
    ("TV/volume", "pousser le son", "pousse un peu le son de la tele", "tv.volume_up", {}, {}),
    ("TV/mute", "couper deux secondes", "la tele, sans le son deux secondes", "tv.mute", {}, {}),
    ("TV/apps", "netflix", "mets-moi netflix", "tv.launch_app", {}, {}),
    ("TV/ambilight", "leds off", "les leds de la tele, tu me les enleves", "tv.ambilight_off", {}, {}),
    ("TV/screen", "ecran noir son on", "ecran de la tele en noir, mais je garde le son", "tv.screen_off", {}, {}),
    ("TV/key", "retour", "fais retour sur la tele", "tv.send_key", {}, {}),
    ("TV/apps", "dispo", "c'est quoi les applis dispo sur la tele", "tv.list_apps", {}, {}),
    ("TV/volume", "a dix", "le son de la tele a dix", "tv.volume_set", {}, {}),
    # ---------------- CATT ----------------
    ("CATT/youtube", "mets ca", "ca, sur le chromecast https://youtu.be/aAbBcCdDeE0", "catt.cast_youtube", {"url": "https://youtu.be/aAbBcCdDeE0"}, {}),
    ("CATT/pause", "attends", "attends deux secondes, le chromecast", "catt.cast_pause", {}, {}),
    ("CATT/resume", "reprendre", "c'est bon, ca peut repartir sur le chromecast", "catt.cast_resume", {}, {}),
    ("CATT/stop", "ce qui passe", "le chromecast, on en reste la", "catt.cast_stop", {}, {}),
    ("CATT/volume", "moins fort", "le chromecast, un peu moins fort", "catt.cast_volume", {}, {}),
    ("CATT/seek", "deux minutes", "avance de deux minutes sur le chromecast", "catt.cast_seek", {}, {}),
    ("CATT/status", "ca en est ou", "ca en est ou sur le chromecast", "catt.cast_status", {}, {}),
    ("CATT/info", "on regarde quoi", "qu'est-ce qu'on regarde la sur le chromecast", "catt.cast_info", {}, {}),
    ("CATT/scan", "lesquels", "il y a quels chromecast ici", "catt.cast_scan", {}, {}),
    ("CATT/url", "flux", "ce flux, sur le chromecast https://example.org/stream.m3u8", "catt.cast_url", {"url": "https://example.org/stream.m3u8"}, {}),
    # ---------------- HUE ----------------
    ("HUE/on", "salon", "de la lumiere dans le salon s'il te plait", "hue.turn_on_group", {}, {}),
    ("HUE/off", "salon", "plus de lumiere au salon", "hue.turn_off_group", {}, {}),
    ("HUE/brightness", "moins", "un peu moins de lumiere dans le salon", "hue.set_group_brightness", {}, {}),
    ("HUE/preset", "coucher de soleil", "la lampe de l'entree en mode coucher de soleil", "hue.set_color_preset", {}, {}),
    ("HUE/color", "chambre bleue", "du bleu dans la chambre", "hue.set_group_color_rgb", {}, {}),
    ("HUE/scene", "lecture", "mets-moi l'ambiance lecture", "hue.activate_scene_by_name", {}, {}),
    ("HUE/scenes", "lesquelles", "j'ai quoi comme ambiances de dispo", "hue.get_all_scenes", {}, {}),
    ("HUE/alert", "signe", "fais-moi un signe avec la lampe du couloir", "hue.alert_light", {}, {}),
    ("HUE/temperature", "plus froid", "une lumiere plus froide au bureau", "hue.set_color_temperature", {}, {}),
    ("HUE/beat", "danser", "fais danser les lumieres avec la musique", "hue.hue_beat_start", {}, {}),
    # ---------------- DENON ----------------
    ("DENON/power", "home cinema", "reveille le home cinema", "denon.power_on", {}, {}),
    ("DENON/power", "au revoir", "l'ampli, c'est fini pour ce soir", "denon.power_off", {}, {}),
    ("DENON/mute", "mute", "mute l'ampli", "denon.mute_on", {}, {}),
    ("DENON/mute", "enlever", "enleve le mute de l'ampli", "denon.mute_off", {}, {}),
    ("DENON/volume", "monter", "monte un peu l'ampli", "denon.volume_up", {}, {}),
    ("DENON/volume", "un poil", "l'ampli, un poil moins", "denon.volume_down", {}, {}),
    ("DENON/volume", "trente-cinq", "l'ampli a trente-cinq", "denon.volume_set", {}, {}),
    ("DENON/input", "bluray", "l'ampli sur le lecteur bluray", "denon.set_input", {}, {}),
    ("DENON/status", "il en est ou", "l'ampli, il en est ou", "denon.get_status", {}, {}),
    ("DENON/mute", "sourdine", "inverse la sourdine de l'ampli", "denon.mute_toggle", {}, {}),
    # ---------------- FEDORA ----------------
    ("FEDORA/vm_start", "staging", "il me faut staging-03 en route", "fedora.vm_start", {"vm_name": "staging-03"}, {}),
    ("FEDORA/vm_stop", "au repos", "mets staging-03 au repos", "fedora.vm_stop", {"vm_name": "staging-03"}, {}),
    ("FEDORA/vm_status", "etat", "staging-03, elle va bien ?", "fedora.vm_status", {"vm_name": "staging-03"}, {}),
    ("FEDORA/vm_clone", "copie", "refais-moi staging-03 sous le nom staging-04", "fedora.vm_clone", {"source_vm": "staging-03"}, {}),
    ("FEDORA/vm_snapshot", "instantane", "garde-moi une image de staging-03 avant que je touche", "fedora.vm_snapshot", {"vm_name": "staging-03"}, {}),
    ("FEDORA/vm_exec", "uptime", "regarde depuis combien de temps staging-03 tourne, avec uptime", "fedora.vm_exec", {"vm_name": "staging-03"}, {}),
    ("FEDORA/vm_export", "archive", "sors staging-03 dans une archive", "fedora.vm_export", {"vm_name": "staging-03"}, {}),
    ("FEDORA/backup_list", "montrer", "on a quoi comme sauvegardes", "fedora.backup_list", {}, {}),
    ("FEDORA/backup_verify", "controle", "les sauvegardes, elles sont bonnes ?", "fedora.backup_verify", {}, {}),
    ("FEDORA/backup_status", "le point", "le point sur les sauvegardes", "fedora.backup_status", {}, {}),
    # ============ 50 de plus : formulations d'usage quotidien, noms reels ============
    # ---------------- TV ----------------
    ("TV/apps", "plex", "mets plex sur la tele", "tv.launch_app", {}, {}),
    ("TV/apps", "disney", "on se fait un disney, mets-le sur la tele", "tv.launch_app", {}, {}),
    ("TV/ambilight", "lounge", "l'ambilight en mode lounge pour ce soir", "tv.ambilight_mode", {}, {}),
    ("TV/volume", "trop fort", "la tele est trop forte, descends un peu", "tv.volume_down", {}, {}),
    ("TV/mute", "telephone", "je suis au telephone, coupe le son de la tele", "tv.mute", {}, {}),
    ("TV/screen", "rallume", "rallume-moi l'image de la tele", "tv.screen_on", {}, {}),
    ("TV/youtube", "cette video", "mets cette video sur la tele https://www.youtube.com/watch?v=jNQXAC9IVRw", "tv.youtube_video", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}, {}),
    ("TV/key", "ok", "valide avec ok sur la tele", "tv.send_key", {}, {}),
    ("TV/power", "c'est bon", "c'est bon pour la tele ce soir, tu peux la mettre en veille", "tv.power_off", {}, {}),
    ("TV/ambilight", "leds on", "remets les leds derriere la tele", "tv.ambilight_on", {}, {}),
    # ---------------- CATT ----------------
    ("CATT/browser", "firefox", "envoie l'onglet firefox sur la tele", "catt.cast_browser", {}, {}),
    ("CATT/dual", "lightbeat", "lance la video sur le pc et la tele en meme temps pour lightbeat", "catt.cast_browser_dual", {}, {}),
    ("CATT/dual", "stop", "coupe la lecture synchronisee entre le pc et la tele", "catt.cast_dual_stop", {}, {}),
    ("CATT/dual", "resync", "la tele et le pc sont decales, recale-les", "catt.cast_dual_resync", {}, {}),
    ("CATT/dual", "offset", "la tele est en avance d'une seconde sur le pc", "catt.cast_dual_offset", {}, {}),
    ("CATT/seek", "arriere", "reviens trente secondes en arriere sur le chromecast", "catt.cast_seek", {}, {}),
    ("CATT/volume", "moitie", "le chromecast a la moitie du volume", "catt.cast_volume", {}, {}),
    ("CATT/info", "titre", "c'est quoi le titre de ce qui passe sur le chromecast", "catt.cast_info", {}, {}),
    ("CATT/stop", "on arrete", "on arrete le chromecast, je vais dormir", "catt.cast_stop", {}, {}),
    ("CATT/status", "encore", "le chromecast diffuse encore ?", "catt.cast_status", {}, {}),
    # ---------------- HUE ----------------
    ("HUE/light", "chevet on", "la lampe de chevet, s'il te plait", "hue.turn_on_light", {}, {}),
    ("HUE/light", "chevet off", "tu peux couper la lampe de chevet", "hue.turn_off_light", {}, {}),
    ("HUE/brightness", "a fond", "la lampe du bureau a fond", "hue.set_brightness", {}, {}),
    ("HUE/brightness", "chambre 20", "la chambre a 20 pour cent", "hue.set_group_brightness", {}, {}),
    ("HUE/effect", "effet", "mets un effet qui bouge sur la lampe du salon", "hue.set_light_effect", {}, {}),
    ("HUE/beat", "palette ironman", "la synchro musicale en palette iron man", "hue.hue_beat_set", {}, {}),
    ("HUE/beat", "stop", "stoppe les lumieres qui suivent la musique", "hue.hue_beat_stop", {}, {}),
    ("HUE/beat", "status", "les lumieres suivent toujours la musique ?", "hue.hue_beat_status", {}, {}),
    ("HUE/list", "combien", "j'ai combien de lampes connectees", "hue.get_all_lights", {}, {}),
    ("HUE/color", "rouge chambre", "chambre en rouge, ambiance", "hue.set_group_color_rgb", {}, {}),
    # ---------------- DENON ----------------
    ("DENON/power", "denon marche", "mets le denon en marche", "denon.power_on", {}, {}),
    ("DENON/input", "game", "l'ampli sur la console de jeu", "denon.set_input", {}, {}),
    ("DENON/input", "tv arc", "l'ampli, prends le son de la tele", "denon.set_input", {}, {}),
    ("DENON/input", "mplay", "l'ampli sur le lecteur media", "denon.set_input", {}, {}),
    ("DENON/volume", "60", "l'ampli a soixante", "denon.volume_set", {}, {}),
    ("DENON/volume", "un cran", "l'ampli, un cran de plus", "denon.volume_up", {}, {}),
    ("DENON/mute", "silence", "silence sur l'ampli", "denon.mute_on", {}, {}),
    ("DENON/mute", "remets", "tu peux remettre le son de l'ampli", "denon.mute_off", {}, {}),
    ("DENON/status", "volume ?", "il est a combien l'ampli", "denon.get_status", {}, {}),
    ("DENON/power", "denon veille", "le denon en veille, merci", "denon.power_off", {}, {}),
    # ---------------- FEDORA ----------------
    ("FEDORA/vm_start", "fedora-base", "reveille fedora-base", "fedora.vm_start", {"vm_name": "fedora-base"}, {}),
    ("FEDORA/vm_stop", "arch-base", "arch-base, tu peux la couper", "fedora.vm_stop", {"vm_name": "arch-base"}, {}),
    ("FEDORA/vm_status", "test-vm", "test-vm tourne encore ?", "fedora.vm_status", {"vm_name": "test-vm"}, {}),
    ("FEDORA/vm_clone", "ubuntu", "un jumeau d'ubuntu-base qui s'appelle ubuntu-test", "fedora.vm_clone", {"source_vm": "ubuntu-base"}, {}),
    ("FEDORA/vm_destroy", "test-vm", "test-vm, tu peux la degager completement", "fedora.vm_destroy", {"vm_name": "test-vm"}, {}),
    ("FEDORA/vm_exec", "df", "regarde la place qu'il reste sur fedora-base avec df -h", "fedora.vm_exec", {"vm_name": "fedora-base"}, {}),
    ("FEDORA/backup_create", "timeshift", "un timeshift maintenant", "fedora.backup_create", {}, {}),
    ("FEDORA/vm_verify", "copie fidele", "verifie que ubuntu-test est bien une copie fidele", "fedora.vm_verify", {}, {}),
    ("FEDORA/vm_import", "archive", "recharge fedora-base depuis son archive", "fedora.vm_import", {}, {}),
    ("FEDORA/backup_clean", "menage", "un peu de menage dans les vieux backups", "fedora.backup_clean", {}, {}),
]
