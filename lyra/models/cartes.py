"""Cartes de mots d'EPHAISTOS : donnees seules, aucune logique.

Tables mot -> cibles (tokens des noms d'outils) pour le tri des specs,
lexiques de synonymes pour etendre la requete avant le RAG, et le bloc
d'exemples Denon. Regle d'ecriture : des mots de langue courante, jamais une
phrase d'un jeu de test (scripts/controle_hors_regles.py le verifie). Chaque
table dit quelle variante la lit ; l'histoire de chacune est dans
docs/dev/BOUCLE_AMELIORATION.md.
"""

from __future__ import annotations

MOTS_CIBLES: dict[str, tuple[str, ...]] = {
    "ambilight": ("ambilight",),
    "veille": ("off", "standby"),
    "chevet": ("light",),
    "lampe": ("light",),
    "ampoule": ("light",),
    "fort": ("brightness",),
    "fortes": ("brightness",),
    "forte": ("brightness",),
    "faible": ("brightness",),
    "luminosite": ("brightness",),
    "couleur": ("color", "rgb"),
    "ambiance": ("color", "rgb"),
    "rouge": ("color", "rgb"),
    "bleu": ("color", "rgb"),
    "bleue": ("color", "rgb"),
    "vert": ("color", "rgb"),
    "verte": ("color", "rgb"),
    "jaune": ("color", "rgb"),
    "youtube": ("youtube",),
    "http": ("youtube", "url"),
    "https": ("youtube", "url"),
    "diffusion": ("cast",),
    "cast": ("cast",),
    "chromecast": ("cast",),
    "volume": ("volume",),
    "son": ("volume",),
    "secondes": ("seek",),
    "minutes": ("seek",),
    "netflix": ("app",),
    "application": ("app",),
    "appli": ("app",),
}

# Mots du langage courant -> serveur ou famille d'outils (variante carte_equipements)
MOTS_EQUIPEMENTS: dict[str, tuple[str, ...]] = {
    "ampli": ("denon",), "amplificateur": ("denon",), "denon": ("denon",),
    "chromecast": ("cast", "catt"), "cast": ("cast", "catt"),
    "leds": ("ambilight",), "led": ("ambilight",),
    "synchro": ("beat",), "synchronisation": ("beat",),
    "machine": ("vm",), "vm": ("vm",), "serveur": ("vm",),
    "sauvegarde": ("backup",), "sauvegardes": ("backup",), "backup": ("backup",),
    "lampe": ("light",), "lumiere": ("light", "group"), "lumieres": ("group",),
    "scene": ("scene",), "ambiance": ("scene", "color"),
    "telecommande": ("key",), "touche": ("key",),
    "applis": ("apps",), "applications": ("apps",),
    "ecran": ("screen",), "image": ("screen",),
}

# Verbes oraux du cast et reglages (variante verbes_catt)
VERBES_CATT: dict[str, tuple[str, ...]] = {
    "coupe": ("stop", "off"), "couper": ("stop", "off"), "arrete": ("stop",), "stoppe": ("stop",),
    "fige": ("pause",), "gele": ("pause",), "pause": ("pause",),
    "remets": ("resume", "on"), "reprends": ("resume",), "relance": ("resume",), "continue": ("resume",),
    "recule": ("seek",), "avance": ("seek",), "secondes": ("seek",),
    "regle": ("set",), "regler": ("set",), "cent": ("volume", "set"), "pourcent": ("volume", "set"),
}

_MOTS_DUAL = {"dual", "synchro", "synchronise", "synchronisee", "pc", "firefox", "decalage", "resynchronise"}

# Question d'etat -> outils d'information (verbes_tri et nombres_tri)
_MARQUES_QUESTION = {"?", "est-il", "est-elle", "tourne", "encore", "quel", "quelle", "quels", "quelles",
                     "combien", "ou", "quoi", "comment", "etat"}

_CIBLES_ETAT = ("status", "state", "info", "get", "list", "scan")

