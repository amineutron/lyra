"""Abonnes passifs du demon : etats diffuses, confirmations, restrictions."""

import socket
import socketserver
import threading
import time
from types import SimpleNamespace

import pytest

from lyra.daemon.display import build_display
from lyra.daemon.protocol import ChannelClosed, LineChannel
from lyra.daemon.remote_ui import RemoteUI
from lyra.daemon.server import LyraDaemon, _ConnectionHandler
from lyra.daemon.subscribe import StateHub, external_answer

TV = build_display("tv.volume_set", {"level": 30}, {"volume": 20, "muted": False})
VM = build_display("fedora.vm_start", {"vm_name": "web"},
                   {"vms": [{"name": "web", "state": "stopped"}]})


def pair():
    a, b = socket.socketpair()
    return LineChannel(a), LineChannel(b)


def collect(channel, n, timeout=3.0):
    return [channel.recv(timeout=timeout) for _ in range(n)]


def subscribed(hub):
    server_side, client_side = pair()
    assert hub.subscribe(server_side, {"type": "subscribed", "max_subscribers": 8})
    assert client_side.recv(timeout=3)["type"] == "subscribed"
    return server_side, client_side


# ---------------------------------------------------------------------------

class TestExternalAnswer:
    @pytest.mark.parametrize(("display", "danger", "value", "control", "expected"), [
        (VM, False, "o", None, "o"),
        (VM, False, "OUI", None, "o"),
        (VM, True, "o", None, "n"),          # jamais de confirmation d'un danger
        (VM, True, "oui", None, "n"),
        (VM, False, "n", None, "n"),
        (VM, False, "", None, "n"),          # Entree ne vaut pas oui pour un abonne
        (VM, False, "m", None, "n"),         # pas de correction par un abonne
        (VM, False, "ghost", None, "n"),
        (VM, False, "web", None, "web"),     # id propose : translate decidera
        (VM, False, "x" * 100, None, "n"),
        (VM, False, 5, None, "n"),
        (TV, False, "volume", {"id": "volume", "value": 45}, "volume=45"),
        (TV, False, "volume=45", None, "volume=45"),
        (TV, False, "volume", {"id": "volume", "value": 99}, "n"),
        (TV, False, "volume", {"id": "volume", "value": True}, "n"),
        (TV, False, "volume", {"id": "volume", "value": 4.5}, "n"),
        (TV, False, "volume", {"id": "other", "value": 4}, "n"),
        (TV, False, "volume", "volume=4", "n"),
    ])
    def test_table(self, display, danger, value, control, expected):
        assert external_answer(display, danger, value, control) == expected


