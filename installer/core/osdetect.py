"""Detection de la distribution et des commandes paquets associees.

Logique pure : parse un contenu os-release, retourne une description
immuable. Aucun acces systeme en dehors de detect_current().
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Paquets systeme par famille. nodejs/npm sont REQUIS (fedora-agents est un
# MCP Node) — leur absence dans l'ancien installeur interactif etait un bug.
_PACKAGES = {
    "fedora": [
        "python3", "python3-pip", "python3-devel", "git", "curl", "wget",
        "nodejs", "npm", "ffmpeg", "portaudio", "portaudio-devel",
        "gcc", "gcc-c++", "make", "cmake", "alsa-lib", "alsa-lib-devel",
        "espeak-ng", "zstd",
    ],
    "debian": [
        "python3", "python3-venv", "python3-dev", "python3-pip", "git",
        "curl", "wget", "nodejs", "npm", "ffmpeg", "portaudio19-dev",
        "libportaudio2", "gcc", "g++", "make", "cmake", "build-essential",
        "libssl-dev", "alsa-utils", "espeak-ng", "zstd",
    ],
    "arch": [
        "python", "python-pip", "git", "curl", "wget", "nodejs", "npm",
        "ffmpeg", "portaudio", "gcc", "make", "cmake", "base-devel",
        "alsa-utils", "espeak-ng", "zstd",
    ],
}

_INSTALL_CMD = {
    "fedora": ["sudo", "dnf", "install", "-y"],
    "debian": ["sudo", "apt-get", "install", "-y"],
    "arch": ["sudo", "pacman", "-S", "--noconfirm", "--needed"],
}


@dataclass(frozen=True)
class Distro:
    id: str            # ex: "fedora", "ubuntu", "arch"
    family: str        # "fedora" | "debian" | "arch" | "unknown"
    pretty_name: str

    @property
    def supported(self) -> bool:
        return self.family in _PACKAGES

    @property
    def packages(self) -> list[str]:
        return list(_PACKAGES.get(self.family, []))

    @property
    def install_cmd(self) -> list[str]:
        return list(_INSTALL_CMD.get(self.family, []))


_FAMILY_MAP = {
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora",
    "nobara": "fedora",
    "debian": "debian", "ubuntu": "debian", "linuxmint": "debian",
    "pop": "debian", "raspbian": "debian",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",
    "cachyos": "arch",
}


def parse_os_release(text: str) -> Distro:
    """Parse le contenu d'un fichier os-release (logique pure)."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip().strip('"').strip("'")

    distro_id = fields.get("ID", "unknown").lower()
    id_like = [w.lower() for w in fields.get("ID_LIKE", "").split()]

    family = _FAMILY_MAP.get(distro_id, "unknown")
    if family == "unknown":
        for candidate in id_like:
            if candidate in _FAMILY_MAP:
                family = _FAMILY_MAP[candidate]
                break

    return Distro(
        id=distro_id,
        family=family,
        pretty_name=fields.get("PRETTY_NAME", distro_id),
    )


def detect_current(path: str = "/etc/os-release") -> Distro:
    """Detecte la distribution de la machine courante."""
    p = Path(path)
    if not p.exists():
        return Distro(id="unknown", family="unknown", pretty_name="inconnu")
    return parse_os_release(p.read_text(encoding="utf-8"))
