"""Invariants des listes de securite (audit 2026-09-19)."""
from lyra.core.constants import (
    DANGEROUS_TOOLS,
    DESTRUCTIVE_TOOLS,
    PERFORMANCE_TOOLS,
    is_dangerous_tool,
    is_destructive_tool,
    is_performance_tool,
)


def test_destructif_est_un_sous_ensemble_des_dangereux():
    assert DESTRUCTIVE_TOOLS <= DANGEROUS_TOOLS


def test_performance_est_prefixe_par_le_serveur():
    # La comparaison est exacte sur le nom prefixe : "cast_youtube" sans prefixe
    # ne matchait jamais "catt.cast_youtube".
    sans_prefixe = [t for t in PERFORMANCE_TOOLS if "." not in t]
    assert sans_prefixe == []


def test_aucun_outil_dangereux_en_mode_performance():
    assert [t for t in PERFORMANCE_TOOLS if is_dangerous_tool(t)] == []
    assert not is_performance_tool("fedora.vm_destroy")


def test_prefixe_normalise():
    assert is_dangerous_tool("fedora.vm_destroy") and is_dangerous_tool("vm_destroy")
    assert is_destructive_tool("fedora.backup_restore")
    assert not is_destructive_tool("fedora.vm_stop")


def test_outils_qui_ecrivent_sont_sensibles():
    # revert/delete d'un snapshot, import d'un disque, copie de fichiers
    for outil in ("vm_snapshot", "vm_import", "vm_copy", "vm_exec"):
        assert is_dangerous_tool(f"fedora.{outil}"), outil


def test_cast_et_denon_sans_confirmation_en_performance():
    assert is_performance_tool("catt.cast_youtube")
    assert is_performance_tool("denon.volume_up")