class TestHub:
    def test_no_subscriber_is_free(self):
        hub = StateHub()
        hub.publish_state("s", "thinking")
        assert hub.open_ask("s", "tv.power_off", True, None) is None
        assert not hub.active and hub._last == {}

    def test_states_one_per_change_and_sanitized(self):
        hub = StateHub()
        _, client = subscribed(hub)
        hub.publish_state("s", "thinking", "fedora.vm_stop")
        hub.publish_state("s", "thinking", "fedora.vm_stop")      # doublon ignore
        hub.publish_state("s", "bogus")                           # etat inconnu ignore
        hub.publish_state("s", "error", "x\x00" + "y" * 200)
        first, second = collect(client, 2)
        assert (first["state"], first["label"], first["session"]) == ("thinking", "vm_stop", "s")
        assert isinstance(first["ts"], float)
        assert second["state"] == "error" and len(second["label"]) <= 60
        assert "\x00" not in second["label"]
        with pytest.raises(TimeoutError):
            client.recv(timeout=0.3)

    def test_subscriber_cap(self):
        hub = StateHub(max_subscribers=2)
        keep = [pair() for _ in range(2)]
        for srv, _ in keep:
            assert hub.subscribe(srv, {"type": "subscribed"})
        extra, _ = pair()
        assert hub.subscribe(extra, {"type": "subscribed"}) is False
        assert hub.subscriber_count() == 2

    def test_closed_subscriber_removed(self):
        hub = StateHub()
        srv, client = pair()
        hub.subscribe(srv, {"type": "subscribed"})
        client.recv(timeout=3)
        client.close()
        for _ in range(50):
            hub.publish_state("s", "thinking" if _ % 2 else "idle")
            if not hub.active:
                break
            time.sleep(0.05)
        assert not hub.active

    def test_slow_subscriber_dropped_without_blocking(self):
        hub = StateHub()
        release = threading.Event()
        aborted = threading.Event()

        class Stuck:
            def send(self, message):
                release.wait(5)
                raise ChannelClosed("coupe")

            def abort(self):
                aborted.set()
                release.set()

        hub.subscribe(Stuck(), {"type": "subscribed"})
        good_srv, good = subscribed(hub)
        received = []

        def drain():
            try:
                while True:
                    received.append(good.recv(timeout=5))
            except (TimeoutError, ChannelClosed):
                pass

        threading.Thread(target=drain, daemon=True).start()
        start = time.monotonic()
        for i in range(200):
            hub.publish_state("s", "thinking" if i % 2 else "idle")
            time.sleep(0.003)                          # laisse l'abonne sain consommer
        assert time.monotonic() - start < 2.0          # le pipeline n'attend pas
        assert aborted.wait(3)
        assert hub.subscriber_count() == 1             # seul le bon reste
        for _ in range(40):
            if len(received) >= 100:
                break
            time.sleep(0.05)
        assert len(received) >= 100                    # l'abonne sain a tout recu
        release.set()

    def test_answer_requires_subscription_and_broadcast_ask(self):
        hub = StateHub()
        outsider, _ = pair()
        assert hub.answer_from(outsider, {"value": "o"}) == "forbidden"
        srv, client = subscribed(hub)
        late_srv, _late = pair()
        pending = hub.open_ask("s", "fedora.vm_start", False, VM)
        assert hub.subscribe(late_srv, {"type": "subscribed"})   # abonne apres la diffusion
        assert hub.answer_from(late_srv, {"ask_id": pending.ask_id, "value": "o"}) == "forbidden"
        assert hub.answer_from(srv, {"ask_id": "inconnu", "value": "o"}) == "stale"
        assert hub.answer_from(srv, {"ask_id": pending.ask_id, "value": "o"}) is None
        assert hub.answer_from(srv, {"ask_id": pending.ask_id, "value": "n"}) == "stale"
        assert pending.value == "o"


# ---------------------------------------------------------------------------

class Confirm:
    """confirm_action dans un thread, avec un client demandeur et un abonne."""

    def __init__(self, tool, args, display_state, danger=None):
        self.hub = StateHub()
        self.sub_srv, self.sub = subscribed(self.hub)
        self.req_srv, self.requester = pair()
        self.rui = RemoteUI(self.req_srv, hub=self.hub, session_id="capsule-test",
                            state_provider=lambda t, a: display_state)
        self.args, self.tool = args, tool
        self.result = []
        self.thread = threading.Thread(target=lambda: self.result.append(
            self.rui.confirm_action(tool, args, danger=danger)))
        self.thread.start()
        self.ask = self.requester.recv(timeout=3)
        self.state = self.sub.recv(timeout=3)

    def finish(self):
        self.thread.join(5)
        assert not self.thread.is_alive()
        return self.result[0]


