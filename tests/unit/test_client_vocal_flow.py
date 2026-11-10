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


def test_tool_call_between_lyra_sentence_and_confirm_does_not_release_it():
    """Regression : le tool_call (silencieux) liberait la phrase technique retenue."""
    messages = [
        {"type": "output", "kind": "lyra", "text": "Je executer ?"},
        {"type": "output", "kind": "tool_call", "tool": "tv.get_state", "arguments": {}},
        {"type": "ask", "kind": "confirm", "prompt": "Executer tv.get_state ? [O/n]",
         "payload": {"tool": "tv.get_state", "arguments": {}, "danger": False}},
        {"type": "output", "kind": "tool_result", "success": True,
         "text": '{"powerstate": "On", "volume": 60, "muted": false}'},
        {"type": "result"},
    ]
    _status, _channel, voice = _run(messages, ["oui"])
    assert voice.said == ["Je vais consulter l'état de la télé. Tu confirmes ?",
                          "La télé est allumée, volume 60."]


def test_failure_is_one_short_sentence_and_lyra_comment_is_silent():
    messages = [
        {"type": "output", "kind": "tool_call", "tool": "hue.turn_on_group",
         "arguments": {}},
        {"type": "output", "kind": "tool_result", "success": False,
         "text": "Le processus d'activation du groupe a échoué. Détail : voir le fichier de log"},
        {"type": "output", "kind": "lyra_tag", "text": "ca a pas marche... details dans le log"},
        {"type": "result"},
    ]
    _status, _channel, voice = _run(messages, [])
    assert voice.said == ["Ça n'a pas marché. Le détail est à l'écran."]


def test_same_sentence_is_not_repeated_in_one_request():
    messages = [
        {"type": "output", "kind": "tool_result", "success": True, "text": "Volume réglé."},
        {"type": "output", "kind": "tool_result", "success": True, "text": "Volume réglé."},
        {"type": "result"},
    ]
    _status, _channel, voice = _run(messages, [])
    assert voice.said == ["Volume réglé."]


def test_long_reply_is_cut_to_two_short_sentences():
    long_text = ("Première phrase utile. Deuxième phrase utile. "
                 "Troisième phrase inutile. Quatrième phrase inutile.")
    messages = [{"type": "output", "kind": "lyra", "text": long_text}, {"type": "result"}]
    _status, _channel, voice = _run(messages, [])
    assert voice.said == ["Première phrase utile. Deuxième phrase utile."]
