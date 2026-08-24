"""Tests unitaires du demon : protocole, etat/crash, RemoteUI."""

import json
import socket
import threading

import pytest

from lyra.daemon import state as daemon_state
from lyra.daemon.protocol import ChannelClosed, LineChannel
from lyra.daemon.remote_ui import RemoteUI, RequestCancelled


# ---------------------------------------------------------------------------
# Helpers : paire de canaux connectes en memoire
# ---------------------------------------------------------------------------

@pytest.fixture()
def channel_pair():
    server_sock, client_sock = socket.socketpair()
    server = LineChannel(server_sock)
    client = LineChannel(client_sock)
    yield server, client
    server.close()
    client.close()


# ---------------------------------------------------------------------------
# Protocole
# ---------------------------------------------------------------------------

class TestLineChannel:
    def test_round_trip(self, channel_pair):
        server, client = channel_pair
        server.send({"type": "output", "kind": "info", "text": "salut"})
        message = client.recv(timeout=2)
        assert message == {"type": "output", "kind": "info", "text": "salut"}

    def test_unicode_et_accents(self, channel_pair):
        server, client = channel_pair
        server.send({"type": "output", "text": "démarrée à 100% — çà marche"})
        assert client.recv(timeout=2)["text"] == "démarrée à 100% — çà marche"

    def test_messages_multiples_dans_l_ordre(self, channel_pair):
        server, client = channel_pair
        for i in range(5):
            server.send({"type": "progress", "step": str(i), "data": {}})
        steps = [client.recv(timeout=2)["step"] for _ in range(5)]
        assert steps == ["0", "1", "2", "3", "4"]

    def test_eof_leve_channel_closed(self, channel_pair):
        server, client = channel_pair
        server.close()
        with pytest.raises(ChannelClosed):
            client.recv(timeout=2)

    def test_timeout(self, channel_pair):
        _server, client = channel_pair
        with pytest.raises(TimeoutError):
            client.recv(timeout=0.1)

    def test_message_sans_type_rejete(self, channel_pair):
        server, client = channel_pair
        server._sock.sendall(b'{"pas_de_type": 1}\n')
        with pytest.raises(ValueError):
            client.recv(timeout=2)

    def test_json_invalide_rejete(self, channel_pair):
        server, client = channel_pair
        server._sock.sendall(b"pas du json\n")
        with pytest.raises(ValueError):
            client.recv(timeout=2)


# ---------------------------------------------------------------------------
# Etat / crash
# ---------------------------------------------------------------------------

class TestDaemonState:
    @pytest.fixture(autouse=True)
    def _isolated_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(daemon_state, "STATE_PATH", tmp_path / "state.json")
        # Pas de journalctl dans les tests
        monkeypatch.setattr(daemon_state, "_journal_hint", lambda: "")

    def test_aucun_etat_pas_de_crash(self):
        assert daemon_state.read_crash_info() is None

    def test_arret_propre_pas_de_crash(self):
        daemon_state.write_state(daemon_state.STOPPED, reason="signal 15")
        assert daemon_state.read_crash_info() is None

    def test_demon_vivant_pas_de_crash(self):
        # write_state utilise notre propre pid, qui est vivant
        daemon_state.write_state(daemon_state.READY)
        assert daemon_state.read_crash_info() is None

    def test_ready_avec_pid_mort_est_un_crash(self):
        daemon_state.write_state(daemon_state.READY)
        data = json.loads(daemon_state.STATE_PATH.read_text())
        data["pid"] = 2 ** 22 + 12345  # pid inexistant
        daemon_state.STATE_PATH.write_text(json.dumps(data))
        crash = daemon_state.read_crash_info()
        assert crash is not None
        assert crash["reason"] == "inconnue"

    def test_starting_avec_pid_mort_echec_demarrage(self):
        daemon_state.write_state(daemon_state.STARTING)
        data = json.loads(daemon_state.STATE_PATH.read_text())
        data["pid"] = 2 ** 22 + 12345
        daemon_state.STATE_PATH.write_text(json.dumps(data))
        crash = daemon_state.read_crash_info()
        assert crash is not None
        assert crash["reason"] == "echec au demarrage"

    def test_detection_oom_dans_journal(self, monkeypatch):
        monkeypatch.setattr(daemon_state, "_journal_hint",
                            lambda: "process killed: Out of memory")
        daemon_state.write_state(daemon_state.READY)
        data = json.loads(daemon_state.STATE_PATH.read_text())
        data["pid"] = 2 ** 22 + 12345
        daemon_state.STATE_PATH.write_text(json.dumps(data))
        assert daemon_state.read_crash_info()["reason"] == "memoire saturee"

    @pytest.mark.parametrize("reason", [
        "memoire saturee", "processus tue", "erreur interne",
        "echec au demarrage", "inconnue", "raison inedite",
    ])
    def test_greeting_toujours_disponible(self, reason):
        greeting = daemon_state.crash_greeting({"reason": reason})
        assert isinstance(greeting, str) and len(greeting) > 20


