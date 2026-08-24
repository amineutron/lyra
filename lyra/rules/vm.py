"""Regles de detection pour les outils VM (fedora.vm_*)."""

import re
from typing import Optional

from .base import normalize, make

_VM_NAME_RE = r'([\w][\w.-]*(?:-\d+)?)'

_VM_GENERIC = {'la', 'le', 'les', 'un', 'une', 'de', 'du', 'des', 'vm', 'machine',
               'serveur', 'mon', 'ma', 'mes', 'cette', 'ce', 'sa', 'son', 'ses',
               'tout', 'tous', 'toutes'}

_VM_NOISE = {
    # Articles / determinants
    'la', 'le', 'les', 'un', 'une', 'des', 'du', 'de', 'l',
    # Pronoms possessifs
    'mon', 'ma', 'mes', 'ton', 'ta', 'tes', 'son', 'sa', 'ses',
    'ce', 'cette', 'ces',
    # Prepositions
    'sur', 'pour', 'dans', 'avec', 'sans', 'vers', 'depuis', 'par',
    'a', 'au', 'aux', 'en', 'entre', 'sous',
    # Conjonctions / auxiliaires
    'et', 'ou', 'mais', 'donc', 'ni', 'car', 'est', 'etes', 'sont',
    # Verbes d'action courants
    'fais', 'faire', 'lance', 'lancer', 'demarre', 'demarrer',
    'arrete', 'arreter', 'stoppe', 'stopper', 'stop', 'start',
    'verifie', 'verifier', 'verif', 'check', 'vm', 'verify',
    'clone', 'cloner', 'exporte', 'exporter', 'importe', 'importer',
    'supprime', 'supprimer', 'detruit', 'detruire', 'efface', 'effacer',
    'execute', 'executer', 'exec', 'cree', 'creer',
    'affiche', 'afficher', 'montre', 'montrer', 'liste', 'lister',
    'copie', 'copier', 'snapshot', 'instantane', 'capture',
    # Mots VM generiques
    'machine', 'machines', 'serveur', 'serveurs', 'hote', 'host',
    'virtuelle', 'virtuelles',
    # Remplissage / politesse
    'rapidement', 'vite', 'maintenant', 'stp', 'please', 'merci',
    'ok', 'peux', 'peut', 'tu', 'moi', 'je', 'il', 'elle',
    'nous', 'veux', 'voudrais', 'voudrait',
}


def _extract_vm_name(phrase: str) -> Optional[str]:
    """Extrait un nom de VM depuis une phrase libre.

    Independant de la structure syntaxique : fonctionne quelle que soit
    la position du nom dans la phrase ou la preposition utilisee.
    Cherche le premier token hostname-like (contient '-' ou >= 6 chars)
    qui n'est pas un mot de bruit.
    """
    tokens = re.findall(r'[a-z][a-z0-9._-]*', phrase)
    for token in tokens:
        if token in _VM_NOISE or len(token) < 3:
            continue
        # Nom de VM typique : contient un tiret (preprod-01) ou est long
        if '-' in token or len(token) >= 6:
            # Exclure les expressions francaises hyphenees (est-ce, peut-etre, etc.)
            prefix = token.split('-')[0]
            if prefix in _VM_NOISE:
                continue
            return token
    return None


