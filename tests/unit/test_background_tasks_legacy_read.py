"""Une tache lancee avant la migration (fichiers dans l'ancien dossier) n'est pas
declaree « interrompue » : la lecture retombe sur l'emplacement enregistre."""
import os
from datetime import datetime

from lyra.hestia.background_tasks import BackgroundTask, BackgroundTaskManager


def _manager(monkeypatch, tmp_path):
    monkeypatch.setenv("LYRA_TASK_DIR", str(tmp_path / "neuf"))
    monkeypatch.setattr(BackgroundTaskManager, "_notify_tracking_completion", lambda s, t: None)
    monkeypatch.setattr(BackgroundTaskManager, "_create_completion_notification", lambda s, t: None)
    monkeypatch.setattr(BackgroundTaskManager, "_save_registry", lambda s: None)
    return BackgroundTaskManager()


def test_tache_restauree_lit_done_et_log_de_l_ancien_dossier(monkeypatch, tmp_path):
    ancien = tmp_path / "ancien"
    ancien.mkdir()
    (ancien / "lyra_task_t1.done").write_text("0")
    (ancien / "lyra_task_t1.log").write_text("tout est bon")
    pid_file = ancien / "lyra_task_t1.pid"
    pid_file.write_text("999999999")  # processus inexistant : la tache est terminee
    m = _manager(monkeypatch, tmp_path)
    m.tasks["t1"] = BackgroundTask("t1", "x", {}, datetime.now(), "d", "?", pid_file=str(pid_file))
    t = m.check_task("t1")
    assert t.completed and t.success is True
    assert t.result == "tout est bon"


def test_progression_lue_dans_l_ancien_dossier(monkeypatch, tmp_path):
    ancien = tmp_path / "ancien"
    ancien.mkdir()
    (ancien / "lyra_task_t2.progress").write_text('{"percentage": 40}')
    m = _manager(monkeypatch, tmp_path)
    m.tasks["t2"] = BackgroundTask("t2", "x", {}, datetime.now(), "d", "?",
                                   pid_file=str(ancien / "lyra_task_t2.pid"))
    assert m.get_task_progress("t2") == {"percentage": 40}


def test_la_lecture_n_ecrit_ni_ne_cree_rien(monkeypatch, tmp_path):
    m = _manager(monkeypatch, tmp_path)
    assert m.get_task_progress("absente") is None
    assert not os.path.exists(tmp_path / "neuf")
