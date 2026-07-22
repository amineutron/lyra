"""
Fixtures pytest pour les tests de la scene Iron Man.

Desactive la telemetrie (metriques ~/.lyra + sessions tracking dashboard)
pour tous les tests du repertoire: les tests ne doivent jamais ecrire de
vraies metriques ni polluer le dashboard tracking.
"""

import os

os.environ.setdefault("IRONMAN_NO_TELEMETRY", "1")