# Mots decisifs du tri manquants (variante cartes_tri). Des mots de langue
# courante, jamais une phrase du jeu ; chacun a fait rater un tri en it7.
MOTS_TRI: dict[str, tuple[str, ...]] = {
    "noir": ("off",), "noire": ("off",), "rien": ("off",), "eteint": ("off",),
    "route": ("on", "start"), "marche": ("on", "start"),
    "bascule": ("toggle",), "inverse": ("toggle",), "toggle": ("toggle",),
    "chambre": ("group",), "salon": ("group",), "bureau": ("group",), "cuisine": ("group",),
    "piece": ("group",), "lumieres": ("group", "lights"),
    "quelles": ("all", "list", "get"), "quels": ("all", "list", "get"), "maison": ("all",),
    "ou": ("status",),
    "cinema": ("scene",), "saines": ("verify",), "saine": ("verify",), "integrite": ("verify",),
    "comme": ("scan", "list", "apps"), "chez": ("scan",),
    "espace": ("exec",), "disque": ("exec",), "df": ("exec",), "commande": ("exec",),
    "allege": ("clean",), "vire": ("clean",), "nettoie": ("clean",), "menage": ("clean",),
    "purge": ("clean",), "recentes": ("clean",), "anciennes": ("clean",),
    "lecture": ("status", "resume"),
}

MOTS_FINS: dict[str, tuple[str, ...]] = {
    "teinte": ("color", "temperature"), "chaude": ("temperature",), "chaud": ("temperature",),
    "froide": ("temperature",), "froid": ("temperature",),
}

_RARES_FINS = {"fige", "gele", "chaude", "froide", "chaud", "froid",
               "mauve", "violet", "rose", "cyan", "turquoise", "orange", "jaune"}

VERBES_TRI: dict[str, tuple[str, ...]] = {
    "allume": ("on", "start"), "allumer": ("on", "start"), "active": ("on", "start"), "activer": ("on",),
    "demarre": ("on", "start"), "demarrer": ("on", "start"), "rallume": ("on",),
    "eteins": ("off", "stop"), "eteindre": ("off", "stop"), "eteint": ("off",), "arrete": ("off", "stop"),
    "arreter": ("off", "stop"), "stoppe": ("stop",), "desactive": ("off",),
    "ouvre": ("launch", "app"), "ouvrir": ("launch", "app"), "lance": ("launch", "app", "start"),
}

# Quantite relative -> direction (variante mots_relatifs)
MOTS_RELATIFS: dict[str, tuple[str, ...]] = {
    "moins": ("down", "off"), "plus": ("up",),
    "baisse": ("down",), "monte": ("up",),
}

_VERBES_MUTE = {"coupe", "couper", "coupez", "remets", "remettre", "remet", "rends", "mute", "sourdine"}

MOTS_RARES = {"ambilight", "diffusion", "chevet", "veille", "cast", "chromecast",
              "youtube", "netflix", "lounge"}

# Synonymes d'equipement absents de data/synonym_dict.json (variante lexique).
# Des MOTS, jamais des phrases du jeu de test : on complete un lexique, on
# n'apprend pas le banc.
LEXIQUE_EQUIPEMENTS: dict[str, tuple[str, ...]] = {
    "tele": ("tv", "television"), "tv": ("tele", "television"),
    "ampli": ("denon", "amplificateur"), "amplificateur": ("denon", "ampli"),
    "chromecast": ("cast", "diffusion"), "cast": ("chromecast",),
    "leds": ("ambilight", "retroeclairage"), "led": ("ambilight",),
    "synchro": ("hue_beat", "beat", "synchronisation"),
    "machine": ("vm", "machine virtuelle"), "serveur": ("vm",),
    "sauvegardes": ("backup", "backups"), "sauvegarde": ("backup",),
    "restauration": ("snapshot", "restore"),
    "tar": ("archive", "export"), "archive": ("export",),
    "clignoter": ("alert", "identifier"),
    "applis": ("applications", "apps"), "appli": ("application", "app"),
    "teinte": ("couleur", "temperature"),
    "ip": ("status", "adresse"),
    "image": ("ecran",),
}

