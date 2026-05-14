"""
Tests unitaires pour MetricsCollector.
"""

import pytest
from datetime import datetime
from time import sleep

from lyra.hestia.metrics import MetricsCollector, ExecutionMetric


class TestExecutionMetric:
    """Tests pour ExecutionMetric."""

    def test_basic_metric(self):
        """Test de creation d'une metrique simple."""
        metric = ExecutionMetric(
            tool_name="vm_start",
            success=True,
            duration_ms=123.45
        )
        assert metric.tool_name == "vm_start"
        assert metric.success is True
        assert metric.duration_ms == 123.45
        assert isinstance(metric.timestamp, datetime)

    def test_metric_timestamp_default(self):
        """Test que le timestamp est auto-genere."""
        before = datetime.now()
        metric = ExecutionMetric("test", True, 0.0)
        after = datetime.now()

        assert before <= metric.timestamp <= after

    def test_failed_metric(self):
        """Test d'une metrique d'echec."""
        metric = ExecutionMetric(
            tool_name="vm_destroy",
            success=False,
            duration_ms=50.0
        )
        assert metric.success is False


class TestMetricsCollector:
    """Tests pour MetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Cree un collecteur de test."""
        return MetricsCollector(max_history=100)

    def test_initialization(self):
        """Test d'initialisation."""
        collector = MetricsCollector(max_history=500)
        assert collector.max_history == 500
        assert len(collector._history) == 0

    def test_record_single_execution(self, collector):
        """Test d'enregistrement d'une execution."""
        collector.record_execution("vm_start", True, 100.0)

        stats = collector.get_tool_stats("vm_start")
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 0
        assert stats["total_count"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["avg_duration_ms"] == 100.0

    def test_record_multiple_executions(self, collector):
        """Test d'enregistrements multiples."""
        collector.record_execution("vm_start", True, 100.0)
        collector.record_execution("vm_start", True, 200.0)
        collector.record_execution("vm_start", False, 50.0)

        stats = collector.get_tool_stats("vm_start")
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["total_count"] == 3
        assert stats["success_rate"] == pytest.approx(0.6667, rel=0.01)
        assert stats["avg_duration_ms"] == pytest.approx(116.67, rel=0.01)

    def test_record_different_tools(self, collector):
        """Test avec differents outils."""
        collector.record_execution("vm_start", True, 100.0)
        collector.record_execution("vm_stop", True, 50.0)
        collector.record_execution("backup_create", False, 5000.0)

        summary = collector.get_summary()
        assert summary["total_executions"] == 3
        assert summary["total_success"] == 2
        assert summary["total_failure"] == 1

    def test_get_tool_stats_nonexistent(self, collector):
        """Test de stats pour un outil inexistant."""
        stats = collector.get_tool_stats("nonexistent")

        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["total_count"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_duration_ms"] == 0.0

    def test_success_rate_calculation(self, collector):
        """Test du calcul du taux de succes."""
        # 3 succes, 1 echec = 75%
        collector.record_execution("vm_start", True, 10.0)
        collector.record_execution("vm_start", True, 10.0)
        collector.record_execution("vm_start", True, 10.0)
        collector.record_execution("vm_start", False, 10.0)

        stats = collector.get_tool_stats("vm_start")
        assert stats["success_rate"] == 0.75

    def test_average_duration_calculation(self, collector):
        """Test du calcul de la duree moyenne."""
        collector.record_execution("vm_start", True, 100.0)
        collector.record_execution("vm_start", True, 200.0)
        collector.record_execution("vm_start", True, 300.0)

        stats = collector.get_tool_stats("vm_start")
        assert stats["avg_duration_ms"] == 200.0

    def test_get_summary_empty(self, collector):
        """Test de resume sans executions."""
        summary = collector.get_summary()

        assert summary["total_executions"] == 0
        assert summary["total_success"] == 0
        assert summary["total_failure"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["top_tools"] == []
        assert summary["tools"] == {}

    def test_get_summary_with_data(self, collector):
        """Test de resume avec donnees."""
        # Simuler plusieurs executions
        for _ in range(5):
            collector.record_execution("vm_start", True, 100.0)
        for _ in range(3):
            collector.record_execution("vm_status", True, 50.0)
        for _ in range(2):
            collector.record_execution("backup_list", True, 200.0)
        collector.record_execution("vm_start", False, 10.0)

        summary = collector.get_summary()

        assert summary["total_executions"] == 11
        assert summary["total_success"] == 10
        assert summary["total_failure"] == 1
        assert summary["success_rate"] == pytest.approx(0.909, rel=0.01)

    def test_top_tools_ordering(self, collector):
        """Test de l'ordre des top tools."""
        # vm_start: 10 executions
        for _ in range(10):
            collector.record_execution("vm_start", True, 100.0)
        # vm_status: 5 executions
        for _ in range(5):
            collector.record_execution("vm_status", True, 50.0)
        # backup_list: 3 executions
        for _ in range(3):
            collector.record_execution("backup_list", True, 200.0)

        summary = collector.get_summary()
        top_tools = summary["top_tools"]

        assert len(top_tools) == 3
        assert top_tools[0]["name"] == "vm_start"
        assert top_tools[0]["count"] == 10
        assert top_tools[1]["name"] == "vm_status"
        assert top_tools[1]["count"] == 5
        assert top_tools[2]["name"] == "backup_list"
        assert top_tools[2]["count"] == 3

    def test_top_tools_limit_5(self, collector):
        """Test que top_tools est limite a 5."""
        for i in range(10):
            collector.record_execution(f"tool_{i}", True, 10.0)

        summary = collector.get_summary()
        assert len(summary["top_tools"]) == 5

    def test_get_recent_empty(self, collector):
        """Test de recent sans executions."""
        recent = collector.get_recent(n=5)
        assert recent == []

    def test_get_recent_with_data(self, collector):
        """Test de recent avec donnees."""
        collector.record_execution("tool1", True, 100.0)
        collector.record_execution("tool2", False, 200.0)
        collector.record_execution("tool3", True, 300.0)

        recent = collector.get_recent(n=2)

        assert len(recent) == 2
        # Plus recent en premier
        assert recent[0]["tool"] == "tool3"
        assert recent[1]["tool"] == "tool2"

    def test_get_recent_format(self, collector):
        """Test du format de get_recent."""
        collector.record_execution("vm_start", True, 123.45)

        recent = collector.get_recent(n=1)

        assert len(recent) == 1
        entry = recent[0]
        assert entry["tool"] == "vm_start"
        assert entry["success"] is True
        assert entry["duration_ms"] == 123.45
        assert "timestamp" in entry

    def test_get_recent_respects_limit(self, collector):
        """Test que get_recent respecte la limite."""
        for i in range(10):
            collector.record_execution(f"tool_{i}", True, 10.0)

        recent = collector.get_recent(n=3)
        assert len(recent) == 3

    def test_history_truncation(self):
        """Test de la troncature de l'historique."""
        collector = MetricsCollector(max_history=5)

        for i in range(10):
            collector.record_execution(f"tool_{i}", True, 10.0)

        # Historique devrait etre tronque a 5
        assert len(collector._history) == 5
        # Devrait contenir les 5 derniers
        assert collector._history[-1].tool_name == "tool_9"
        assert collector._history[0].tool_name == "tool_5"

    def test_clear(self, collector):
        """Test de clear."""
        collector.record_execution("vm_start", True, 100.0)
        collector.record_execution("vm_stop", False, 50.0)

        collector.clear()

        assert len(collector._history) == 0
        summary = collector.get_summary()
        assert summary["total_executions"] == 0

    def test_clear_resets_all_counters(self, collector):
        """Test que clear reinitialise tous les compteurs."""
        collector.record_execution("vm_start", True, 100.0)
        collector.clear()

        stats = collector.get_tool_stats("vm_start")
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0

    def test_concurrent_tools_stats(self, collector):
        """Test des stats avec plusieurs outils."""
        collector.record_execution("vm_start", True, 100.0)
        collector.record_execution("vm_stop", True, 50.0)
        collector.record_execution("vm_start", False, 10.0)

        start_stats = collector.get_tool_stats("vm_start")
        stop_stats = collector.get_tool_stats("vm_stop")

        assert start_stats["total_count"] == 2
        assert stop_stats["total_count"] == 1
        assert start_stats["success_rate"] == 0.5
        assert stop_stats["success_rate"] == 1.0


class TestMetricsCollectorIntegration:
    """Tests d'integration pour MetricsCollector."""

    def test_realistic_session(self):
        """Test d'une session realiste."""
        collector = MetricsCollector()

        # Simuler une session d'utilisation
        # Utilisateur demande le status des VMs
        collector.record_execution("vm_status", True, 2500.0)

        # Demarre quelques VMs
        collector.record_execution("vm_start", True, 3000.0)
        collector.record_execution("vm_start", True, 2800.0)
        collector.record_execution("vm_start", False, 100.0)  # Echec

        # Check backup status
        collector.record_execution("backup_status", True, 1500.0)

        # Resume de la session
        summary = collector.get_summary()

        assert summary["total_executions"] == 5
        assert summary["total_success"] == 4
        assert summary["total_failure"] == 1
        assert summary["success_rate"] == 0.8

        # vm_start devrait etre le plus utilise
        top = summary["top_tools"][0]
        assert top["name"] == "vm_start"
        assert top["count"] == 3

    def test_performance_tracking(self):
        """Test de suivi des performances."""
        collector = MetricsCollector()

        # Enregistrer des executions avec differentes durees
        collector.record_execution("vm_clone", True, 60000.0)  # 1 min
        collector.record_execution("vm_clone", True, 65000.0)  # 1 min 5s
        collector.record_execution("vm_clone", True, 55000.0)  # 55s

        stats = collector.get_tool_stats("vm_clone")

        # Moyenne devrait etre ~60s
        assert stats["avg_duration_ms"] == 60000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
