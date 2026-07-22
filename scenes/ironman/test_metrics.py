"""
Tests pour les metriques de la scene Iron Man
"""

import json

import pytest

from .metrics import SceneMetrics, load_runs, format_comparison, MAX_RUNS


@pytest.fixture
def metrics_file(tmp_path):
    return tmp_path / "ironman_metrics.json"


class TestSceneMetrics:

    def test_record_and_finalize(self, metrics_file):
        m = SceneMetrics("full", [0, 1], metrics_file=metrics_file)
        m.record_step("phase1", 3.0, True, result={"latency_ms": 169.4})
        m.mark("first_visible_effect")
        m.finalize(success=True)

        runs = load_runs(metrics_file)
        assert len(runs) == 1
        run = runs[0]
        assert run["success"] is True
        assert run["steps"]["phase1"]["duration_s"] == 3.0
        assert run["steps"]["phase1"]["latency_ms"] == 169.4
        assert run["time_to_first_effect_s"] is not None
        assert run["total_s"] >= 0

    def test_extra_keys_filtered(self, metrics_file):
        """Seules les cles connues des resultats sont conservees."""
        m = SceneMetrics("full", [1], metrics_file=metrics_file)
        m.record_step("phase1", 1.0, True,
                      result={"latency_ms": 5, "gros_blob": "x" * 1000})
        m.finalize(success=True)
        step = load_runs(metrics_file)[0]["steps"]["phase1"]
        assert "latency_ms" in step
        assert "gros_blob" not in step

    def test_rotation_keeps_last_5(self, metrics_file):
        for i in range(MAX_RUNS + 3):
            m = SceneMetrics("sub-scene", [i], metrics_file=metrics_file)
            m.finalize(success=True)

        runs = load_runs(metrics_file)
        assert len(runs) == MAX_RUNS
        # Les plus recents sont conserves
        assert runs[-1]["selection"] == [MAX_RUNS + 2]
        assert runs[0]["selection"] == [3]

    def test_finalize_never_raises(self, tmp_path):
        """Un chemin de metriques invalide ne casse pas la scene."""
        bad = tmp_path / "not_a_dir_file"
        bad.write_text("blocker")
        m = SceneMetrics("full", [], metrics_file=bad / "x.json")
        m.finalize(success=True)  # ne doit pas lever


class TestLoadRuns:

    def test_missing_file(self, metrics_file):
        assert load_runs(metrics_file) == []

    def test_corrupt_file(self, metrics_file):
        metrics_file.write_text("{pas du json[")
        assert load_runs(metrics_file) == []

    def test_wrong_type(self, metrics_file):
        metrics_file.write_text(json.dumps({"pas": "une liste"}))
        assert load_runs(metrics_file) == []


class TestFormatComparison:

    def test_empty(self):
        assert "Aucun run" in format_comparison([])

    def test_columns_and_rows(self, metrics_file):
        for i in range(2):
            m = SceneMetrics("full", [1], metrics_file=metrics_file)
            m.record_step("phase1", 3.0 + i, True)
            m.finalize(success=(i == 0))

        out = format_comparison(load_runs(metrics_file))
        assert "phase1" in out
        assert "TOTAL" in out
        assert "OUI" in out and "NON" in out

    def test_missing_step_shows_dash(self, metrics_file):
        m1 = SceneMetrics("full", [1], metrics_file=metrics_file)
        m1.record_step("phase1", 1.0, True)
        m1.finalize(success=True)
        m2 = SceneMetrics("full", [2], metrics_file=metrics_file)
        m2.record_step("phase2", 1.0, True)
        m2.finalize(success=True)

        out = format_comparison(load_runs(metrics_file))
        assert "-" in out