def detect(query: str):
    q = normalize(query)

    # vm_clone_system: la source est TOUJOURS le PC hote
    # Doit venir AVANT vm_clone (qui exclut "system").
    # Gate double : mot "systeme" ISOLE (pas "system-clone-final" — les
    # lookarounds excluent le tiret) ET un verbe de clonage (sinon
    # "exporte system-clone-final" devenait un clone systeme).
    if re.search(r'(?<![\w-])(?:syst[eè]?me?|system)(?![\w-])', q) \
            and re.search(r'\b(?:clone[rz]?|duplique[rz]?|copie[rz]?)\b', q):
        # La SOURCE d'un clone systeme est TOUJOURS le PC hote : seul le nom
        # de la nouvelle VM compte (arg MCP: name). Formes acceptees :
        # Marqueur explicite d'abord ("en X" / "nomme X" / "appele X"), meme
        # loin du mot "systeme" : "clone systeme preprod-01 en Y" -> Y est le
        # nom voulu (l'ancienne phrase avec source, la source reste l'hote).
        m = re.search(
            r'(?:syst[eè]?me?|system)\b.*?\b(?:en|nomm[ée]e?|appel[ée]e?)\s+([\w][\w.-]*)',
            q
        )
        if not m:
            # "clone systeme X" : le mot qui suit directement est le nom
            m = re.search(
                r'(?:clone[rz]?|duplique[rz]?)\s+(?:le\s+|la\s+|un\s+)?'
                r'(?:syst[eè]?me?|system)\s+([\w][\w.-]*)',
                q
            )
        if m and m.group(1) not in _VM_GENERIC:
            return make("fedora.vm_clone_system", {"name": m.group(1)},
                        "rule: clone systeme (hote) -> name", 0.95)
        # "fait un clone systeme" sans nom -> interactif
        if re.search(r'\b(?:clone[rz]?|duplique[rz]?|copie[rz]?)\b', q):
            return make("fedora.vm_clone_system", {},
                        "rule: clone systeme (interactif, nom manquant)",
                        0.85, missing_args=["name"])

    # "cree une vm" : pas d'outil vm_create — la creation passe par le clone
    # d'un template. On route vers vm_clone en mode interactif (args manquants)
    # plutot que de laisser le RAG proposer un outil "MCP" illisible.
    if re.search(r"\bcre[ea][rz]?\b.{0,20}\b(?:vms?|machines?(?:\s+virtuelles?)?)\b", q) \
            and not re.search(r"\b(?:snapshot|backup|sauvegarde|copie)\b", q):
        return make("fedora.vm_clone", {},
                    "rule: creer une vm -> clone d'un template (interactif)",
                    0.85, missing_args=["source_vm", "new_vm_name"])

    # vm_clone: "clone/duplique SOURCE en DEST"
    if 'system' not in q and 'systeme' not in q:
        m = re.search(
            r'(?:clone[rz]?|duplique[rz]?)\s+([\w][\w.-]*)\s+en\s+([\w][\w.-]*)',
            q
        )
        if m:
            args = {"source_vm": m.group(1), "new_vm_name": m.group(2)}
            # "clone X en Y et demarre" -> demarrage apres clone
            if re.search(r'\b(?:et\s+)?(?:demarre[sz]?|start|boote?[rz]?|lance[rz]?)\b(?!\S)', q[m.end():]):
                args["start"] = True
            return make("fedora.vm_clone", args,
                        "rule: clone SOURCE en DEST", 0.95)

    # vm_clone via "copie de VM": "fais une copie de fedora-base" -> clone sans dest specifiee
    m = re.search(
        r'(?:fai[st]?\s+)?(?:une?\s+)?copie[rz]?\s+(?:de\s+|du\s+|d\s+)' + _VM_NAME_RE, q
    )
    if m:
        vm = m.group(1).strip()
        if vm not in _VM_GENERIC:
            return make("fedora.vm_clone", {"source_vm": vm},
                        "rule: copie de VM (clone sans dest)", 0.85,
                        missing_args=["new_vm_name"])

    # vm_copy: "copie/transfere FILE vers/sur/dans VM"
    m = re.search(
        r'(?:copie[rz]?|transfere[rz]?|envoie[rz]?)\s+(.+?)\s+(?:vers|sur|dans|a)\s+([\w][\w.-]*)',
        q
    )
    if m:
        src = m.group(1).strip()
        vm = m.group(2).strip()
        dest_file = src.split('/')[-1]
        return make("fedora.vm_copy",
                    {"source": src, "vm_name": vm, "dest": f"/tmp/{dest_file}"},
                    "rule: copie FILE vers VM", 0.92)

    # vm_verify: detection par verbe, extraction libre du nom de VM
    if re.search(r'(?:verifie[rz]?|verif|check)\b', q) \
            and not re.search(r'\b(?:backup|sauvegarde|disque|partition)\b', q):
        vm = _extract_vm_name(q)
        args: dict = {}
        if vm:
            args["vm_name"] = vm
        if re.search(r'\b(?:quick|rapide|vite)\b', q):
            args["quick"] = True
        if re.search(r'\bpackages?\b', q):
            args["compare_packages"] = True
        return make("fedora.vm_verify", args,
                    f"rule: verifie {'VM=' + vm if vm else 'sans VM specifiee'}",
                    0.93 if vm else 0.85)

    # vm_start: "demarre/lance/booter/allume VMNAME"
    _IS_DOMOTIQUE_CONTEXT = bool(
        re.search(r'\b(?:tv|tele(?:vision)?)\b', q)
        or re.search(r'\b(?:commande?|cmd)\b', q)
        or re.search(r'\bscene\b', q)
        or re.search(r'\bsur\b.{0,30}\b(?:ecran|moniteur|display|affichage|tele(?:vision)?|tv)\b', q)
        # Domotique: hue, lumieres, ambilight
        or re.search(r'\b(?:lumiere[sz]?|lumieres?|lampe[sz]?|ampoule[sz]?|ambilight|hue)\b', q)
        # Domotique: denon, ampli, home cinema
        or re.search(r'\b(?:denon|avr|amplificateur?|home.?cinema|ampli)\b', q)
        # Cast / Chromecast
        or re.search(r'\b(?:cast|chromecast|catt)\b', q)
    )
    if not _IS_DOMOTIQUE_CONTEXT:
        m = re.search(
            r'\b(?:demarr[ea]?[rz]?|lanc[ea]?[rz]?|boote?[rz]?|allum[ea]?[rz]?|start|power\s*on)\b\s+'
            r'(?:(?:la|le|les|l)\s+)?(?:(?:vm?\s+|machine(?:\s+virtuelle)?\s+|serveur\s+|hote\s+))?'
            + _VM_NAME_RE, q
        )
        if m:
            vm = m.group(1).strip()
            if vm not in _VM_GENERIC:
                return make("fedora.vm_start", {"vm_name": vm}, "rule: demarre VMNAME", 0.94)
            # Verbe vm_start detecte mais pas de nom specifique ("demarre une vm")
            return make("fedora.vm_start", {}, "rule: demarre sans nom specifique",
                        0.70, missing_args=["vm_name"])
        # Verbe vm_start detecte sans regex match (ex: "allume une vm")
        elif re.search(r'\b(?:demarr[ea]?[rz]?|lanc[ea]?[rz]?|boote?[rz]?|allum[ea]?[rz]?)\b', q) \
                and re.search(r'\b(?:vms?|machines?(?:\s+virtuelles?)?|serveurs?)\b', q):
            return make("fedora.vm_start", {}, "rule: demarre sans nom",
                        0.70, missing_args=["vm_name"])

    # vm_stop: "arrete/stoppe/stop [de force] VMNAME"
    # Exclure les contextes domotique (denon, cast, lumieres...)
    _IS_STOP_DOMOTIQUE = bool(
        re.search(r'\b(?:denon|avr|amplificateur?|home.?cinema|ampli)\b', q)
        or re.search(r'\b(?:cast|chromecast|catt)\b', q)
        or re.search(r'\b(?:lumiere[sz]?|lampe[sz]?|ampoule[sz]?|ambilight|hue)\b', q)
        or re.search(r'\b(?:tv|tele(?:vision)?)\b', q)
    )
    if not _IS_STOP_DOMOTIQUE:
        # etein(s|t|d|dre|ds) : toutes les fautes/variantes courantes d'"eteins"
        # ("eteint neutron-template-05" partait en denon_volume via le RAG)
        m = re.search(
            r'(?:arre?t[ea]?[rz]?|stopp[ea]?[rz]?|stop|etein(?:s|t|d|ds|dre)?)\s+'
            r'(?:de\s+)?(?:force\s+)?(?:(?:la|le)\s+)?(?:vm?\s+|machine(?:\s+virtuelle)?\s+|serveur\s+)?'
            + _VM_NAME_RE, q
        )
        if m:
            vm = m.group(1).strip()
            if vm not in _VM_GENERIC:
                args: dict = {"vm_name": vm}
                if re.search(r'\bforce\b', q):
                    args["force"] = True
                return make("fedora.vm_stop", args, "rule: arrete VMNAME", 0.94)

    # vm_destroy: "supprime/detruit/efface [de force] [la vm] VMNAME"
    m = re.search(
        r'(?:supprim[ea]?[rz]?|detru[iu][st]?[rz]?|efface[rz]?|destroy)\s+'
        r'(?:de\s+)?(?:force\s+)?(?:(?:la\s+)?(?:vm?\s+|machine\s+|serveur\s+))?'
        + _VM_NAME_RE, q
    )
    if m:
        vm = m.group(1).strip()
        if vm not in _VM_GENERIC:
            args: dict = {"vm_name": vm}
            if re.search(r'\bforce\b', q):
                args["force"] = True
            return make("fedora.vm_destroy", args, "rule: supprime VMNAME", 0.94)

    # vm_exec: "execute/exec/lance CMD sur/dans VMNAME"
    m = re.search(
        r'(?:execut[ea]?[rz]?|exec|lance[rz]?\s+(?:la\s+)?commande?)\s+'
        r'(.+?)\s+(?:sur|dans|a)\s+'
        + _VM_NAME_RE, q
    )
    if m:
        cmd = m.group(1).strip()
        vm = m.group(2).strip()
        if vm not in _VM_GENERIC and cmd:
            return make("fedora.vm_exec", {"vm_name": vm, "command": cmd},
                        "rule: exec CMD sur VMNAME", 0.93)

    # vm_snapshot: "cree un snapshot [live] de VMNAME"
    m = re.search(
        r'(?:cree?[rz]?\s+(?:un\s+)?snapshot[sz]?|snapshot[sz]?|instantane|capture)'
        r'\s+(?:live\s+)?(?:de\s+)?'
        + _VM_NAME_RE, q
    )
    if m:
        vm = m.group(1).strip()
        if vm not in _VM_GENERIC:
            args: dict = {"vm_name": vm}
            if re.search(r'\blive\b', q):
                args["live"] = True
            return make("fedora.vm_snapshot", args, "rule: snapshot VMNAME", 0.92)

    # vm_status: "c'est quoi arch-base" / "qu'est-ce que electron-backup-test"
    # (nom avec tirets = objet concret -> status detaille, PAS une question de
    # connaissance : LYRA hallucinait une reponse pour ces noms)
    m = re.search(
        r"\b(?:c'?est\s+quoi|qu'?est[- ]ce\s+que?)\s+(?:la\s+vm\s+)?([a-z0-9]+(?:-[a-z0-9]+)+)\b",
        q,
    )
    if m:
        return make("fedora.vm_status", {"vm_name": m.group(1), "detailed": True},
                    "rule: c'est quoi VMNAME", 0.93)

    # vm_status (VM specifique): "status [detaille] de la vm VMNAME"
    m = re.search(
        r'(?:status|statut|etat)\s+(?:detailles?\s+)?(?:de\s+)?(?:la\s+)?(?:vm?\s+)?'
        + _VM_NAME_RE, q
    )
    if m:
        vm = m.group(1).strip()
        if vm not in _VM_GENERIC:
            args: dict = {"vm_name": vm}
            if re.search(r'\bdetaille\b', q):
                args["detailed"] = True
            return make("fedora.vm_status", args, "rule: status VMNAME specifique", 0.92)

    # vm_status: "liste/affiche/montre/quelles sont [mes/les] VMs"
    if re.search(r'\b(?:liste[rz]?|affiche[rz]?|montre[rz]?|quelles?\s+sont|donne[rz]?\s+moi)\b', q) and \
            re.search(r'\b(?:vms?|machines?(?:\s+virtuelles?)?|serveurs?)\b', q):
        return make("fedora.vm_status", {}, "rule: liste VMs", 0.90)

    # vm_export: "exporte [moi] [de force] [la vm/machine] VM_NAME [mode exam]"
    m = re.search(
        r'(?:export[ea]?[rz]?|emballe[rz]?|packag[ea]?[rz]?|prepare[rz]?\s+pour\s+export)'
        r'\s+(?:moi\s+)?(?:de\s+)?(?:force\s+)?(?:(?:la\s+)?(?:vm?\s+|machine\s+))?'
        + _VM_NAME_RE, q
    )
    if m:
        vm = m.group(1).strip()
        if vm not in _VM_GENERIC:
            if re.search(r'\b(?:custom|personnalis[eé]|personnalis[eé]e|sur.mesure|choisir|choix)\b', q):
                mode = "custom"
            elif re.search(r'\b(?:exam|examen)\b', q):
                mode = "exam"
            else:
                mode = "classic"
            args: dict = {"vm_name": vm, "mode": mode}
            if re.search(r'\bforce\b', q):
                args["force"] = True
            return make("fedora.vm_export", args, f"rule: export VMNAME mode={mode}", 0.93)

    # vm_import: "importe depuis /chemin/archive.tar.gz [sous le nom NOM]"
    m = re.search(
        r'(?:import[ea]?[rz]?|installe[rz]?\s+(?:la\s+)?vm|charge[rz]?\s+(?:la\s+)?vm)\s+'
        r'(?:depuis\s+)?([/~][\w/.-]+\.tar\.gz)',
        q
    )
    if m:
        archive = m.group(1).strip()
        m_name = re.search(
            r'(?:sous\s+le\s+nom\s+|en\s+tant\s+que\s+|renomme[rz]?\s+en\s+'
            r'|avec\s+le\s+nom\s+["\']?|appele[e]?\s+'
            r'|(?:nomme[e]?\s+)?en\s+(?!mode\b|tant\b|cours\b|arriere\b|dry.?run\b)'
            r'|dans\s+(?!le\b|/|~))' + _VM_NAME_RE,
            q
        )
        args: dict = {"archive_path": archive}
        if m_name:
            name_candidate = m_name.group(1).strip().strip('"\'')
            if name_candidate not in _VM_GENERIC:
                args["new_name"] = name_candidate
        m_pool = re.search(r'(?:dans\s+le\s+pool\s+|pool\s+|dans\s+)([/~][\w/.-]+)', q)
        if m_pool:
            args["pool_dir"] = m_pool.group(1).strip()
        return make("fedora.vm_import", args, "rule: import archive.tar.gz", 0.93)

    return None


