"""
Tests unitaires pour le module TOON.
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from lyra.utils.toon import (
    toon_encode,
    toon_encode_specs,
    toon_encode_history,
    parse_spec,
    _quote_value,
)


class TestQuoteValue:
    """Tests pour _quote_value."""

    def test_simple_value(self):
        assert _quote_value("hello") == "hello"

    def test_empty_value(self):
        assert _quote_value("") == ""

    def test_value_with_comma(self):
        assert _quote_value("a, b") == '"a, b"'

    def test_value_with_quotes(self):
        assert _quote_value('say "hello"') == '"say ""hello"""'

    def test_value_with_newline(self):
        assert _quote_value("line1\nline2") == '"line1\nline2"'


class TestToonEncode:
    """Tests pour toon_encode."""

    def test_empty_list(self):
        assert toon_encode([]) == ""

    def test_single_record(self):
        result = toon_encode([{"name": "test", "value": "42"}])
        assert result == "[1]{name,value}:\ntest,42"

    def test_multiple_records(self):
        records = [
            {"name": "vm_start", "server": "fedora"},
            {"name": "vm_stop", "server": "fedora"},
        ]
        result = toon_encode(records)
        lines = result.split("\n")
        assert lines[0] == "[2]{name,server}:"
        assert lines[1] == "vm_start,fedora"
        assert lines[2] == "vm_stop,fedora"

    def test_records_with_commas(self):
        records = [
            {"name": "test", "desc": "a, b, c"},
        ]
        result = toon_encode(records)
        assert '"a, b, c"' in result

    def test_missing_field_defaults_empty(self):
        records = [
            {"name": "a", "desc": "hello"},
            {"name": "b"},
        ]
        result = toon_encode(records)
        lines = result.split("\n")
        assert lines[2] == "b,"

    def test_header_format(self):
        records = [{"a": "1", "b": "2", "c": "3"}]
        result = toon_encode(records)
        assert result.startswith("[1]{a,b,c}:")

    def test_count_in_header(self):
        records = [{"x": str(i)} for i in range(5)]
        result = toon_encode(records)
        assert result.startswith("[5]{x}:")


class TestParseSpec:
    """Tests pour parse_spec."""

    def test_basic_spec(self):
        spec = """Outil: vm_start
Serveur: fedora
Description: Demarre une VM KVM
Parametres obligatoires: vm_name
Schema:
  - vm_name (string): Nom de la VM"""

        result = parse_spec(spec)
        assert result["outil"] == "vm_start"
        assert result["serveur"] == "fedora"
        assert result["desc"] == "Demarre une VM KVM"
        assert result["req"] == "vm_name"
        assert result["opt"] == ""
        assert "vm_name(string):Nom de la VM" in result["schema"]

    def test_spec_with_optional_params(self):
        spec = """Outil: turn_on_group
Serveur: hue
Description: Allume les lumieres
Parametres optionnels: group_id
Schema:
  - group_id (integer): ID du groupe"""

        result = parse_spec(spec)
        assert result["outil"] == "turn_on_group"
        assert result["req"] == ""
        assert result["opt"] == "group_id"
        assert "group_id(integer):ID du groupe" in result["schema"]

    def test_spec_with_enrichment(self):
        spec = """Outil: turn_on_light
Serveur: hue
Description: Allume une lumiere

Mots-cles: allumer allume activer active philips hue
Parametres obligatoires: light_id
Schema:
  - light_id (integer): ID de la lumiere"""

        result = parse_spec(spec)
        assert result["outil"] == "turn_on_light"
        assert result["desc"] == "Allume une lumiere"
        # Mots-cles ne doivent PAS apparaitre dans le resultat
        assert "Mots-cles" not in str(result)
        assert "allumer" not in result["desc"]

    def test_spec_with_multiple_params(self):
        spec = """Outil: set_color_rgb
Serveur: hue
Description: Change la couleur
Parametres obligatoires: light_id, r, g, b
Schema:
  - light_id (integer): ID lumiere
  - r (integer): Rouge
  - g (integer): Vert
  - b (integer): Bleu"""

        result = parse_spec(spec)
        assert result["req"] == "light_id, r, g, b"
        assert "light_id(integer):ID lumiere" in result["schema"]
        assert "r(integer):Rouge" in result["schema"]
        assert "; " in result["schema"]  # Separateur entre params

    def test_empty_spec(self):
        result = parse_spec("")
        assert result["outil"] == ""

    def test_spec_no_schema(self):
        spec = """Outil: power_on
Serveur: tv
Description: Allume la TV"""

        result = parse_spec(spec)
        assert result["outil"] == "power_on"
        assert result["schema"] == ""