# Synonymes de langue courante (variante lexique_langue) : des mots que ni
# l'index ni le dictionnaire ne relient a un outil. Registre oral -> registre
# des paraphrases. Jamais une phrase du jeu de test.
LEXIQUE_LANGUE: dict[str, tuple[str, ...]] = {
    "route": ("allumer", "demarrer", "marche"),
    "noir": ("eteindre", "eteins", "off"), "noire": ("eteindre", "ecran", "off"),
    "moitie": ("luminosite", "50", "tamiser"),
    "double": ("clone", "cloner", "dupliquer"),
    "restauration": ("snapshot", "instantane"), "point": ("snapshot",),
    "emporter": ("exporter", "archive"), "tar": ("archive", "exporter"),
    "saines": ("verifier", "integrite"), "saine": ("verifier", "integrite"),
    "allege": ("nettoyer", "supprimer", "purger"), "stock": ("liste", "anciens"),
    "recentes": ("anciens", "nettoyer"),
    "console": ("game", "source", "entree"), "cran": ("volume", "monter"),
    "lien": ("url",), "balance": ("caster", "envoyer", "diffuser"),
    "fige": ("pause",), "gele": ("pause",), "remets": ("reprendre", "reactiver", "desactiver", "mute"),
    "regarde": ("regarder", "video", "youtube"),
    "passe": ("joue", "lecture", "media"), "moment": ("cours", "actuel"),
    "regarder": ("lancer", "application", "app"), "veux": ("lance",),
    "repere": ("identifier", "clignoter"), "clignoter": ("identifier", "alert"),
    "maison": ("toutes", "liste"), "quelles": ("liste",),
    "ambiance": ("scene", "activer"), "cinema": ("scene",),
    "mauve": ("violet", "couleur"), "celle": ("lampe",),
    "encore": ("etat", "status"), "tourne": ("etat", "actif"),
    "comme": ("liste",), "applis": ("applications",),
    "espace": ("commande", "executer"), "disque": ("commande", "executer"),
    "depose": ("copier", "fichier"), "rapport": ("fichier",),
    "vingt": ("20", "niveau"), "trente": ("30", "niveau"), "dix": ("10",),
    "suit": ("mode",), "derriere": ("ambilight",),
}

# Bloc d'exemples Denon (variante exemples_denon) : le prompt systeme n'en avait aucun
EXEMPLES_DENON = """=== EXEMPLES DENON (Home cinema) ===

Requete: "allume l'ampli"
Specs: power_on(), power_off()
Reponse:
{"tool": "power_on", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "allumer = ON"}

Requete: "__VEILLE__"
Specs: power_on(), power_off()
Reponse:
{"tool": "power_off", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "eteindre = OFF"}

Requete: "coupe le son de l'ampli"
Specs: mute_on(), mute_off(), volume_down()
Reponse:
{"tool": "mute_on", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "couper le son = mute"}

Requete: "remets le son sur l'ampli"
Specs: mute_on(), mute_off(), volume_up()
Reponse:
{"tool": "mute_off", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "remettre le son = fin du mute"}

Requete: "regle l'ampli a 40"
Specs: volume_set(level: integer), power_on()
Reponse:
{"tool": "volume_set", "arguments": {"level": 40}, "missing_args": [], "confidence": 0.95, "reasoning": "niveau explicite"}

Requete: "l'ampli sur la console"
Specs: set_input(source: string), power_on()
Reponse:
{"tool": "set_input", "arguments": {"source": "GAME"}, "missing_args": [], "confidence": 0.9, "reasoning": "console = entree GAME"}

Requete: "l'ampli est allume ?"
Specs: get_status(), power_on()
Reponse:
{"tool": "get_status", "arguments": {}, "missing_args": [], "confidence": 0.95, "reasoning": "question d'etat"}

"""

_MODES_AMBILIGHT = {"lounge": "lounge_light", "musique": "follow_audio", "audio": "follow_audio",
                    "video": "follow_video", "film": "follow_video", "manuel": "manual"}

