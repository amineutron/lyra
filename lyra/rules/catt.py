"""Regles de detection pour les outils CATT (Chromecast)."""

import re
from typing import Optional

from .base import normalize, make

_YOUTUBE_URL_RE = r'https?://(?:www\.)?(?:youtube\.com/watch\S*|youtu\.be/[\w-]+)'


def detect(query: str):
    q = normalize(query)

    # cast_scan: "scan les appareils cast"
    # Note: SlangNorm peut transformer "cast" -> "diffuse"
    if re.search(r'\b(?:scan|cherche|liste|trouve|recherche|detecte)\b', q) and \
            re.search(r'\b(?:cast|diffuse?|appareils|devices|chromecast)\b', q):
        return make("catt.cast_scan", {}, "rule: scan appareils cast", 0.93)

    # cast_volume: "monte/baisse le volume du cast"
    if re.search(r'\b(?:cast|chromecast|diffusion|diffuse?)\b', q) and \
            re.search(r'\b(?:volume|son|monte|augmente|hausse|baisse|diminue|reduit|reduis)\b', q):
        m = re.search(r'\b(\d+)\b', q)
        level = int(m.group(1)) if m else None
        args = {"level": level} if level is not None else {}
        return make("catt.cast_volume", args, "rule: volume du cast", 0.92)

    # cast_youtube: URL YouTube + verbe cast/diffuse
    # Doit venir APRES cast_volume pour ne pas intercepter les requetes volume
    if re.search(_YOUTUBE_URL_RE, q) and \
            re.search(r'\b(?:caste?[rz]?|diffuse?[rz]?|envoie[rz]?)\b', q):
        m_cyt = re.search(_YOUTUBE_URL_RE, q)
        return make("catt.cast_youtube", {"url": m_cyt.group(0)},
                    "rule: cast youtube URL", 0.94)

    # cast_stop: "arrete/stop/stoppe le cast/la diffusion"
    if re.search(r'\b(?:arrete[rz]?|stop|stoppe[rz]?)\b', q) and \
            re.search(r'\b(?:cast|diffusion|chromecast)\b', q):
        return make("catt.cast_stop", {}, "rule: cast_stop", 0.93)

    # cast_pause: "mets le cast en pause"
    if re.search(r'\b(?:pause|en\s+pause)\b', q) and \
            re.search(r'\b(?:cast|diffusion|chromecast)\b', q):
        return make("catt.cast_pause", {}, "rule: cast_pause", 0.93)

    # cast_resume: "reprends/continue/relance le cast"
    if re.search(r'\b(?:reprends?|reprendre|continue[rz]?|relance[rz]?|play)\b', q) and \
            re.search(r'\b(?:cast|diffusion|chromecast)\b', q):
        return make("catt.cast_resume", {}, "rule: cast_resume", 0.93)

    # cast_seek: "avance/recule de N secondes/minutes [dans le cast]"
    m_seek_verb = re.search(r'\b(avance[rz]?|recule[rz]?)\b', q)
    if m_seek_verb and re.search(r'\b(\d+)\s*(?:seconde[sz]?|s\b|minute[sz]?|min\b)', q):
        m_seek_n = re.search(r'(\d+)\s*(?:seconde[sz]?|s\b|minute[sz]?|min\b)', q)
        n = int(m_seek_n.group(1))
        is_minute = bool(re.search(r'minute[sz]?|min\b', m_seek_n.group(0)))
        seconds = n * 60 if is_minute else n
        if 'recule' in m_seek_verb.group(1):
            seconds = -seconds
        return make("catt.cast_seek", {"seek_seconds": seconds},
                    f"rule: cast_seek {seconds}s", 0.93)

    return None
