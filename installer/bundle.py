"""Bundle hors ligne de Lyra (lyra#25) : tout ce que l'installeur telecharge, dans une archive.

Creer, sur une machine connectee (avec le venv de Lyra, pour huggingface_hub) :

    .venv/bin/python -m installer.bundle create --out lyra-bundle.tar

Installer, sur la machine sans reseau (python3 du systeme suffit, aucune dependance) :

    python3 -m installer.bundle install lyra-bundle.tar --lyra-dir ~/lyra

Contenu : modeles Ollama (dialogue + outils), modeles Hugging Face (MiniLM du RAG,
Whisper du micro), binaire et voix Piper, wheels Python du venv. Chaque fichier est
controle par sha256 (MANIFEST.json) avant toute copie : une archive alteree ou
tronquee est refusee en entier. Taille : environ 3 Go.

Ce que le bundle ne couvre pas : les paquets systeme (dnf/apt : portaudio, git,
nodejs...) et le binaire Ollama lui-meme, a installer depuis le media de la
distribution ; les serveurs MCP (depots git separes).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from installer.core.pipplan import _PIP_CORE, _PIP_ST_DEPS
from installer.core.sources import MODELS as OLLAMA_MODELS
from installer.core.sources import PIPER_URL as _PIPER_URL
from installer.core.sources import VOICE_BASE as _VOICE_BASE

FORMAT = 1
ST_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
WHISPER_REPO = "Systran/faster-whisper-{taille}"
VOICE_NAME = _VOICE_BASE.rsplit("/", 1)[-1]
_OLLAMA_REGISTRY = Path("manifests") / "registry.ollama.ai" / "library"


# ---------------------------------------------------------------- logique pure
def sha256_fichier(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def construire_manifeste(racine: Path) -> dict:
    """Empreinte de chaque fichier reel sous `racine` (les liens du cache HF sont suivis a la verification)."""
    fichiers = {}
    for p in sorted(racine.rglob("*")):
        if p.is_file() and not p.is_symlink() and p.name != "MANIFEST.json":
            fichiers[p.relative_to(racine).as_posix()] = {"sha256": sha256_fichier(p), "size": p.stat().st_size}
    return {"format": FORMAT, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": fichiers}


def verifier_manifeste(racine: Path, manifeste: dict) -> list[str]:
    """Liste des problemes (fichier manquant, taille ou empreinte differente). Vide = archive saine."""
    if manifeste.get("format") != FORMAT:
        return [f"format de bundle {manifeste.get('format')!r} inconnu (attendu {FORMAT})"]
    problemes = []
    for rel, attendu in manifeste.get("files", {}).items():
        p = racine / rel
        if ".." in Path(rel).parts or not p.is_file():
            problemes.append(f"manquant : {rel}")
        elif p.stat().st_size != attendu["size"] or sha256_fichier(p) != attendu["sha256"]:
            problemes.append(f"altere : {rel}")
    return problemes


def blobs_ollama(manifeste_modele: dict) -> list[str]:
    """Noms de fichier des blobs d'un modele Ollama ("sha256:ab" -> "sha256-ab")."""
    couches = [manifeste_modele.get("config", {})] + list(manifeste_modele.get("layers", []))
    return [c["digest"].replace(":", "-") for c in couches if c.get("digest")]


def chemin_manifeste_ollama(modele: str) -> Path:
    """"llama3.2:1b" -> manifests/registry.ollama.ai/library/llama3.2/1b."""
    nom, _, tag = modele.partition(":")
    return _OLLAMA_REGISTRY / nom / (tag or "latest")


def dossier_cache_hf(repo_id: str) -> str:
    """"org/nom" -> "models--org--nom" (format du cache huggingface_hub)."""
    return "models--" + repo_id.replace("/", "--")


def membres_surs(archive: tarfile.TarFile, destination: Path) -> list[tarfile.TarInfo]:
    """Refuse chemins absolus, remontees et liens qui sortent de la destination."""
    racine = destination.resolve()
    surs = []
    for m in archive.getmembers():
        cible = (racine / m.name).resolve()
        if not cible.is_relative_to(racine):
            raise ValueError(f"chemin hors de l'archive : {m.name}")
        if m.issym() or m.islnk():
            lien = (cible.parent / m.linkname).resolve() if m.issym() else (racine / m.linkname).resolve()
            if not lien.is_relative_to(racine):
                raise ValueError(f"lien hors de l'archive : {m.name} -> {m.linkname}")
        surs.append(m)
    return surs


