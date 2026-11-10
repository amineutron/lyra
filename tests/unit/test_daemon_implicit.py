"""Intention implicite : session, expiration et flux de run_request."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from lyra.core.types import PipelineResult, QueryType
from lyra.daemon import actions, implicit
from lyra.models._analysis import EphaistosAnalysis
from lyra.rag.session_memory import SessionMemory


class FakePipeline:
    """Pipeline plat : `reply` est la reponse de discussion ; `action` (tool) la force en action."""

    def __init__(self, reply=""):
        self._session = SessionMemory()
        self._hestia = None
        self.executed = []
        self.process_calls = []
        self.reply = reply
        self.action = None

    @contextmanager
    def session_scope(self, session_id=None):
        yield

    def process(self, text, rag_step_callback=None, session_id=None):
        self.process_calls.append(text)
        if self.action:
            return PipelineResult(response="x", query_type=QueryType.ACTION,
                                  tool_call={"name": self.action, "arguments": {}})
        return PipelineResult(response=self.reply, query_type=QueryType.KNOWLEDGE)

    def process_precomputed(self, query, analysis, session_id=None):
        return PipelineResult(
            response=f"Je vais executer {analysis.tool}.", query_type=QueryType.ACTION,
            tool_call={"name": analysis.tool, "arguments": dict(analysis.arguments)})

    def execute_action(self, tool, args, **kw):
        self.executed.append(tool)
        return SimpleNamespace(executed=True, response="fait", error=None)

    def is_async_tool(self, name):
        return False


class FakeUI:
    def __init__(self, answer="o"):
        self.answer, self.asked = answer, []

    def info(self, t): pass
    def warning(self, t): pass
    def lyra(self, t): pass
    def lyra_tag(self, t): pass
    def error(self, t): pass
    def note_tool(self, t): pass
    def tool_call(self, *a, **k): pass
    def tool_result(self, *a, **k): pass
    def success(self, t): pass
    def progress(self, *a, **k): pass

    def ask(self, kind, prompt, payload=None):
        self.asked.append((kind, payload))
        return self.answer


def run(pipe, text, ui, **kw):
    return actions.run_request(pipe, None, text, ui, use_fast_path=False, interactive=True, **kw)


def propose(pipe, ui, reply="Je peux lancer la scene soiree si tu veux."):
    pipe.reply = reply
    run(pipe, "parle moi de la lumiere", ui)


class TestFlow:
    def test_ok_vasy_rejoue_avec_confirmation(self):
        pipe, ui = FakePipeline(), FakeUI("o")
        propose(pipe, ui)
        assert run(pipe, "ok vasy", ui) == 0
        assert [k for k, _ in ui.asked] == ["confirm"]
        assert pipe.executed == ["hue.activate_scene_by_name"]

    def test_refus_a_la_confirmation_n_execute_rien(self):
        pipe, ui = FakePipeline(), FakeUI("n")
        propose(pipe, ui)
        assert run(pipe, "ok vasy", ui) == 2
        assert pipe.executed == []

    @pytest.mark.parametrize("mode,yes", [("performance", False), ("default", True), ("performance", True)])
    def test_modes_p_et_y_ne_contournent_pas(self, mode, yes):
        pipe, ui = FakePipeline(), FakeUI("o")
        propose(pipe, ui)
        run(pipe, "ok vasy", ui, mode=mode, yes=yes)
        assert len(ui.asked) == 1

    def test_outil_dangereux_jamais_auto_confirme(self):
        pipe, ui = FakePipeline(), FakeUI("")
        propose(pipe, ui, "Je peux supprimer la vm test si tu veux.")
        run(pipe, "ok vasy", ui, mode="performance", yes=True)
        assert ui.asked and ui.asked[0][1]["danger"] is True
        assert pipe.executed == []

    def test_sans_proposition_comportement_inchange(self):
        pipe, ui = FakePipeline("Salut !"), FakeUI()
        run(pipe, "ok vasy", ui)
        assert pipe.process_calls == ["ok vasy"]
        assert ui.asked == [] and pipe.executed == []

    def test_usage_unique(self):
        pipe, ui = FakePipeline(), FakeUI("o")
        propose(pipe, ui)
        run(pipe, "ok vasy", ui)
        pipe.reply = "Salut"
        run(pipe, "ok vasy", ui)
        assert pipe.executed == ["hue.activate_scene_by_name"]

    def test_phrase_non_assentiment_ne_rejoue_pas(self):
        pipe, ui = FakePipeline(), FakeUI("o")
        propose(pipe, ui)
        pipe.reply = "ok"
        run(pipe, "ok merci", ui)
        assert pipe.executed == [] and ui.asked == []

    def test_proposition_expire_par_nombre_de_requetes(self):
        pipe, ui = FakePipeline(), FakeUI("o")
        propose(pipe, ui)
        pipe.reply = "Rien"
        for _ in range(implicit.MAX_REQUESTS):
            run(pipe, "et la meteo ?", ui)
        run(pipe, "ok vasy", ui)
        assert pipe.executed == []

    def test_une_action_explicite_efface_la_proposition(self):
        pipe, ui = FakePipeline(), FakeUI("o")
        propose(pipe, ui)
        pipe.action = "tv.power_on"
        run(pipe, "allume la tele", ui)
        pipe.action = None
        pipe.reply = "ok"
        run(pipe, "ok vasy", ui)
        assert pipe.executed == ["tv.power_on"]      # pas la scene proposee avant


class TestExpiration:
    def test_expire_par_duree(self):
        pipe = FakePipeline()
        implicit.remember_from_reply(pipe, "s", "Je peux allumer la tele.", now=1000.0)
        assert implicit.resolve_implicit(pipe, "s", "ok", now=1000.0 + implicit.MAX_AGE_S + 1) is None

    def test_valide_dans_les_temps(self):
        pipe = FakePipeline()
        implicit.remember_from_reply(pipe, "s", "Je peux allumer la tele.", now=1000.0)
        got = implicit.resolve_implicit(pipe, "s", "ok", now=1010.0)
        assert isinstance(got, EphaistosAnalysis) and got.tool == "tv.power_on"

    def test_question_en_attente_prioritaire(self):
        pipe = FakePipeline()
        implicit.remember_from_reply(pipe, "s", "Je peux allumer la tele.", now=1000.0)
        pipe._session.set_pending_action("fedora.vm_start", {}, ["vm_name"], "Quelle VM ?")
        assert implicit.resolve_implicit(pipe, "s", "ok", now=1001.0) is None

    def test_proposition_immuable(self):
        pipe = FakePipeline()
        implicit.remember_from_reply(pipe, "s", "Je peux allumer la tele.", now=1.0)
        with pytest.raises(AttributeError):
            pipe._session.get_suggestion().tool = "autre"