class TestConfirmFlow:
    def test_confirm_event_has_display_but_no_arguments(self):
        c = Confirm("fedora.vm_start", {"vm_name": "web", "secret": "hunter2"},
                    {"vms": [{"name": "web", "state": "stopped"}]})
        assert c.ask["type"] == "ask"
        s = c.state
        assert s["state"] == "confirm" and s["label"] == "vm_start"
        assert s["display"]["kind"] == "vms" and s["danger"] is False
        assert "hunter2" not in str(s) and "arguments" not in s
        c.requester.send({"type": "answer", "value": "n"})
        c.finish()

    def test_subscriber_confirms_non_dangerous_and_ack(self):
        c = Confirm("fedora.vm_start", {"vm_name": "web"},
                    {"vms": [{"name": "web", "state": "stopped"}]})
        c.sub.send({"type": "answer", "ask_id": c.state["ask_id"], "value": "web"})
        # le canal abonne n'est lu que cote serveur dans ce test : on appelle le hub
        assert c.hub.answer_from(c.sub_srv, {"ask_id": c.state["ask_id"], "value": "web"}) is None
        assert c.finish() is True
        ack = c.sub.recv(timeout=3)
        assert (ack["type"], ack["value"], ack["source"]) == ("answer_ack", "o", "subscriber")

    def test_subscriber_never_confirms_dangerous(self):
        for value in ("o", "oui", "vm"):
            c = Confirm("fedora.vm_destroy", {"vm_name": "vm"},
                        {"vms": [{"name": "vm", "state": "running"}]}, danger=True)
            assert c.state["danger"] is True
            assert c.hub.answer_from(c.sub_srv, {"ask_id": c.state["ask_id"],
                                                 "value": value}) is None
            assert c.finish() is False
            assert c.sub.recv(timeout=3)["value"] == "n"

    def test_slider_control_without_voice_path_is_not_confirmed(self):
        # confirm_action ne sait pas appliquer un curseur : refus (comportement existant)
        c = Confirm("tv.volume_set", {"level": 30}, {"volume": 20})
        c.hub.answer_from(c.sub_srv, {"ask_id": c.state["ask_id"], "value": "volume",
                                      "control": {"id": "volume", "value": 45}})
        assert c.finish() is False
        assert c.sub.recv(timeout=3)["value"] == "n"

    def test_slider_control_through_ask_confirm(self):
        hub = StateHub()
        sub_srv, sub = subscribed(hub)
        req_srv, requester = pair()
        rui = RemoteUI(req_srv, hub=hub, state_provider=lambda t, a: {"volume": 20})
        out = []
        t = threading.Thread(target=lambda: out.append(
            rui.ask_confirm("tv.volume_set", {"level": 30}, "?", False)))
        t.start()
        requester.recv(timeout=3)
        state = sub.recv(timeout=3)
        assert hub.answer_from(sub_srv, {"ask_id": state["ask_id"], "value": "volume",
                                         "control": {"id": "volume", "value": 45}}) is None
        t.join(5)
        assert out[0] == ("o", {"level": 45})
        assert sub.recv(timeout=3)["value"] == "n"   # confirm_action refuserait (pas de curseur)

    def test_client_answers_first_then_subscriber_is_stale(self):
        c = Confirm("fedora.vm_start", {"vm_name": "web"},
                    {"vms": [{"name": "web", "state": "stopped"}]})
        c.requester.send({"type": "answer", "value": "o"})
        assert c.finish() is True
        ack = c.sub.recv(timeout=3)
        assert (ack["value"], ack["source"]) == ("o", "client")
        assert c.hub.answer_from(c.sub_srv, {"ask_id": c.state["ask_id"],
                                             "value": "n"}) == "stale"

    def test_without_subscriber_legacy_path(self):
        hub = StateHub()
        req_srv, requester = pair()
        rui = RemoteUI(req_srv, hub=hub)
        t = threading.Thread(target=lambda: rui.confirm_action("catt.cast_stop", {}))
        t.start()
        requester.recv(timeout=3)
        requester.send({"type": "answer", "value": "o"})
        t.join(5)
        assert not t.is_alive() and hub._asks == {}


class TestRemoteUIStates:
    def test_state_sequence(self):
        hub = StateHub()
        _, sub = subscribed(hub)
        srv, _client = pair()
        rui = RemoteUI(srv, hub=hub, session_id="s1")
        rui.state("thinking")
        rui.tool_call("tv.power_on", {"token": "secret"})
        rui.tool_result("TOP SECRET OUTPUT", success=True)
        rui.lyra("Reponse complete confidentielle")
        rui.error("boom avec chemin/secret")
        events = collect(sub, 5)
        assert [e["state"] for e in events] == ["thinking", "thinking", "ok",
                                                "speaking", "error"]
        assert events[0].get("label") is None and events[1]["label"] == "power_on"
        blob = str(events)
        for leak in ("secret", "SECRET", "confidentielle", "boom", "token"):
            assert leak not in blob


