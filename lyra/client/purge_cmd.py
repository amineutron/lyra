"""`lyra --purge [--dry-run] [-y]` : purge verifiable des donnees en clair (roadmap #54).

Si le demon tourne, la purge passe par lui (il vide aussi ce qu'il garde en
memoire) ; sinon elle agit directement sur les fichiers. Toujours dans cet
ordre : plan, confirmation (sauf -y), purge, verification.
"""
from __future__ import annotations

from pathlib import Path

from lyra.utils import purge

EXIT_OK, EXIT_ERROR, EXIT_ABORTED, EXIT_NOT_CLEAN = 0, 1, 2, 3


def _via_daemon(dry_run: bool) -> dict | None:
    """Reponse du demon, ou None s'il ne tourne pas (on ne le demarre pas pour ca).

    Un demon present mais injoignable (socket sature, bloque) n'est PAS « absent » :
    purger les fichiers dans son dos serait annule par ce qu'il garde en memoire."""
    from lyra.daemon.protocol import SOCKET_PATH, connect

    try:
        channel = connect(SOCKET_PATH)
    except (FileNotFoundError, ConnectionRefusedError):
        return None  # pas de demon : purge directe des fichiers
    except OSError as e:
        raise RuntimeError(f"demon present mais injoignable ({e})") from e
    try:
        channel.send({"type": "purge", "dry_run": dry_run})
        reply = channel.recv(timeout=180)
    finally:
        channel.close()
    if reply.get("type") != "purge_result":
        raise RuntimeError(reply.get("text", "reponse inattendue du demon"))
    return reply


def _from_dicts(rows: list[dict]) -> list[purge.PurgeItem]:
    return [purge.PurgeItem(r["label"], Path(r["path"]), r["count"], r["unit"]) for r in rows]


def run(dry_run: bool, assume_yes: bool, root: Path, confirm=input) -> int:
    try:
        return _run(dry_run, assume_yes, root, confirm)
    except RuntimeError as e:
        # demon d'avant cette commande : purger les fichiers dans son dos ne sert a
        # rien, il reecrirait le feedback qu'il garde en memoire
        print(f"Purge impossible via le demon : {e}")
        print("Redemarrer le demon (systemctl --user restart lyra-daemon) puis relancer.")
        return EXIT_ERROR


def _run(dry_run: bool, assume_yes: bool, root: Path, confirm) -> int:
    reply = _via_daemon(dry_run=True)
    items = _from_dicts(reply["items"]) if reply else purge.plan(root, Path.home())
    print(purge.render(items, "Donnees en clair" + (" (via le demon)" if reply else "") + " :"))
    if dry_run or purge.is_clean(items):
        print("Rien n'a ete efface." if dry_run else "Deja vide.")
        return EXIT_OK
    if not assume_yes and confirm("Tout effacer ? [o/N] ").strip().lower() not in ("o", "oui", "y", "yes"):
        print("Annule.")
        return EXIT_ABORTED

    reply = _via_daemon(dry_run=False)
    if reply:
        after = _from_dicts(reply["remaining"])
    else:
        purge.purge(root, Path.home())
        after = purge.plan(root, Path.home())
    print(purge.render(after, "Verification apres purge :"))
    if purge.is_clean(after):
        print("Purge verifiee : plus aucune donnee en clair dans ces magasins.")
        return EXIT_OK
    print("Purge incomplete : des donnees restent (voir ci-dessus).")
    return EXIT_NOT_CLEAN
