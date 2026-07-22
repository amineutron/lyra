"""
Controle des ecrans PC (Hyprland DPMS) pour la scene Iron Man.
==============================================================

Eteint les ecrans du PC pendant le blackout (Phase 1) et arme une
sortie clavier : 1 seconde apres l'extinction, n'importe quelle touche
rallume les ecrans (option Hyprland misc:key_press_enables_dpms).

Le watcher (arming + auto-wake + restauration de l'option) tourne dans
un process bash detache : il survit a la fin du process Python, ce qui
est indispensable pour les tests de sous-scenes ou run_scene.py se
termine avant que l'utilisateur n'appuie sur une touche.

Sequence du watcher detache:
    T+0s   : dpms off (fait par turn_off avant de spawner le watcher)
    T+1s   : key_press_enables_dpms = 1 (touche => reveil)
    [test] : si auto_wake_s est defini, dpms on force apres ce delai
    reveil : quand tous les ecrans sont rallumes, restaure la valeur
             d'origine de key_press_enables_dpms puis se termine
"""

import logging
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

HYPRCTL = "hyprctl"
ARM_DELAY_S = 1.0          # Delai avant que les touches rallument
WATCHER_MAX_LIFETIME_S = 600  # Garde-fou: le watcher ne vit jamais plus de 10 min


def _hyprctl_available() -> bool:
    return shutil.which(HYPRCTL) is not None


def _get_key_press_option() -> int:
    """Lit la valeur actuelle de misc:key_press_enables_dpms (0 ou 1)."""
    try:
        result = subprocess.run(
            [HYPRCTL, "getoption", "misc:key_press_enables_dpms", "-j"],
            capture_output=True, text=True, timeout=3
        )
        import json
        return int(json.loads(result.stdout).get("int", 0))
    except Exception as e:
        logger.debug(f"[PC-SCREENS] getoption failed: {e}")
        return 0


class PCScreenController:
    """
    Eteint/rallume les ecrans PC via Hyprland DPMS.

    Args:
        enabled: False = no-op complet (config scenes.ironman.pc_screens)
        auto_wake_s: delai en secondes avant rallumage auto (tests
                     de sous-scenes uniquement, None en production)
    """

    def __init__(self, enabled: bool = True, auto_wake_s: Optional[int] = None):
        self.enabled = enabled and _hyprctl_available()
        self.auto_wake_s = auto_wake_s
        self._screens_off = False
        if enabled and not _hyprctl_available():
            logger.warning("[PC-SCREENS] hyprctl introuvable, ecrans PC ignores")

    def turn_off(self) -> bool:
        """
        Eteint tous les ecrans PC et arme la sortie clavier.

        Returns:
            True si l'extinction a ete lancee
        """
        if not self.enabled:
            return False

        original_option = _get_key_press_option()

        try:
            subprocess.run(
                [HYPRCTL, "dispatch", "dpms", "off"],
                capture_output=True, timeout=3
            )
        except Exception as e:
            logger.warning(f"[PC-SCREENS] dpms off failed: {e}")
            return False

        self._screens_off = True
        self._spawn_watcher(original_option)
        logger.info("[PC-SCREENS] Ecrans eteints (sortie: touche clavier apres 1s)")
        return True

    def _spawn_watcher(self, original_option: int):
        """
        Lance le watcher detache: arming clavier, auto-wake optionnel,
        restauration de l'option apres reveil.
        """
        auto_wake = f"{self.auto_wake_s}" if self.auto_wake_s else ""
        script = f"""
sleep {ARM_DELAY_S}
{HYPRCTL} keyword misc:key_press_enables_dpms 1 >/dev/null
deadline=$(( $(date +%s) + {WATCHER_MAX_LIFETIME_S} ))
auto_wake="{auto_wake}"
[ -n "$auto_wake" ] && wake_at=$(( $(date +%s) + auto_wake ))
while {HYPRCTL} monitors -j 2>/dev/null | grep -q '"dpmsStatus": false'; do
    now=$(date +%s)
    [ "$now" -ge "$deadline" ] && break
    if [ -n "$auto_wake" ] && [ "$now" -ge "$wake_at" ]; then
        {HYPRCTL} dispatch dpms on >/dev/null
        break
    fi
    sleep 1
done
{HYPRCTL} keyword misc:key_press_enables_dpms {original_option} >/dev/null
"""
        try:
            subprocess.Popen(
                ["bash", "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            logger.warning(f"[PC-SCREENS] watcher spawn failed: {e}")

    def wake(self):
        """Rallume immediatement les ecrans (rollback d'erreur)."""
        if not self.enabled or not self._screens_off:
            return
        try:
            subprocess.run(
                [HYPRCTL, "dispatch", "dpms", "on"],
                capture_output=True, timeout=3
            )
            self._screens_off = False
            logger.info("[PC-SCREENS] Ecrans rallumes (rollback)")
        except Exception as e:
            logger.warning(f"[PC-SCREENS] dpms on failed: {e}")
