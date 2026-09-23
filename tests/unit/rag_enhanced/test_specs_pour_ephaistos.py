"""Le pipeline et le banc construisent les specs EPHAISTOS de la meme facon."""
from lyra.rag_enhanced.rag_3tier import specs_pour_ephaistos


def test_prefixe_et_registry_ecartee():
    res = [
        {"metadata": {"server_name": "FEDORA", "tool_name": "fedora.vm_start"}, "document": "Demarre une VM"},
        {"metadata": {"server_name": "FEDORA", "category": "vm"}, "document": "FEDORA (19 outils)"},
        {"metadata": {"name": "tv.mute"}, "document": "Coupe le son"},
    ]
    assert specs_pour_ephaistos(res) == ["fedora.vm_start: Demarre une VM", "tv.mute: Coupe le son"]


def test_vide():
    assert specs_pour_ephaistos([]) == [] and specs_pour_ephaistos(None) == []