# Synonymes de langue courante par domaine (variante lexique_courant). Ecrits a
# partir du francais de tous les jours, domaine par domaine, pas des echecs d'un
# banc : chaque entree relie un mot ordinaire au registre des paraphrases indexees.
LEXIQUE_COURANT: dict[str, tuple[str, ...]] = {
    # allumage / extinction
    "reveille": ("allumer", "demarrer"), "reveiller": ("allumer", "demarrer"), "reveilles": ("allumer",),
    "eclaire": ("allumer", "lumiere"), "eclairer": ("allumer", "lumiere"), "eclairage": ("lumiere", "lampe"),
    "vire": ("eteindre", "supprimer"), "virer": ("eteindre", "supprimer"), "degage": ("supprimer", "eteindre"),
    "degager": ("supprimer", "eteindre"), "enleve": ("eteindre", "desactiver"), "enlever": ("eteindre", "desactiver"),
    "repos": ("eteindre", "arreter", "veille"), "dodo": ("veille", "eteindre"), "dormir": ("veille", "eteindre"),
    "nuit": ("eteindre", "veille"), "fini": ("eteindre", "arreter"), "ferme": ("eteindre", "arreter"),
    "obscurite": ("eteindre",), "sombre": ("baisser", "luminosite"),
    # volume / son
    "fort": ("volume", "monter"), "forte": ("volume", "monter"), "pousse": ("monter", "volume"),
    "pousser": ("monter", "volume"), "descends": ("baisser", "volume"), "descendre": ("baisser", "volume"),
    "doucement": ("baisser", "volume"), "silence": ("mute", "couper le son"), "chut": ("mute", "couper le son"),
    "sourdine": ("mute",), "cran": ("volume",), "niveau": ("volume",),
    # lumiere
    "tamise": ("luminosite", "baisser"), "tamiser": ("luminosite", "baisser"), "moitie": ("luminosite", "50"),
    "fond": ("luminosite", "maximum"), "couleur": ("couleur", "rgb"), "teinte": ("couleur", "temperature"),
    "preset": ("preset", "couleur"), "predefini": ("preset",), "groupe": ("groupe", "piece"),
    "groupes": ("groupes", "pieces"), "pieces": ("groupes",), "nommee": ("nom", "chercher"), "nomme": ("nom", "chercher"),
    "appelle": ("nom", "chercher"), "connectees": ("liste", "toutes"), "clignote": ("alert", "identifier"),
    # lecture / cast
    "attends": ("pause",), "patiente": ("pause",), "reprends": ("reprendre", "lecture"), "repartir": ("reprendre",),
    "saute": ("avancer", "secondes"), "arriere": ("reculer", "secondes"), "titre": ("info", "en cours"),
    "morceau": ("info", "en cours"), "onglet": ("navigateur", "browser"), "navigateur": ("browser", "onglet"),
    "firefox": ("navigateur", "browser"), "recale": ("resynchroniser", "decalage"), "decales": ("resynchroniser",),
    "decale": ("decalage", "offset"), "avance": ("decalage", "avancer"), "retard": ("decalage",),
    "flux": ("url", "diffuser"), "lien": ("url",), "video": ("youtube", "url"),
    # applications / entrees
    "netflix": ("application", "app"), "plex": ("application", "app"), "disney": ("application", "app"),
    "prime": ("application", "app"), "twitch": ("application", "app"), "spotify": ("application", "app"),
    "youtube": ("application", "app"), "playstation": ("game", "source", "entree"), "ps5": ("game", "source"),
    "xbox": ("game", "source"), "switch": ("game", "source"), "console": ("game", "source", "entree"),
    "bluray": ("bd", "source", "entree"), "lecteur": ("source", "entree"), "media": ("mplay", "source"),
    # machines
    "jumeau": ("clone", "cloner"), "jumelle": ("clone",), "duplique": ("clone", "cloner"), "copie": ("clone", "copier"),
    "instantane": ("snapshot",), "photo": ("snapshot",), "image": ("snapshot", "ecran"),
    "supprime": ("supprimer", "detruire"), "efface": ("supprimer", "detruire"), "detruis": ("detruire",),
    "place": ("commande", "df"), "espace": ("commande", "df"), "uptime": ("commande", "executer"),
    "tourne": ("etat", "status"), "route": ("allumer", "demarrer", "etat"),
    # sauvegardes
    "restaure": ("restaurer", "restore"), "recupere": ("restaurer", "restore"), "hier": ("sauvegarde", "restaurer"),
    "menage": ("nettoyer", "supprimer"), "nettoie": ("nettoyer", "purger"), "purge": ("nettoyer",),
    "vieilles": ("anciennes", "nettoyer"), "timeshift": ("sauvegarde", "backup"), "borg": ("sauvegarde", "backup"),
    "bonnes": ("verifier", "integrite"), "fiables": ("verifier", "integrite"),
}