# Mots qui ne peuvent pas etre le nom d'une nouvelle VM dans une reponse libre
_NAME_STOPWORDS = _VM_GENERIC | {
    'oui', 'non', 'ok', 'pc', 'source', 'nom', 'hote', 'host', 'systeme',
    'system', 'clone', 'nouvelle', 'nouveau',
}


def extract_clone_system_name(query: str) -> str | None:
    """Nom de la nouvelle VM depuis une reponse libre (multi-tour pending).

    La source d'un clone systeme est TOUJOURS le PC hote : la reponse peut
    etre juste le nom ("test-vm"), ou une phrase ("le nom est test-vm",
    "la source est mon pc et le nom est X"). Extraction deterministe —
    le LLM 0.5b hallucinait sur ces reponses (regression 2026-08-14).
    """
    q = normalize(query).strip()
    if not q:
        return None
    # "le nom (de la nouvelle vm/machine) est X"
    m = re.search(
        r"\bnom\b(?:\s+de\s+la\s+(?:nouvelle\s+)?(?:vm|machine))?"
        r"\s*(?:est|sera|:)?\s+([\w][\w.-]*)", q)
    if not m:
        # "nomme-la X" / "appelle-la X"
        m = re.search(r"\b(?:nomme|appelle)(?:-?la)?\s+([\w][\w.-]*)", q)
    if not m:
        # "c'est X" / "ce sera X" (reponse complete uniquement)
        m = re.search(r"^(?:c'?est|ce\s+sera)\s+([\w][\w.-]*)\s*$", q)
    if m and m.group(1) not in _NAME_STOPWORDS:
        return m.group(1)
    # Reponse reduite au nom lui-meme ("test-vm")
    if re.fullmatch(r"[\w][\w.-]*", q) and q not in _NAME_STOPWORDS:
        return q
    return None