class TestToonEncodeSpecs:
    """Tests pour toon_encode_specs."""

    def test_encode_single_spec(self):
        specs = ["""Outil: vm_start
Serveur: fedora
Description: Demarre une VM
Parametres obligatoires: vm_name
Schema:
  - vm_name (string): Nom de la VM"""]

        result = toon_encode_specs(specs)
        assert "[1]{outil,serveur,desc,req,opt,schema}:" in result
        assert "vm_start" in result
        assert "fedora" in result

    def test_encode_multiple_specs(self):
        specs = [
            """Outil: turn_on_group
Serveur: hue
Description: Allume les lumieres
Parametres optionnels: group_id
Schema:
  - group_id (integer): ID groupe""",
            """Outil: turn_off_group
Serveur: hue
Description: Eteint les lumieres
Parametres optionnels: group_id
Schema:
  - group_id (integer): ID groupe""",
        ]

        result = toon_encode_specs(specs)
        assert "[2]{outil,serveur,desc,req,opt,schema}:" in result
        assert "turn_on_group" in result
        assert "turn_off_group" in result

    def test_encode_strips_enrichments(self):
        specs = ["""Outil: turn_on_light
Serveur: hue
Description: Allume une lumiere

Mots-cles: allumer allume activer
Parametres obligatoires: light_id
Schema:
  - light_id (integer): ID lumiere"""]

        result = toon_encode_specs(specs)
        assert "Mots-cles" not in result
        assert "allumer allume" not in result

    def test_fallback_when_parse_fails(self):
        specs = ["just some random text without any structure"]
        result = toon_encode_specs(specs)
        # Fallback au format original
        assert result == "just some random text without any structure"

    def test_empty_specs(self):
        result = toon_encode_specs([])
        assert result == ""

    def test_token_savings(self):
        """Verifie que TOON est plus compact que le format original."""
        specs = [
            """Outil: turn_on_group
Serveur: hue
Description: Allume les lumieres

Mots-cles: allumer allume activer active philips hue lumieres lampes eclairage domotique
Parametres optionnels: group_id
Schema:
  - group_id (integer): The ID of the group to turn on""",
            """Outil: turn_off_group
Serveur: hue
Description: Eteint les lumieres

Mots-cles: eteindre eteins eteint desactiver desactive philips hue lumieres lampes eclairage domotique
Parametres optionnels: group_id
Schema:
  - group_id (integer): The ID of the group to turn off""",
            """Outil: set_group_brightness
Serveur: hue
Description: Regle la luminosite du groupe

Mots-cles: luminosite intensite baisse baisser diminue diminuer lumieres lampes groupe domotique
Parametres obligatoires: brightness
Parametres optionnels: group_id
Schema:
  - brightness (integer): Brightness level 0-254
  - group_id (integer): The group ID""",
        ]

        original = "\n---\n".join(specs)
        toon = toon_encode_specs(specs)

        # TOON doit etre plus court
        assert len(toon) < len(original)
        # Au moins 20% d'economie
        savings = 1 - len(toon) / len(original)
        assert savings > 0.20, f"Economie trop faible: {savings:.0%}"


@dataclass
class MockTurn:
    """Mock Turn pour les tests."""
    user_input: str
    assistant_response: str
    tool_call: Optional[dict] = None
    tool_result: Optional[str] = None


class TestToonEncodeHistory:
    """Tests pour toon_encode_history."""

    def test_empty_history(self):
        assert toon_encode_history([]) == ""

    def test_simple_history(self):
        turns = [
            MockTurn(user_input="salut", assistant_response="Bonjour!"),
            MockTurn(user_input="ca va", assistant_response="Bien merci"),
        ]
        result = toon_encode_history(turns)
        assert "[2]{user,assistant}:" in result
        assert "salut" in result
        assert "Bonjour!" in result

    def test_history_with_tools(self):
        turns = [
            MockTurn(
                user_input="demarre vm1",
                assistant_response="VM demarree",
                tool_call={"name": "vm_start"},
                tool_result="VM started"
            ),
        ]
        result = toon_encode_history(turns)
        assert "[1]{user,assistant,tool,result}:" in result
        assert "vm_start" in result
        assert "VM started" in result

    def test_mixed_history(self):
        turns = [
            MockTurn(user_input="salut", assistant_response="Bonjour!"),
            MockTurn(
                user_input="demarre vm1",
                assistant_response="OK",
                tool_call={"name": "vm_start"},
                tool_result="done"
            ),
        ]
        result = toon_encode_history(turns)
        # Tous doivent avoir les champs tool/result
        assert "{user,assistant,tool,result}" in result

    def test_truncates_long_responses(self):
        long_response = "x" * 500
        turns = [
            MockTurn(user_input="test", assistant_response=long_response),
        ]
        result = toon_encode_history(turns)
        # Response tronquee a 200
        assert len(result) < len(long_response)

    def test_history_compactness(self):
        """Verifie que TOON est plus compact que le format texte."""
        turns = [
            MockTurn(user_input="demarre preprod-01", assistant_response="VM preprod-01 demarree"),
            MockTurn(user_input="status", assistant_response="preprod-01: running, IP 192.168.122.10"),
            MockTurn(user_input="arrete preprod-01", assistant_response="VM preprod-01 arretee"),
        ]

        toon_result = toon_encode_history(turns)

        # Format texte classique
        text_lines = []
        for t in turns:
            text_lines.append(f"Utilisateur: {t.user_input}")
            text_lines.append(f"Assistant: {t.assistant_response}")
            text_lines.append("")
        text_result = "\n".join(text_lines)

        assert len(toon_result) < len(text_result)