# ---------------------------------------------------------------------------
# RemoteUI (ask/answer avec un vrai canal en memoire)
# ---------------------------------------------------------------------------

class TestRemoteUI:
    def test_outputs_serialises(self, channel_pair):
        server, client = channel_pair
        rui = RemoteUI(server)
        rui.info("a")
        rui.tool_result("fait", success=False, raw_error="boom")
        first = client.recv(timeout=2)
        second = client.recv(timeout=2)
        assert first["kind"] == "info" and first["text"] == "a"
        assert second["kind"] == "tool_result"
        assert second["success"] is False and second["raw_error"] == "boom"

    def _client_answers(self, client, value):
        def responder():
            message = client.recv(timeout=5)
            assert message["type"] == "ask"
            client.send({"type": "answer", "value": value})
        thread = threading.Thread(target=responder)
        thread.start()
        return thread

    def test_ask_round_trip(self, channel_pair):
        server, client = channel_pair
        thread = self._client_answers(client, "  ma reponse  ")
        result = RemoteUI(server).ask_input("nom de la VM ?")
        thread.join(timeout=5)
        assert result == "ma reponse"  # trim applique

    @pytest.mark.parametrize("value,expected", [
        ("", True), ("o", True), ("OUI", True), ("n", False),
        ("nimportequoi", False), ("m", "modify"),
    ])
    def test_confirm_action_interpretation(self, channel_pair, value, expected):
        server, client = channel_pair
        thread = self._client_answers(client, value)
        result = RemoteUI(server).confirm_action("vm_start", {"vm_name": "x"})
        thread.join(timeout=5)
        assert result == expected

    def test_cancel_leve_request_cancelled(self, channel_pair):
        server, client = channel_pair

        def responder():
            client.recv(timeout=5)
            client.send({"type": "cancel"})
        thread = threading.Thread(target=responder)
        thread.start()
        with pytest.raises(RequestCancelled):
            RemoteUI(server).ask_input("?")
        thread.join(timeout=5)

    def test_deconnexion_pendant_ask(self, channel_pair):
        server, client = channel_pair

        def responder():
            client.recv(timeout=5)
            client.close()
        thread = threading.Thread(target=responder)
        thread.start()
        with pytest.raises(RequestCancelled):
            RemoteUI(server).ask_input("?")
        thread.join(timeout=5)

    def test_uic_est_un_uicontext_complet(self, channel_pair):
        server, _client = channel_pair
        uic = RemoteUI(server).uic()
        # Les 9 callables du contrat UIContext sont fournis
        for name in ("print_info", "print_success", "print_error",
                     "print_warning", "print_tool_result", "colored",
                     "confirm_action", "ask_input", "println"):
            assert callable(getattr(uic, name))
        assert uic.colored("texte", "red") == "texte"
