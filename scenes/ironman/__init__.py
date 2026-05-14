# Iron Man Scene Package
# Experience immersive ~33s synchronisant TV Philips + Hue
#
# Triggers vocaux:
#   - "je suis iron man"
#   - "je suis tony stark"
#   - "mode iron man"
#
# Usage:
#   from scenes.ironman import IronManOrchestrator
#
#   orchestrator = IronManOrchestrator()
#   if orchestrator.trigger("je suis iron man"):
#       # Scene lancee
#       pass

from .orchestrator import IronManOrchestrator, SceneState
from .phases import (
    Phase0Detection,
    Phase1Blackout,
    Phase2Impact,
    Phase3Buildup,
    Phase4Transition,
    Phase5TTS,
)

__all__ = [
    'IronManOrchestrator',
    'SceneState',
    'Phase0Detection',
    'Phase1Blackout',
    'Phase2Impact',
    'Phase3Buildup',
    'Phase4Transition',
    'Phase5TTS',
]