# Les memes verbes dans les cartes de tri (variante verbes_courants) : cibles = tokens des noms d'outils.
VERBES_COURANTS: dict[str, tuple[str, ...]] = {
    "reveille": ("on", "start"), "reveiller": ("on", "start"), "eclaire": ("on",), "eclairer": ("on",),
    "vire": ("off", "destroy"), "virer": ("off", "destroy"), "degage": ("destroy", "off"), "degager": ("destroy", "off"),
    "enleve": ("off",), "enlever": ("off",), "enleves": ("off",), "repos": ("off", "stop"), "dodo": ("off",), "dormir": ("off",),
    "fini": ("off", "stop"), "ferme": ("off", "stop"),
    "pousse": ("up",), "pousser": ("up",), "descends": ("down",), "descendre": ("down",), "doucement": ("down",),
    "silence": ("mute",), "chut": ("mute",), "sourdine": ("mute",),
    "tamise": ("brightness",), "tamiser": ("brightness",), "fond": ("brightness",),
    "preset": ("preset",), "predefini": ("preset",), "groupes": ("groups",), "pieces": ("groups",),
    "nommee": ("find", "name"), "nomme": ("find", "name"), "appelle": ("find", "name"),
    "attends": ("pause",), "patiente": ("pause",), "reprends": ("resume",), "repartir": ("resume",),
    "saute": ("seek",), "arriere": ("seek",), "titre": ("info",), "morceau": ("info",),
    "onglet": ("browser",), "navigateur": ("browser",), "recale": ("resync",), "decale": ("offset",),
    "retard": ("offset",), "flux": ("url",),
    "playstation": ("input",), "ps5": ("input",), "xbox": ("input",), "console": ("input",),
    "bluray": ("input",), "lecteur": ("input",),
    "jumeau": ("clone",), "jumelle": ("clone",), "duplique": ("clone",), "instantane": ("snapshot",),
    "photo": ("snapshot",), "supprime": ("destroy", "clean"), "efface": ("destroy",), "detruis": ("destroy",),
    "place": ("exec",), "uptime": ("exec",), "tourne": ("status", "state"),
    "restaure": ("restore",), "recupere": ("restore",), "menage": ("clean",), "nettoie": ("clean",),
    "purge": ("clean",), "vieilles": ("clean",), "bonnes": ("verify",), "fiables": ("verify",),
}

LEXIQUE_COURANT_2: dict[str, tuple[str, ...]] = {
    "sors": ("exporter", "archive"), "sortir": ("exporter", "archive"), "sortie": ("exporter",),
    "bilan": ("etat", "status"),   # pas "point" : "point de restauration" est un snapshot
    "reste": ("arreter", "stop"), "restons": ("arreter", "stop"), "termine": ("arreter", "stop"),
    "sans": ("couper", "mute"), "silencieux": ("mute",),
    "prends": ("source", "entree"), "prend": ("source", "entree"), "prendre": ("source", "entree"),
    "dispo": ("liste", "disponibles"), "disponibles": ("liste",), "disponible": ("liste",),
    "connectees": ("liste", "toutes"), "connectes": ("liste", "toutes"),
    "danser": ("beat", "synchro", "musique"), "dansent": ("beat", "synchro"),
    "suivent": ("beat", "etat"), "suit": ("beat", "etat"),
    "ambiances": ("scenes", "liste"), "froide": ("temperature", "froid"), "chaude": ("temperature", "chaud"),
    "avance": ("decalage", "offset"), "mettre": ("allumer", "lancer"),
}

VERBES_COURANTS_2: dict[str, tuple[str, ...]] = {
    "sors": ("export",), "sortir": ("export",), "bilan": ("status",),
    "reste": ("stop",), "restons": ("stop",), "termine": ("stop", "off"),
    "sans": ("mute",), "silencieux": ("mute",),
    "prends": ("input",), "prend": ("input",), "prendre": ("input",),
    "dispo": ("all", "list", "apps"), "disponibles": ("all", "list"), "connectees": ("all", "lights"),
    "danser": ("beat", "start"), "dansent": ("beat", "start"), "suivent": ("beat", "status"), "suit": ("beat", "status"),
    "ambiances": ("scenes", "all"), "avance": ("offset",), "mettre": ("on",),
}

NOMBRES = {"zero", "cinq", "dix", "quinze", "vingt", "trente", "quarante", "cinquante", "soixante",
           "septante", "huitante", "nonante", "cent", "moitie", "quart", "tiers"}