def extraire(archive: tarfile.TarFile, destination: Path) -> None:
    """Extraction apres controle des chemins ; filtre "tar" quand Python le propose (3.12+)."""
    membres = membres_surs(archive, destination)
    if hasattr(tarfile, "tar_filter"):
        archive.extractall(destination, members=membres, filter="tar")
    else:
        archive.extractall(destination, members=membres)


# ---------------------------------------------------------------- creation
def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ajouter_ollama(dest: Path, modeles: list[str]) -> None:
    """Telecharge les modeles dans dest/ollama via un serveur Ollama prive (pas de sudo, pas de copie du systeme)."""
    dest.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "OLLAMA_MODELS": str(dest), "OLLAMA_HOST": f"127.0.0.1:{_port_libre()}"}
    serveur = subprocess.Popen(["ollama", "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        for modele in modeles:
            print(f"  ollama pull {modele}")
            subprocess.run(["ollama", "pull", modele], env=env, check=True)
    finally:
        serveur.terminate()
        serveur.wait(timeout=10)


def ajouter_hf(dest: Path, repos: list[str]) -> None:
    """Copie le cache Hugging Face local s'il existe, sinon telecharge dans dest/hf."""
    from huggingface_hub import snapshot_download

    source = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub")
    dest.mkdir(parents=True, exist_ok=True)
    for repo in repos:
        local = source / dossier_cache_hf(repo)
        if local.is_dir():
            print(f"  {repo} : copie du cache local")
            shutil.copytree(local, dest / dossier_cache_hf(repo), symlinks=True, dirs_exist_ok=True)
        else:
            print(f"  {repo} : telechargement")
            snapshot_download(repo, cache_dir=str(dest))


def ajouter_piper(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for url, nom in [(_PIPER_URL, "piper_linux_x86_64.tar.gz"),
                     (_VOICE_BASE + ".onnx", VOICE_NAME + ".onnx"), (_VOICE_BASE + ".onnx.json", VOICE_NAME + ".onnx.json")]:
        print(f"  {nom}")
        subprocess.run(["curl", "-fsSL", "-o", str(dest / nom), url], check=True)


def ajouter_wheels(dest: Path) -> None:
    """Wheels des trois blocs de l'etape venv, plus torch CPU (plateforme de cette machine)."""
    dest.mkdir(parents=True, exist_ok=True)
    pip = [sys.executable, "-m", "pip", "download", "-d", str(dest)]
    subprocess.run(pip + ["pip", "wheel", "setuptools"] + _PIP_CORE + _PIP_ST_DEPS, check=True)
    subprocess.run(pip + ["torch", "--index-url", "https://download.pytorch.org/whl/cpu"], check=True)
    subprocess.run(pip + ["--no-deps", "sentence-transformers"], check=True)


PARTIES = ("ollama", "hf", "piper", "wheels")


def creer(sortie: Path, parties: tuple[str, ...], whisper: str) -> None:
    with tempfile.TemporaryDirectory(prefix="lyra-bundle-") as tmp:
        racine = Path(tmp) / "lyra-bundle"
        if "ollama" in parties:
            ajouter_ollama(racine / "ollama", OLLAMA_MODELS)
        if "hf" in parties:
            ajouter_hf(racine / "hf", [ST_MODEL] + ([WHISPER_REPO.format(taille=whisper)] if whisper != "aucun" else []))
        if "piper" in parties:
            ajouter_piper(racine / "piper")
        if "wheels" in parties:
            ajouter_wheels(racine / "wheels")
        manifeste = construire_manifeste(racine)
        manifeste["parts"] = list(parties)
        (racine / "MANIFEST.json").write_text(json.dumps(manifeste, indent=1))
        with tarfile.open(sortie, "w") as tar:   # modeles deja compresses : pas de gzip
            tar.add(racine, arcname="lyra-bundle")
    taille = sortie.stat().st_size / 1e9
    print(f"bundle ecrit : {sortie} ({taille:.2f} Go, {len(manifeste['files'])} fichiers)")


# ---------------------------------------------------------------- installation
def _copier(src: Path, dst: Path) -> None:
    """Copie un arbre ; passe par sudo si la destination n'est pas inscriptible (dossier du service Ollama)."""
    parent = dst if dst.exists() else dst.parent
    if os.access(parent, os.W_OK):
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
    else:
        subprocess.run(["sudo", "cp", "-a", f"{src}/.", str(dst)], check=True)


def dossier_ollama_cible() -> Path:
    if os.environ.get("OLLAMA_MODELS"):
        return Path(os.environ["OLLAMA_MODELS"])
    systeme = Path("/usr/share/ollama/.ollama/models")
    return systeme if systeme.parent.exists() else Path.home() / ".ollama" / "models"


def installer(archive: Path, lyra_dir: Path, ollama_dir: Path, hf_dir: Path, piper_dir: Path, pip_ok: bool = True) -> None:
    with tempfile.TemporaryDirectory(prefix="lyra-bundle-") as tmp:
        with tarfile.open(archive) as tar:
            extraire(tar, Path(tmp))
        racine = Path(tmp) / "lyra-bundle"
        manifeste = json.loads((racine / "MANIFEST.json").read_text())
        problemes = verifier_manifeste(racine, manifeste)
        if problemes:
            raise SystemExit("bundle refuse :\n  " + "\n  ".join(problemes[:20]))
        print(f"bundle verifie : {len(manifeste['files'])} fichiers intacts")
        if (racine / "ollama").is_dir():
            _copier(racine / "ollama", ollama_dir)
            print(f"  modeles Ollama -> {ollama_dir}")
        if (racine / "hf").is_dir():
            hf_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(racine / "hf", hf_dir, symlinks=True, dirs_exist_ok=True)
            print(f"  modeles Hugging Face -> {hf_dir}")
        if (racine / "piper").is_dir():
            _installer_piper(racine / "piper", lyra_dir / "models", piper_dir)
        if (racine / "wheels").is_dir() and pip_ok:
            _installer_wheels(racine / "wheels", lyra_dir / ".venv")
    print("termine. Lancer Lyra avec LYRA_OFFLINE=1 pour interdire tout telechargement.")


def _installer_piper(src: Path, voix_dir: Path, piper_dir: Path) -> None:
    voix_dir.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.onnx*"):
        shutil.copy2(f, voix_dir / f.name)
    print(f"  voix Piper -> {voix_dir}")
    tarball = src / "piper_linux_x86_64.tar.gz"
    if tarball.is_file():
        piper_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball) as tar:
            extraire(tar, piper_dir)
        print(f"  binaire Piper -> {piper_dir}")


def _installer_wheels(wheels: Path, venv: Path) -> None:
    if not venv.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    pip = [str(venv / "bin" / "pip"), "install", "--no-index", "--find-links", str(wheels)]
    subprocess.run(pip + ["--upgrade", "pip", "wheel", "setuptools"], check=True)
    subprocess.run(pip + _PIP_CORE + ["torch"], check=True)
    subprocess.run(pip + ["--no-deps", "sentence-transformers"], check=True)
    subprocess.run(pip + _PIP_ST_DEPS, check=True)
    print(f"  dependances Python -> {venv}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="fabriquer le bundle (machine connectee)")
    c.add_argument("--out", type=Path, default=Path("lyra-bundle.tar"))
    c.add_argument("--parts", default=",".join(PARTIES), help=f"parmi {','.join(PARTIES)}")
    c.add_argument("--whisper", default="base", help="taille du modele Whisper, ou 'aucun'")
    i = sub.add_parser("install", help="installer depuis le bundle (sans reseau)")
    i.add_argument("archive", type=Path)
    i.add_argument("--lyra-dir", type=Path, default=Path.cwd())
    i.add_argument("--ollama-dir", type=Path, default=None)
    i.add_argument("--hf-dir", type=Path, default=None)
    i.add_argument("--piper-dir", type=Path, default=Path.home() / ".local" / "piper")
    i.add_argument("--sans-pip", action="store_true", help="ne pas installer les wheels")
    args = ap.parse_args(argv)
    if args.cmd == "create":
        parties = tuple(p for p in args.parts.split(",") if p)
        inconnues = set(parties) - set(PARTIES)
        if inconnues:
            ap.error(f"parties inconnues : {', '.join(sorted(inconnues))}")
        creer(args.out, parties, args.whisper)
    else:
        hf = args.hf_dir or Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
        installer(args.archive, args.lyra_dir, args.ollama_dir or dossier_ollama_cible(), hf, args.piper_dir,
                  pip_ok=not args.sans_pip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
