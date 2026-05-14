"""
Lyra HESTIA - Metrics Collector.

Collecte de metriques in-memory pour les executions MCP.
"""

from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from typing import Optional


@dataclass
class ExecutionMetric:
    """Metrique d'une execution."""
    tool_name: str
    success: bool
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)


class MetricsCollector:
    """Collecteur de metriques in-memory.

    Collecte les stats d'execution sans dependance externe.
    Alternative legere au logging Notion.
    """

    def __init__(self, max_history: int = 1000):
        """Initialise le collecteur.

        Args:
            max_history: Nombre max d'executions a conserver
        """
        self.max_history = max_history
        self._history: list[ExecutionMetric] = []

        # Compteurs par outil
        self._success_count: dict[str, int] = defaultdict(int)
        self._failure_count: dict[str, int] = defaultdict(int)
        self._total_duration: dict[str, float] = defaultdict(float)

    def record_execution(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float
    ):
        """Enregistre une execution.

        Args:
            tool_name: Nom de l'outil
            success: Succes ou echec
            duration_ms: Duree en millisecondes
        """
        # Historique
        metric = ExecutionMetric(
            tool_name=tool_name,
            success=success,
            duration_ms=duration_ms
        )
        self._history.append(metric)

        # Truncate si necessaire
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        # Compteurs
        if success:
            self._success_count[tool_name] += 1
        else:
            self._failure_count[tool_name] += 1

        self._total_duration[tool_name] += duration_ms

    def get_tool_stats(self, tool_name: str) -> dict:
        """Retourne les stats d'un outil.

        Args:
            tool_name: Nom de l'outil

        Returns:
            Dict avec success, failure, avg_duration_ms
        """
        success = self._success_count[tool_name]
        failure = self._failure_count[tool_name]
        total = success + failure

        return {
            "success_count": success,
            "failure_count": failure,
            "total_count": total,
            "success_rate": success / total if total > 0 else 0.0,
            "avg_duration_ms": (
                self._total_duration[tool_name] / total
                if total > 0 else 0.0
            )
        }

    def get_summary(self) -> dict:
        """Retourne un resume global.

        Returns:
            Dict avec stats globales et par outil
        """
        total_success = sum(self._success_count.values())
        total_failure = sum(self._failure_count.values())
        total = total_success + total_failure

        # Top 5 outils les plus utilises
        all_tools = set(self._success_count.keys()) | set(self._failure_count.keys())
        tool_counts = {
            t: self._success_count[t] + self._failure_count[t]
            for t in all_tools
        }
        top_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_executions": total,
            "total_success": total_success,
            "total_failure": total_failure,
            "success_rate": total_success / total if total > 0 else 0.0,
            "top_tools": [
                {"name": name, "count": count}
                for name, count in top_tools
            ],
            "tools": {
                tool: self.get_tool_stats(tool)
                for tool in all_tools
            }
        }

    def get_recent(self, n: int = 10) -> list[dict]:
        """Retourne les N dernieres executions.

        Args:
            n: Nombre d'executions

        Returns:
            Liste des dernieres executions
        """
        recent = self._history[-n:]
        return [
            {
                "tool": m.tool_name,
                "success": m.success,
                "duration_ms": m.duration_ms,
                "timestamp": m.timestamp.isoformat()
            }
            for m in reversed(recent)
        ]

    def clear(self):
        """Efface toutes les metriques."""
        self._history.clear()
        self._success_count.clear()
        self._failure_count.clear()
        self._total_duration.clear()
