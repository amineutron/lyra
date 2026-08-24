"""Regles de detection pour les outils BACKUP (fedora.backup_*)."""

import re
from typing import Optional

from .base import normalize, make

_BACKUP_RE = r'\b(?:backup|backups|sauvegarde|sauvegardes)\b'
_GENERIC = {'de', 'du', 'des', 'la', 'le', 'les', 'un', 'une', 'tous', 'toutes', 'tout'}


def detect(query: str):
    q = normalize(query)

    if not re.search(_BACKUP_RE, q):
        return None

    # backup_status: "status/etat/dashboard + backup"
    # watch=True jamais injecte (MCP boucle infinie)
    if re.search(r'\b(?:status|statut|etat|dashboard)\b', q):
        return make("fedora.backup_status", {}, "rule: status backup sans watch", 0.92)

    # backup_list: "liste + backups/sauvegardes"
    if re.search(r'\b(?:liste[rz]?|affiche[rz]?|montre[rz]?|quelles?\s+sont|donne[rz]?\s+moi)\b', q):
        return make("fedora.backup_list", {}, "rule: liste backups", 0.92)

    # backup_verify: "verifie le backup [de VM]"
    # Doit venir AVANT backup_create pour eviter collision sur "teste"
    if re.search(r'\b(?:verifie[rz]?|verif|teste[rz]?|controle[rz]?)\b', q) and \
            not re.search(r'\b(?:cree?[rz]?|fai[st]?[rz]?|genere[rz]?|nouveau|nouvelle)\b', q):
        m = re.search(r'(?:backup|sauvegarde)\s+(?:de\s+)?([\w][\w.-]*)', q)
        vm = m.group(1).strip() if m else None
        args = {"vm_name": vm} if vm and vm not in _GENERIC else {}
        return make("fedora.backup_verify", args, "rule: verifie backup", 0.93)

    # backup_create: "cree/fais/lance un backup [de VM]"
    if re.search(r'\b(?:cree?[rz]?|fai[st]?[rz]?|lance[rz]?|genere[rz]?|demarr[ea][rz]?)\b', q):
        m = re.search(r'(?:backup|sauvegarde)\s+(?:de\s+|d[e\']\s*)?([\w][\w.-]*)', q)
        vm = m.group(1).strip() if m else None
        args = {"vm_name": vm} if vm and vm not in _GENERIC else {}
        return make("fedora.backup_create", args, "rule: cree backup", 0.92)

    # backup_restore: "restaure [le backup de] VM"
    if re.search(r'\b(?:restaure[rz]?|restore|recupere[rz]?)\b', q):
        m = re.search(r'(?:backup|sauvegarde)\s+(?:de\s+)?([\w][\w.-]*)', q)
        vm = m.group(1).strip() if m else None
        args = {"identifier": vm} if vm and vm not in _GENERIC else {}
        return make("fedora.backup_restore", args, "rule: restaure backup", 0.92)

    # backup_clean: "nettoie/purge/supprime les anciens backups"
    if re.search(r'\b(?:nettoie[rz]?|purge[rz]?|supprim[ea][rz]?|efface[rz]?|vide[rz]?)\b', q):
        return make("fedora.backup_clean", {}, "rule: nettoie backups", 0.92)

    return None
