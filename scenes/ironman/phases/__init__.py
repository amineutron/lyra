# Iron Man Scene Phases
#
# Phase 0: Detection & Validation (2s)
# Phase 1: Blackout (3s)
# Phase 2: Impact (3.5s)
# Phase 3: Buildup (12s)
# Phase 4: Transition (7s)
# Phase 5: TTS J.A.R.V.I.S. (5.5s)

from .phase0_detection import Phase0Detection
from .phase1_blackout import Phase1Blackout
from .phase2_impact import Phase2Impact
from .phase3_buildup import Phase3Buildup
from .phase4_transition import Phase4Transition
from .phase5_tts import Phase5TTS

__all__ = [
    'Phase0Detection',
    'Phase1Blackout',
    'Phase2Impact',
    'Phase3Buildup',
    'Phase4Transition',
    'Phase5TTS',
]