# ---------------------------------------------------------------------------

@pytest.fixture
def served(tmp_path):
    path = f"/tmp/lyra-sub-{time.monotonic_ns()}.sock"
    calls = []
    daemon = SimpleNamespace(
        hub=StateHub(), _stop=threading.Event(), status="ready", started_at=time.time(),
        _send_safe=LyraDaemon._send_safe,
        handle_request=lambda *a, **k: calls.append("request"),
        handle_tool=lambda *a, **k: calls.append("tool"),
        handle_memory=lambda *a, **k: calls.append("memory"),
        handle_analyze=lambda *a, **k: calls.append("analyze"),
        purge_data=lambda **k: calls.append("purge") or {},
        health=lambda: calls.append("health") or {},
        tasks_snapshot=lambda: calls.append("tasks") or {},
    )

    class Srv(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

    server = Srv(path, _ConnectionHandler)
    server.daemon = daemon
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield path, daemon, calls
    daemon._stop.set()
    server.shutdown()
    server.server_close()
    import os
    os.unlink(path) if os.path.exists(path) else None


class TestServerRestrictions:
    def _client(self, path):
        from lyra.daemon.protocol import connect
        return connect(__import__("pathlib").Path(path))

    @pytest.mark.parametrize("mtype", ["request", "tool", "memory_list", "memory_update",
                                       "memory_delete", "memory_add", "analyze", "purge",
                                       "health", "tasks_poll", "hello", "bogus"])
    def test_subscriber_cannot_do_anything_but_answer(self, served, mtype):
        path, daemon, calls = served
        c = self._client(path)
        c.send({"type": "subscribe"})
        assert c.recv(timeout=3)["type"] == "subscribed"
        c.send({"type": mtype, "text": "eteins la tele", "name": "tv.power_off"})
        err = c.recv(timeout=3)
        assert (err["type"], err["code"]) == ("error", "forbidden")
        c.send({"type": "ping"})
        assert c.recv(timeout=3)["type"] == "pong"
        assert calls == []

    def test_restriction_survives_unsubscribe(self, served):
        path, daemon, calls = served
        c = self._client(path)
        c.send({"type": "subscribe"})
        c.recv(timeout=3)
        c.send({"type": "unsubscribe"})
        c.send({"type": "request", "text": "x"})
        assert c.recv(timeout=3)["code"] == "forbidden"
        assert calls == []
        assert not daemon.hub.active

    def test_answer_without_pending_ask_is_stale(self, served):
        path, _, _ = served
        c = self._client(path)
        c.send({"type": "subscribe"})
        c.recv(timeout=3)
        c.send({"type": "answer", "value": "o"})
        assert c.recv(timeout=3)["code"] == "stale"

    def test_normal_client_unchanged(self, served):
        path, daemon, calls = served
        c = self._client(path)
        c.send({"type": "request", "text": "x"})
        c.send({"type": "ping"})
        assert c.recv(timeout=3)["type"] == "pong"
        assert calls == ["request"]

    def test_disconnect_unsubscribes(self, served):
        path, daemon, _ = served
        c = self._client(path)
        c.send({"type": "subscribe"})
        c.recv(timeout=3)
        assert daemon.hub.active
        c.close()
        for _ in range(40):
            if not daemon.hub.active:
                break
            time.sleep(0.05)
        assert not daemon.hub.active

    def test_subscribe_limit(self, served):
        path, daemon, _ = served
        daemon.hub = StateHub(max_subscribers=1)
        a, b = self._client(path), self._client(path)
        a.send({"type": "subscribe"})
        assert a.recv(timeout=3)["type"] == "subscribed"
        b.send({"type": "subscribe"})
        assert b.recv(timeout=3)["code"] == "limit"
