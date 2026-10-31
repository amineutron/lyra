"""Le socket du demon nait en 0600, meme sous un umask permissif, et l'umask est restaure."""
import os
import socketserver
import stat

from lyra.daemon.server import _bind_private


class _H(socketserver.BaseRequestHandler):
    pass


def test_socket_nait_en_0600_et_umask_restaure(tmp_path):
    chemin = tmp_path / "d.sock"
    ancien = os.umask(0o022)
    try:
        srv = _bind_private(lambda: socketserver.UnixStreamServer(str(chemin), _H))
        try:
            assert stat.S_IMODE(chemin.stat().st_mode) == 0o600
        finally:
            srv.server_close()
        assert os.umask(0o022) == 0o022  # l'umask permissif d'origine est revenu
    finally:
        os.umask(ancien)


def test_umask_restaure_meme_si_la_creation_echoue():
    ancien = os.umask(0o022)
    try:
        def boom():
            raise OSError("bind impossible")
        try:
            _bind_private(boom)
        except OSError:
            pass
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(ancien)
