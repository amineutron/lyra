"""installer/bundle.py : bundle hors ligne (lyra#25)."""
import io
import json
import tarfile
from pathlib import Path

import pytest

from installer import bundle


def _faux_bundle(tmp_path: Path) -> Path:
    """Arborescence de bundle realiste : Ollama, cache HF avec liens, voix Piper."""
    racine = tmp_path / "src" / "lyra-bundle"
    blob = racine / "ollama" / "blobs" / "sha256-aa"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"poids")
    man = racine / "ollama" / bundle.chemin_manifeste_ollama("llama3.2:1b")
    man.parent.mkdir(parents=True)
    man.write_text(json.dumps({"config": {"digest": "sha256:aa"}, "layers": []}))
    hf = racine / "hf" / bundle.dossier_cache_hf(bundle.ST_MODEL)
    (hf / "blobs").mkdir(parents=True)
    (hf / "blobs" / "b1").write_text("{}")
    snap = hf / "snapshots" / "rev"
    snap.mkdir(parents=True)
    (snap / "config.json").symlink_to("../../blobs/b1")
    voix = racine / "piper"
    voix.mkdir()
    (voix / "fr_FR-upmc-medium.onnx").write_bytes(b"onnx")
    (voix / "fr_FR-upmc-medium.onnx.json").write_text("{}")
    (racine / "MANIFEST.json").write_text(json.dumps(bundle.construire_manifeste(racine)))
    archive = tmp_path / "lyra-bundle.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(racine, arcname="lyra-bundle")
    return archive


def test_chemins_ollama_et_hf():
    assert bundle.chemin_manifeste_ollama("llama3.2:1b").as_posix().endswith("library/llama3.2/1b")
    assert bundle.chemin_manifeste_ollama("qwen").name == "latest"
    assert bundle.dossier_cache_hf("Systran/faster-whisper-base") == "models--Systran--faster-whisper-base"


def test_blobs_ollama_config_et_couches():
    man = {"config": {"digest": "sha256:c"}, "layers": [{"digest": "sha256:l1"}, {"digest": "sha256:l2"}]}
    assert bundle.blobs_ollama(man) == ["sha256-c", "sha256-l1", "sha256-l2"]


def test_manifeste_detecte_alteration_et_manque(tmp_path):
    (tmp_path / "a").write_text("un")
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "b").write_text("deux")
    man = bundle.construire_manifeste(tmp_path)
    assert bundle.verifier_manifeste(tmp_path, man) == []
    (tmp_path / "a").write_text("UN")
    (tmp_path / "d" / "b").unlink()
    assert sorted(bundle.verifier_manifeste(tmp_path, man)) == ["altere : a", "manquant : d/b"]


def test_manifeste_format_inconnu_refuse(tmp_path):
    assert bundle.verifier_manifeste(tmp_path, {"format": 99, "files": {}})


@pytest.mark.parametrize("nom, lien", [("../evasion", None), ("/etc/passwd", None), ("x", "../../etc/passwd")])
def test_archive_malveillante_refusee(tmp_path, nom, lien):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(nom)
        if lien:
            info.type, info.linkname = tarfile.SYMTYPE, lien
        tar.addfile(info, io.BytesIO(b""))
    buf.seek(0)
    with tarfile.open(fileobj=buf) as tar, pytest.raises(ValueError):
        bundle.membres_surs(tar, tmp_path)


def test_installation_complete_sans_reseau(tmp_path):
    archive = _faux_bundle(tmp_path)
    cibles = {k: tmp_path / k for k in ("lyra", "ollama", "hf", "piper")}
    bundle.installer(archive, cibles["lyra"], cibles["ollama"], cibles["hf"], cibles["piper"], pip_ok=False)
    assert (cibles["ollama"] / "blobs" / "sha256-aa").read_bytes() == b"poids"
    assert (cibles["ollama"] / bundle.chemin_manifeste_ollama("llama3.2:1b")).is_file()
    config = cibles["hf"] / bundle.dossier_cache_hf(bundle.ST_MODEL) / "snapshots" / "rev" / "config.json"
    assert config.is_symlink() and config.read_text() == "{}"   # le lien relatif du cache HF survit
    assert (cibles["lyra"] / "models" / "fr_FR-upmc-medium.onnx").read_bytes() == b"onnx"


def test_bundle_altere_refuse_avant_toute_copie(tmp_path):
    archive = _faux_bundle(tmp_path)
    src = tmp_path / "src" / "lyra-bundle"
    (src / "piper" / "fr_FR-upmc-medium.onnx").write_bytes(b"trafique")
    with tarfile.open(archive, "w") as tar:          # manifeste d'origine, contenu modifie
        tar.add(src, arcname="lyra-bundle")
    cible = tmp_path / "ollama"
    with pytest.raises(SystemExit, match="altere"):
        bundle.installer(archive, tmp_path / "lyra", cible, tmp_path / "hf", tmp_path / "piper", pip_ok=False)
    assert not cible.exists()


def test_parties_inconnues_refusees():
    with pytest.raises(SystemExit):
        bundle.main(["create", "--parts", "ollama,inconnu"])


def test_regression_bundle_python_nu():
    # 'bundle.py install' tourne avec le Python du systeme, sans pyyaml : l'import
    # des constantes passait par steps/ -> pipeline -> catalog -> yaml et echouait.
    import subprocess
    import sys
    from pathlib import Path
    garde = (
        "import builtins,sys\n"
        "reel=builtins.__import__\n"
        "def g(n,*a,**k):\n"
        "    if n.split('.')[0] in ('yaml','requests','huggingface_hub','rich','httpx'):\n"
        "        raise ImportError('hors bibliotheque standard : '+n)\n"
        "    return reel(n,*a,**k)\n"
        "builtins.__import__=g\n"
        "import installer.bundle, installer.core.pipplan\n"
    )
    racine = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(racine)!r})\n" + garde],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
