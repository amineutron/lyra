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


class TestMessageExecution:
    """Mode performance : on dit ce qu'on fait, pas "Tu confirmes ?" (recette 2026-09-23)."""

    def test_message(self):
        from lyra.daemon.actions import _message_execution
        assert _message_execution("tv.power_on", {}) == "J'execute tv.power_on."
        assert _message_execution("fedora.vm_start", {"vm_name": "x"}) == "J'execute fedora.vm_start (vm_name=x)."


class TestHandleTool:
    """Route directe (roadmap #73) : un outil nomme, sans modele, meme confirmation que la voix."""

    def _daemon(self, executed=True, error=None, dangerous_confirmed=None):
        from types import SimpleNamespace as N
        from unittest.mock import Mock

        from lyra.daemon.server import LyraDaemon
        d = LyraDaemon.__new__(LyraDaemon)
        d._init_done = threading.Event()
        d._init_done.set()
        d._init_error = [None]
        d._busy = threading.Lock()
        d._busy_with = ""
        v2 = Mock()
        v2._hestia.get_available_tools.return_value = [{"name": "tv.power_on"}, {"name": "fedora.vm_destroy"}]
        v2.execute_action.return_value = N(executed=executed, error=error, response="TV allumee")
        d.pipeline = N(_pipeline_v2=v2)
        return d, v2

    def _echange(self, d, message, reponses=()):
        """Envoie `message` au demon dans un thread, repond aux ask avec `reponses`, rend les messages recus."""
        server_sock, client_sock = socket.socketpair()
        server, client = LineChannel(server_sock), LineChannel(client_sock)
        recus = []
        t = threading.Thread(target=d.handle_tool, args=(server, message, "s"))
        t.start()
        it = iter(reponses)
        while True:
            m = client.recv(timeout=5)
            recus.append(m)
            if m.get("type") == "ask":
                client.send({"type": "answer", "value": next(it)})
            if m.get("type") == "result":
                break
        t.join(5)
        return recus

    def test_outil_simple_execute_sans_confirmation(self):
        d, v2 = self._daemon()
        recus = self._echange(d, {"type": "tool", "name": "tv.power_on", "arguments": {}})
        assert [m["type"] for m in recus] == ["output", "result"]
        assert recus[0]["kind"] == "tool_result" and recus[0]["success"] is True and recus[1]["exit_code"] == 0
        v2.execute_action.assert_called_once()

    def test_outil_dangereux_demande_confirmation(self):
        d, v2 = self._daemon()
        recus = self._echange(d, {"type": "tool", "name": "fedora.vm_destroy", "arguments": {"vm_name": "x"}}, reponses=["n"])
        assert recus[0]["type"] == "ask" and recus[0]["kind"] == "confirm" and recus[0]["payload"]["danger"] is True
        assert recus[-1]["exit_code"] == 2
        v2.execute_action.assert_not_called()

    def test_outil_dangereux_deja_confirme_par_le_client(self):
        d, v2 = self._daemon()
        recus = self._echange(d, {"type": "tool", "name": "fedora.vm_destroy", "arguments": {"vm_name": "x"},
                                  "options": {"confirmed": True}})
        assert [m["type"] for m in recus] == ["output", "result"]
        v2.execute_action.assert_called_once()

    def test_outil_inconnu_refuse(self):
        d, v2 = self._daemon()
        recus = self._echange(d, {"type": "tool", "name": "tv.teleporter", "arguments": {}})
        assert recus[0]["type"] == "error" and recus[-1]["exit_code"] == 1
        v2.execute_action.assert_not_called()

    def test_echec_d_execution(self):
        d, _ = self._daemon(executed=True, error="Error executing tool")
        recus = self._echange(d, {"type": "tool", "name": "tv.power_on", "arguments": {}})
        assert recus[0]["success"] is False and recus[-1]["exit_code"] == 1


class TestPrechauffage:
    """Le prechauffage Ollama ne retient plus le demon (2026-09-26 : Ollama bloque = 240 s d'indisponibilite)."""

    def _daemon(self, preload):
        from types import SimpleNamespace as N

        from lyra.daemon.server import LyraDaemon
        d = LyraDaemon.__new__(LyraDaemon)
        d.pipeline = N(preload_models=preload)
        return d

    def test_rend_la_main_pendant_que_le_modele_charge(self):
        libere = threading.Event()
        appele = threading.Event()

        def preload():
            appele.set()
            libere.wait(5)

        thread = self._daemon(preload)._preload_in_background()
        assert appele.wait(2) and thread.is_alive()
        libere.set()
        thread.join(2)
        assert not thread.is_alive()

    def test_echec_journalise_sans_lever(self, caplog):
        def preload():
            raise RuntimeError("ollama injoignable")

        with caplog.at_level("WARNING", logger="lyra.daemon"):
            self._daemon(preload)._preload_in_background().join(2)
        assert "ollama injoignable" in caplog.text
