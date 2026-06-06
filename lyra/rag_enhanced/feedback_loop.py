"""
Feedback Loop pour RAG Enhanced.

Système d'apprentissage continu basé sur succès/échecs RAG.

SESSION 6 (P5)
"""

import logging
import json
import time
import threading
from typing import Optional
from pathlib import Path
from collections import defaultdict, Counter
import re

from .types import FeedbackEntry

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """
    Boucle de feedback pour apprentissage continu.

    Fonctionnalités:
        - Record interactions (succès/échecs)
        - Suggère enrichissement après 3 échecs
        - Auto-enrichit après 5 échecs
        - Rotation dict si plein (200 slang, 80 synonyms)
        - Promotion après N hits
        - Rollback auto si dégradation

    Exemples:
        >>> feedback = FeedbackLoop()
        >>> feedback.record_interaction("start vm", "vm_start", 0.40, False)
        >>> suggestions = feedback.get_suggestions()
    """

    def __init__(
        self,
        feedback_file: str = "data/feedback.json",
        window_size: int = 100,
        suggestion_threshold: int = 3,
        auto_enrich_threshold: int = 5,
        promotion_threshold: int = 50,
        degradation_threshold: float = 0.20  # Baisse >20%
    ):
        """
        Initialise la boucle de feedback.

        Args:
            feedback_file: Chemin fichier JSON pour persistance
            window_size: Taille fenêtre glissante (défaut: 100)
            suggestion_threshold: Seuil suggestion (défaut: 3 échecs)
            auto_enrich_threshold: Seuil auto-enrichissement (défaut: 5 échecs)
            promotion_threshold: Seuil promotion (défaut: 50 hits)
            degradation_threshold: Seuil dégradation rollback (défaut: 20%)
        """
        self.feedback_file = Path(feedback_file)
        self.window_size = window_size
        self.suggestion_threshold = suggestion_threshold
        self.auto_enrich_threshold = auto_enrich_threshold
        self.promotion_threshold = promotion_threshold
        self.degradation_threshold = degradation_threshold

        # État interne
        self._interactions: list[FeedbackEntry] = []
        self._hits: Counter = Counter()  # Hits par pattern
        self._enrichments: dict[str, dict] = {}  # Enrichissements tracés
        self.slang_dict_size = 0  # Taille dict slang (simulé)
        self.synonym_dict_size = 0  # Taille dict synonymes (simulé)

        # Charger depuis fichier si existe
        self._load()

    def _load(self):
        """Charge le feedback depuis fichier JSON."""
        if self.feedback_file.exists():
            try:
                with open(self.feedback_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._interactions = data.get('interactions', [])
                    self._hits = Counter(data.get('hits', {}))
                    self._enrichments = data.get('enrichments', {})
                    self.slang_dict_size = data.get('slang_dict_size', 0)
                    self.synonym_dict_size = data.get('synonym_dict_size', 0)
                    logger.info(
                        f"Feedback chargé: {len(self._interactions)} interactions"
                    )
            except Exception as e:
                logger.error(f"Erreur chargement feedback: {e}")

    def _save(self):
        """Sauvegarde le feedback dans fichier JSON (appel direct, synchrone)."""
        try:
            self.feedback_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'interactions': self._interactions,
                    'hits': dict(self._hits),
                    'enrichments': self._enrichments,
                    'slang_dict_size': self.slang_dict_size,
                    'synonym_dict_size': self.synonym_dict_size
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde feedback: {e}")

    def _schedule_save(self):
        """Planifie une sauvegarde differee (5s) pour eviter les ecritures I/O a chaque requete."""
        if hasattr(self, '_save_timer') and self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(5.0, self._save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def record_interaction(
        self,
        query: str,
        tool_name: str,
        rag_score: float,
        success: bool
    ):
        """
        Enregistre une interaction.

        Args:
            query: Requête utilisateur
            tool_name: Outil MCP identifié
            rag_score: Score RAG (0-1)
            success: True si bon outil, False sinon
        """
        entry: FeedbackEntry = {
            'query': query,
            'tool_name': tool_name,
            'rag_score': rag_score,
            'success': success,
            'timestamp': int(time.time())
        }

        self._interactions.append(entry)

        # Limiter à window_size
        if len(self._interactions) > self.window_size:
            self._interactions = self._interactions[-self.window_size:]

        self._save()  # Sauvegarde immediate : donnee critique (une fois par requete utilisateur)

        logger.debug(
            f"Feedback: query='{query[:20]}...' tool={tool_name} "
            f"score={rag_score:.2f} success={success}"
        )

    def record_hit(self, pattern: str):
        """
        Enregistre un hit sur un pattern.

        Args:
            pattern: Pattern (mot slang, synonyme, etc.)
        """
        self._hits[pattern] += 1
        self._schedule_save()

    def mark_enrichment(self, pattern: str, dict_type: str):
        """
        Marque un enrichissement pour tracking.

        Args:
            pattern: Pattern ajouté
            dict_type: Type de dict ("slang", "synonym")
        """
        self._enrichments[pattern] = {
            'type': dict_type,
            'timestamp': int(time.time()),
            'baseline_rate': self.get_success_rate(None)  # Taux global avant
        }
        self._schedule_save()

    def get_stats(self, tool_name: str) -> dict:
        """
        Retourne statistiques pour un outil.

        Args:
            tool_name: Nom de l'outil MCP

        Returns:
            dict: {'success_count', 'failure_count', 'total', 'success_rate'}
        """
        tool_interactions = [
            i for i in self._interactions
            if i['tool_name'] == tool_name
        ]

        success_count = sum(1 for i in tool_interactions if i['success'])
        failure_count = len(tool_interactions) - success_count
        total = len(tool_interactions)
        success_rate = success_count / total if total > 0 else 0.0

        return {
            'success_count': success_count,
            'failure_count': failure_count,
            'total': total,
            'success_rate': success_rate
        }

    def get_average_score(self, tool_name: str) -> float:
        """
        Retourne score RAG moyen pour un outil.

        Args:
            tool_name: Nom de l'outil MCP

        Returns:
            float: Score moyen (0-1)
        """
        tool_interactions = [
            i for i in self._interactions
            if i['tool_name'] == tool_name
        ]

        if not tool_interactions:
            return 0.0

        return sum(i['rag_score'] for i in tool_interactions) / len(tool_interactions)

    def get_success_rate(self, tool_name: Optional[str] = None) -> float:
        """
        Retourne taux de succès global ou pour un outil.

        Args:
            tool_name: Nom de l'outil (None = global)

        Returns:
            float: Taux de succès (0-1)
        """
        if tool_name is None:
            # Taux global
            if not self._interactions:
                return 0.0
            success_count = sum(1 for i in self._interactions if i['success'])
            return success_count / len(self._interactions)
        else:
            # Taux pour outil spécifique
            stats = self.get_stats(tool_name)
            return stats['success_rate']

    def get_window(self, tool_name: Optional[str] = None) -> list[FeedbackEntry]:
        """
        Retourne fenêtre d'interactions.

        Args:
            tool_name: Filtrer par outil (None = toutes)

        Returns:
            list[FeedbackEntry]: Dernières interactions
        """
        if tool_name is None:
            return self._interactions
        else:
            return [i for i in self._interactions if i['tool_name'] == tool_name]

    def get_failure_patterns(self, min_count: int = 3) -> list[dict]:
        """
        Identifie patterns d'échec récurrents.

        Args:
            min_count: Nombre minimum d'occurrences

        Returns:
            list[dict]: [{'pattern': str, 'count': int, 'tool_name': str}, ...]
        """
        failures = [i for i in self._interactions if not i['success']]

        # Extraire mots depuis queries échouées
        pattern_counts = defaultdict(lambda: {'count': 0, 'tool_names': set()})

        for failure in failures:
            words = re.findall(r'\b\w+\b', failure['query'].lower())
            for word in words:
                if len(word) > 2:  # Ignorer mots courts
                    pattern_counts[word]['count'] += 1
                    pattern_counts[word]['tool_names'].add(failure['tool_name'])

        # Filtrer par min_count
        patterns = [
            {
                'pattern': pattern,
                'count': data['count'],
                'tool_names': list(data['tool_names'])
            }
            for pattern, data in pattern_counts.items()
            if data['count'] >= min_count
        ]

        # Trier par count DESC
        patterns.sort(key=lambda x: x['count'], reverse=True)

        return patterns

    def get_suggestions(self) -> list[dict]:
        """
        Retourne suggestions d'enrichissement.

        Returns:
            list[dict]: [{'type': str, 'pattern': str, 'count': int}, ...]
        """
        patterns = self.get_failure_patterns(min_count=self.suggestion_threshold)

        suggestions = []
        for p in patterns:
            # Heuristique simple: mot anglais → slang
            # TODO: Améliorer avec détection langue
            if re.match(r'^[a-z]+$', p['pattern']):
                suggestions.append({
                    'type': 'slang',
                    'pattern': p['pattern'],
                    'count': p['count'],
                    'suggestion': f"Ajouter '{p['pattern']}' au slang_dict"
                })
            else:
                suggestions.append({
                    'type': 'synonym',
                    'pattern': p['pattern'],
                    'count': p['count'],
                    'suggestion': f"Ajouter synonymes pour '{p['pattern']}'"
                })

        return suggestions

    def should_auto_enrich(self, pattern: str) -> bool:
        """
        Vérifie si on doit auto-enrichir pour un pattern.

        Args:
            pattern: Pattern à vérifier

        Returns:
            bool: True si auto-enrichissement recommandé
        """
        # Compter échecs contenant ce pattern
        failures = [
            i for i in self._interactions
            if not i['success'] and pattern.lower() in i['query'].lower()
        ]

        return len(failures) >= self.auto_enrich_threshold

    def should_rotate_dict(self, dict_type: str) -> bool:
        """
        Vérifie si on doit faire rotation du dictionnaire.

        Args:
            dict_type: Type de dict ("slang", "synonym")

        Returns:
            bool: True si dict plein
        """
        if dict_type == "slang":
            return self.slang_dict_size >= 200  # Limite TOPO
        elif dict_type == "synonym":
            return self.synonym_dict_size >= 80  # Limite TOPO
        else:
            return False

    def should_promote(self, pattern: str) -> bool:
        """
        Vérifie si on doit promouvoir une entrée feedback vers dict permanent.

        Args:
            pattern: Pattern à vérifier

        Returns:
            bool: True si promotion recommandée
        """
        return self._hits[pattern] >= self.promotion_threshold

    def should_rollback(self, pattern: str) -> bool:
        """
        Vérifie si on doit rollback un enrichissement.

        Args:
            pattern: Pattern enrichi

        Returns:
            bool: True si rollback recommandé (dégradation >20%)
        """
        if pattern not in self._enrichments:
            return False

        enrichment = self._enrichments[pattern]
        baseline_rate = enrichment['baseline_rate']
        current_rate = self.get_success_rate(None)

        # Vérifier dégradation
        if baseline_rate > 0:
            degradation = (baseline_rate - current_rate) / baseline_rate
            return degradation > self.degradation_threshold

        return False

    def extract_slang_candidates(self) -> list[dict]:
        """
        Extrait candidats slang depuis échecs.

        Returns:
            list[dict]: [{'word': str, 'count': int}, ...]
        """
        patterns = self.get_failure_patterns(min_count=1)

        # Liste de mots anglais courants (indicateurs de slang)
        # TODO: Étendre cette liste ou utiliser une détection de langue
        english_words = {
            'start', 'stop', 'kill', 'boot', 'run', 'check', 'list', 'show',
            'get', 'set', 'add', 'remove', 'delete', 'create', 'update',
            'switch', 'turn', 'open', 'close', 'cut', 'play', 'pause'
        }

        # Filtrer mots anglais courts (probable slang)
        candidates = [
            {'word': p['pattern'], 'count': p['count']}
            for p in patterns
            if (re.match(r'^[a-z]{3,8}$', p['pattern']) and
                p['pattern'] in english_words)
        ]

        return candidates

    def extract_synonym_candidates(self) -> list[dict]:
        """
        Extrait candidats synonymes depuis échecs.

        Returns:
            list[dict]: [{'word': str, 'count': int}, ...]
        """
        patterns = self.get_failure_patterns(min_count=1)

        # Filtrer mots qui ne sont PAS des slang anglais courts
        # (synonymes = mots français, soit avec accents, soit plus longs)
        slang_words = {c['word'] for c in self.extract_slang_candidates()}

        candidates = [
            {'word': p['pattern'], 'count': p['count']}
            for p in patterns
            if p['pattern'] not in slang_words  # Pas un slang
        ]

        return candidates


# Instance singleton (lazy-loaded)
_instance: Optional[FeedbackLoop] = None


def get_feedback_loop(feedback_file: str = "data/feedback.json") -> FeedbackLoop:
    """
    Retourne instance singleton du FeedbackLoop.

    Args:
        feedback_file: Chemin fichier JSON

    Returns:
        FeedbackLoop: Instance unique
    """
    global _instance
    if _instance is None:
        _instance = FeedbackLoop(feedback_file=feedback_file)
    return _instance
