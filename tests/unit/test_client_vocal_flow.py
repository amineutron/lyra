"""Flux du client vocal avec faux canal et fausse voix : ce qui est dit a voix haute."""

from lyra.client import vocal


class FakeChannel:
    def __init__(self, messages):
        self._messages = list(messages)
        self.sent = []

    def send(self, message):
        self.sent.append(message)

    def recv(self, timeout=None):
        return self._messages.pop(0)


class FakeVoice:
    def __init__(self, answers):
        self.said = []
        self._answers = list(answers)

    def speak(self, text):
        self.said.append(text)

    def listen(self):
        return self._answers.pop(0)


def _run(messages, answers):
    channel, voice = FakeChannel(messages), FakeVoice(answers)
    status = vocal._process_request(channel, voice, "volume", "default", False)
    return status, channel, voice


def test_confirmation_is_spoken_in_plain_french_and_technical_sentence_dropped():
    messages = [
        {"type": "output", "kind": "lyra", "text": "Je vais executer . Tu confirmes?"},
        {"type": "ask", "kind": "confirm", "prompt": "Executer tv.get_state ? [O/n]",
         "payload": {"tool": "tv.get_state", "arguments": {}, "danger": False}},
        {"type": "output", "kind": "tool_result", "text": "Volume a 60%."},
        {"type": "result"},
    ]
    status, channel, voice = _run(messages, ["oui"])
    assert status == "done"
    assert channel.sent[-1] == {"type": "answer", "value": "oui"}
    assert voice.said[0] == "Je vais consulter l'état de la télé. Tu confirmes ?"
    assert "Volume a 60 pour cent." in voice.said
    assert not any("executer ." in s or "tv.get_state" in s for s in voice.said)


def test_final_lyra_answer_is_still_spoken_at_result():
    messages = [
        {"type": "output", "kind": "lyra", "text": "Il est 20 heures."},
        {"type": "result"},
    ]
    _status, _channel, voice = _run(messages, [])
    assert voice.said == ["Il est 20 heures."]


def test_lyra_text_before_free_question_is_spoken_in_order():
    messages = [
        {"type": "output", "kind": "lyra", "text": "Plusieurs choix existent."},
        {"type": "ask", "kind": "input", "prompt": "Lequel ?", "payload": {}},
        {"type": "result"},
    ]
    _status, _channel, voice = _run(messages, ["le premier"])
    assert voice.said == ["Plusieurs choix existent.", "Lequel ?"]


def test_dangerous_confirmation_wording():
    messages = [
        {"type": "ask", "kind": "confirm", "prompt": "x",
         "payload": {"tool": "vm_stop", "arguments": {"vm_name": "preprod-09"},
                     "danger": True}},
        {"type": "result"},
    ]
    _status, channel, voice = _run(messages, ["ok vas-y", "non"])
    assert voice.said[0].startswith("Attention, action sensible")
    assert "preprod-09" in voice.said[0]
    # "ok vas-y" n'est pas une confirmation pour un outil dangereux : redemande
    assert voice.said[1] == "Je n'ai pas compris. Oui ou non ?"
    assert channel.sent[-1] == {"type": "answer", "value": "non"}