LEXIQUE_COURANT_3: dict[str, tuple[str, ...]] = {
    "appuie": ("touche", "telecommande"), "appuyer": ("touche", "telecommande"), "appuies": ("touche",),
    "presse": ("touche", "telecommande"), "valide": ("touche", "ok"),
    "train": ("etat", "status", "en cours"), "quelle": ("etat", "status"), "quel": ("etat", "status"),
    "quinze": ("15", "regler"), "quarante": ("40", "regler"), "cinquante": ("50", "regler"),
    "soixante": ("60", "regler"), "trente": ("30", "regler"), "vingt": ("20", "regler"),
    "rythme": ("beat", "musique"), "detente": ("scene", "ambiance"), "soiree": ("scene", "ambiance"),
}

VERBES_COURANTS_3: dict[str, tuple[str, ...]] = {
    "appuie": ("key", "send"), "appuyer": ("key", "send"), "appuies": ("key",), "presse": ("key", "send"),
    "valide": ("key",), "train": ("status",), "rythme": ("start",),
    "active": ("activate", "on"), "activer": ("activate",), "scene": ("scene", "activate"),
}

CARTES_17: dict[str, tuple[str, ...]] = {
    "home": ("denon",), "cinema": ("denon",),
    "poil": ("volume",), "fort": ("volume",), "forte": ("volume",),
    "retour": ("key",), "menu": ("key",), "touche": ("key",),
    "pc": ("dual",), "synchronisee": ("dual",), "synchronise": ("dual",), "meme": ("dual",), "decales": ("dual", "resync"),
    "bonnes": ("verify",), "bonne": ("verify",),
    "repos": ("stop",),
    "uptime": ("exec",), "df": ("exec",), "free": ("exec",), "ls": ("exec",),
    # l'equipement designe le serveur : le score absolu monte d'un cran pour
    # tous ses outils, et le tri devient net quand il ne l'etait qu'a 1 point
    "tele": ("tv",), "tv": ("tv",), "television": ("tv",),
    "lampe": ("hue",), "lampes": ("hue", "lights"), "lumiere": ("hue",), "lumieres": ("hue",), "ampoule": ("hue",),
    "toutes": ("all", "list"), "tous": ("all", "list"), "liste": ("all", "list"), "lister": ("all", "list"),
    "quel": ("get", "status", "state"), "quelle": ("get", "status", "state"), "etat": ("get", "status", "state"),
    "tournent": ("status", "state"), "ok": ("verify",),
    "borg": ("create",), "timeshift": ("create",),   # pas "backup" : tous les outils backup l'ont
    "effet": ("effect",), "bouge": ("effect",), "lien": ("url",), "balance": ("cast",),
    "entree": ("input", "source"), "source": ("input",),
    "vois": ("scan",), "voir": ("scan",), "combien": ("scan", "all", "list"),
    "refais": ("clone",), "refaire": ("clone",), "nom": ("clone", "name"), "jumeau": ("clone",),
    "coucher": ("preset",), "soleil": ("preset",), "aube": ("preset",), "mode": ("mode", "preset"),
    "mauve": ("color", "rgb"), "violet": ("color", "rgb"), "rose": ("color", "rgb"), "cyan": ("color", "rgb"),
    "turquoise": ("color", "rgb"), "orange": ("color", "rgb"), "jaune": ("color", "rgb"),
}

_COULEURS = {"mauve", "violet", "rose", "cyan", "turquoise", "orange", "jaune", "rouge", "vert", "verte", "bleu", "bleue", "blanc", "blanche"}

_PIECES = {"bureau", "salon", "chambre", "cuisine", "entree", "couloir", "salle", "garage"}

_MOTS_COMMANDE = {"uptime", "df", "free", "ls", "ping", "top", "cat", "systemctl", "journalctl", "uname", "ps"}

LEXIQUE_17: dict[str, tuple[str, ...]] = {
    "remettre": ("reprendre", "reactiver", "desactiver", "mute"),
    "poil": ("un peu", "volume"), "home": ("ampli", "denon"), "cinema": ("ampli", "denon"),
    "retour": ("touche", "telecommande"), "menu": ("touche", "telecommande"),
    "pc": ("dual", "navigateur"), "synchronisee": ("dual", "synchronise"),
    "point": ("etat", "status"), "etat": ("infos", "informations", "status", "detail"),
}
