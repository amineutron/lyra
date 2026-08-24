"""Tests unitaires du multi-sessions Pipeline (Phase 1 demon).

Le pipeline n'est PAS initialise (pas de ChromaDB/LLM) : on teste uniquement
la mecanique SessionStore / session_scope / properties _session et _ctx.
"""

import threading

import pytest

from lyra.core.config import RAGConfig
from lyra.core.pipeline import Pipeline
from lyra.rag.session_memory import SessionMemory


@pytest.fixture()
def pipeline() -> Pipeline:
    config = RAGConfig.from_dict({"session": {"max_turns": 5}})
    return Pipeline(config)


class TestSessionStore:
    def test_session_none_avant_init(self, pipeline):
        # Avant initialize(), pas de session par defaut : comportement historique
        assert pipeline._session is None

    def test_get_session_cree_et_reutilise(self, pipeline):
        first = pipeline.get_session("alpha")
        assert isinstance(first, SessionMemory)
        assert pipeline.get_session("alpha") is first
        assert pipeline.get_session("beta") is not first

    def test_session_par_defaut_via_property(self, pipeline):
        default = pipeline.get_session("default")
        assert pipeline._session is default

    def test_scope_change_la_session_active(self, pipeline):
        default = pipeline.get_session("default")
        with pipeline.session_scope("mobile"):
            scoped = pipeline._session
            assert scoped is not default
            assert scoped is pipeline.get_session("mobile")
        # Retour a la session par defaut apres le scope
        assert pipeline._session is default

    def test_scopes_imbriques(self, pipeline):
        with pipeline.session_scope("a"):
            session_a = pipeline._session
            with pipeline.session_scope("b"):
                assert pipeline._session is pipeline.get_session("b")
            assert pipeline._session is session_a

    def test_isolation_entre_sessions(self, pipeline):
        with pipeline.session_scope("client1"):
            pipeline._session.set_pending_action(
                tool_name="vm_start", known_args={}, missing_args=["vm_name"],
                clarification_question="quelle VM ?")
        with pipeline.session_scope("client2"):
            assert pipeline._session.get_pending_action() is None
        with pipeline.session_scope("client1"):
            pending = pipeline._session.get_pending_action()
            assert pending is not None and pending.tool_name == "vm_start"

    def test_ctx_embarque_la_session_du_scope(self, pipeline):
        with pipeline.session_scope("client1"):
            assert pipeline._ctx.session is pipeline.get_session("client1")
        with pipeline.session_scope("client2"):
            assert pipeline._ctx.session is pipeline.get_session("client2")

    def test_scope_est_par_thread(self, pipeline):
        """Deux threads avec des scopes differents ne se voient pas (ContextVar)."""
        pipeline.get_session("default")
        seen = {}
        barrier = threading.Barrier(2)

        def worker(name):
            with pipeline.session_scope(name):
                barrier.wait(timeout=5)  # les deux scopes actifs simultanement
                seen[name] = pipeline._session

        threads = [threading.Thread(target=worker, args=(n,)) for n in ("t1", "t2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert seen["t1"] is pipeline.get_session("t1")
        assert seen["t2"] is pipeline.get_session("t2")
        assert seen["t1"] is not seen["t2"]
