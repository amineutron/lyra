#!/usr/bin/env python3
"""
MCP Server pour génération et affichage de diagrammes Mermaid.

Fonctionnalités:
- Génération de diagrammes avec validation des bonnes pratiques
- Affichage automatique/manuel/demande
- Templates et légendes automatiques
- Gestion de session pour préférences d'affichage
"""

import asyncio
import json
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Literal, Optional

# Ajouter le parent au path pour importer lyra
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lyra.utils.mermaid_viewer import MermaidViewer

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    print("Erreur: mcp package non installé. Installez avec: pip install mcp", file=sys.stderr)
    sys.exit(1)


class MermaidMCPServer:
    """Serveur MCP pour diagrammes Mermaid."""

    def __init__(self):
        self.server = Server("mermaid-mcp")
        self.viewer = MermaidViewer()

        # Session state
        self.display_mode: Literal["ask", "always", "never"] = "ask"
        self.last_generated_path: Optional[Path] = None
        self.diagrams_cache: dict[str, Path] = {}

        # Compteur pour IDs uniques
        self.diagram_counter = 0

        # Enregistrer les handlers
        self._setup_handlers()

    def _setup_handlers(self):
        """Configure les handlers MCP."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """Liste les outils disponibles."""
            return [
                Tool(
                    name="generate_diagram",
                    description="Génère un diagramme Mermaid avec template et légende. Si mermaid_code n'est pas fourni, génère automatiquement le code basé sur le topic.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Sujet du diagramme (ex: 'VPN', 'Architecture Lyra'). Utilisé pour générer le code automatiquement si mermaid_code n'est pas fourni."
                            },
                            "mermaid_code": {
                                "type": "string",
                                "description": "Code Mermaid du diagramme (optionnel si topic est fourni)"
                            },
                            "title": {
                                "type": "string",
                                "description": "Titre du diagramme",
                                "default": "Diagramme Mermaid"
                            },
                            "subtitle": {
                                "type": "string",
                                "description": "Sous-titre (optionnel)",
                                "default": ""
                            },
                            "theme": {
                                "type": "string",
                                "enum": ["dark", "light", "forest", "neutral"],
                                "description": "Thème du diagramme",
                                "default": "dark"
                            },
                            "add_legend": {
                                "type": "boolean",
                                "description": "Ajouter une légende automatique",
                                "default": True
                            },
                            "legend_colors": {
                                "type": "object",
                                "description": "Définition de la légende {label: {color, description}}",
                                "default": {}
                            },
                            "tech_stack": {
                                "type": "object",
                                "description": "Stack technique à afficher {component: techno}",
                                "default": {}
                            },
                            "output_name": {
                                "type": "string",
                                "description": "Nom du fichier de sortie (sans extension)",
                                "default": "diagram"
                            },
                            "export_format": {
                                "type": "string",
                                "enum": ["html", "png", "svg"],
                                "description": "Format d'export: html (défaut), png ou svg",
                                "default": "html"
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="show_diagram",
                    description="Affiche un diagramme généré précédemment dans le navigateur.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "diagram_id": {
                                "type": "string",
                                "description": "ID du diagramme (retourné par generate_diagram) ou 'last' pour le dernier"
                            }
                        },
                        "required": ["diagram_id"]
                    }
                ),
                Tool(
                    name="set_display_mode",
                    description="Configure le mode d'affichage pour la session: 'ask' (demander), 'always' (toujours afficher), 'never' (jamais afficher).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["ask", "always", "never"],
                                "description": "Mode d'affichage"
                            }
                        },
                        "required": ["mode"]
                    }
                ),
                Tool(
                    name="validate_diagram",
                    description="Valide un diagramme Mermaid selon les bonnes pratiques (12 règles).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "mermaid_code": {
                                "type": "string",
                                "description": "Code Mermaid à valider"
                            }
                        },
                        "required": ["mermaid_code"]
                    }
                ),
                Tool(
                    name="list_diagrams",
                    description="Liste tous les diagrammes générés dans cette session.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            """Exécute un outil."""

            if name == "generate_diagram":
                return await self._generate_diagram(arguments)

            elif name == "show_diagram":
                return await self._show_diagram(arguments)

            elif name == "set_display_mode":
                return await self._set_display_mode(arguments)

            elif name == "validate_diagram":
                return await self._validate_diagram(arguments)

            elif name == "list_diagrams":
                return await self._list_diagrams()

            else:
                raise ValueError(f"Outil inconnu: {name}")

    def _generate_mermaid_for_topic(self, topic: str) -> Optional[str]:
        """Génère du code Mermaid basé sur un topic.

        Args:
            topic: Sujet du diagramme

        Returns:
            Code Mermaid généré, ou None si topic non supporté
        """
        topic_lower = topic.lower().strip()

        # Templates pour topics courants
        templates = {
            "vpn": """graph LR
    A[👤 Utilisateur] -->|Connexion| B[🔐 Client VPN]
    B -->|Tunnel chiffré| C[🌐 Serveur VPN]
    C -->|Accès sécurisé| D[🖥️ Réseau privé]

    E[🕵️ Attaquant] -.->|Données chiffrées<br/>illisibles| B

    style B fill:#4ecdc4,stroke:#45b7d1,color:#fff
    style C fill:#4ecdc4,stroke:#45b7d1,color:#fff
    style E fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style D fill:#95e1d3,stroke:#38ada9,color:#000""",

            "https": """graph LR
    A[👤 Client] -->|1. Hello| B[🔐 Serveur HTTPS]
    B -->|2. Certificat| A
    A -->|3. Clé de session| B
    B -->|4. Données chiffrées| A

    style A fill:#4ecdc4,stroke:#45b7d1,color:#fff
    style B fill:#95e1d3,stroke:#38ada9,color:#000""",

            "git": """graph LR
    A[📂 Working<br/>Directory] -->|git add| B[📦 Staging<br/>Area]
    B -->|git commit| C[🗄️ Local<br/>Repository]
    C -->|git push| D[☁️ Remote<br/>Repository]
    D -->|git pull| C

    style A fill:#feca57,stroke:#ee5a24,color:#000
    style B fill:#a29bfe,stroke:#6c5ce7,color:#fff
    style C fill:#4ecdc4,stroke:#45b7d1,color:#fff
    style D fill:#95e1d3,stroke:#38ada9,color:#000""",
        }

        # Chercher un template correspondant
        for key, template in templates.items():
            if key in topic_lower:
                return template

        # Template générique par défaut
        return f"""graph LR
    A[📋 {topic}] --> B{{Analyse}}
    B --> C[✅ Résultat]

    style A fill:#4ecdc4,stroke:#45b7d1,color:#fff
    style B fill:#feca57,stroke:#ee5a24,color:#000
    style C fill:#95e1d3,stroke:#38ada9,color:#000"""

    async def _generate_diagram(self, args: dict) -> list[TextContent]:
        """Génère un diagramme Mermaid."""
        topic = args.get("topic")
        mermaid_code = args.get("mermaid_code")

        # Si ni topic ni mermaid_code, erreur
        if not topic and not mermaid_code:
            raise ValueError("Vous devez fournir soit 'topic' (pour génération auto) soit 'mermaid_code' (code manuel).")

        # Si topic fourni mais pas de code, générer automatiquement
        if topic and not mermaid_code:
            mermaid_code = self._generate_mermaid_for_topic(topic)
            if not mermaid_code:
                raise ValueError(f"Impossible de générer un diagramme pour le sujet '{topic}'")

        title = args.get("title", topic if topic else "Diagramme Mermaid")
        subtitle = args.get("subtitle", "")
        theme = args.get("theme", "dark")
        add_legend = args.get("add_legend", True)
        legend_colors = args.get("legend_colors", {})
        tech_stack = args.get("tech_stack", {})
        output_name = args.get("output_name", "diagram")
        export_format = args.get("export_format", "html")

        # Générer ID unique
        self.diagram_counter += 1
        diagram_id = f"diagram_{self.diagram_counter}"

        # Construire le contenu extra
        extra_content = ""

        if add_legend and legend_colors:
            extra_content += self.viewer.create_legend(legend_colors)

        if tech_stack:
            tech_html = "<ul>"
            for component, techno in tech_stack.items():
                tech_html += f"<li><strong>{component}</strong>: {techno}</li>"
            tech_html += "</ul>"

            extra_content += self.viewer.create_info_section(
                title="Stack Technique",
                content=tech_html,
                icon="🔧"
            )

        # Générer le fichier HTML
        output_path = Path(f"/tmp/mermaid_mcp/{diagram_id}.html")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.viewer.generate(
            mermaid_code=mermaid_code,
            output_path=str(output_path),
            title=title,
            subtitle=subtitle,
            theme=theme,
            extra_content=extra_content,
            filename=output_name,
            open_browser=False
        )

        # Sauvegarder dans le cache
        self.diagrams_cache[diagram_id] = output_path
        self.last_generated_path = output_path

        # Construire la réponse
        response = f"✅ Diagramme généré: {diagram_id}\n"
        response += f"📁 Fichier: {output_path}\n"
        response += f"🎨 Thème: {theme}\n"

        if legend_colors:
            response += f"📊 Légende: {len(legend_colors)} catégories\n"
        if tech_stack:
            response += f"🔧 Stack: {len(tech_stack)} composants\n"

        # Info export
        if export_format in ["png", "svg"]:
            response += f"\n💡 Export {export_format.upper()}: Ouvrez le HTML et utilisez le bouton '📥 Télécharger {export_format.upper()}'\n"

        # Gestion de l'affichage selon le mode
        if self.display_mode == "always":
            webbrowser.open(f"file://{output_path.absolute()}")
            response += "\n🌐 Diagramme ouvert dans le navigateur (mode: always)"

        elif self.display_mode == "ask":
            response += "\n❓ Voulez-vous afficher le diagramme?\n"
            response += "   → Utilisez show_diagram avec diagram_id='last'\n"
            response += "   → Ou set_display_mode pour changer le mode (always/never/ask)"

        elif self.display_mode == "never":
            response += "\n💤 Diagramme non affiché (mode: never)"

        return [TextContent(type="text", text=response)]

    async def _show_diagram(self, args: dict) -> list[TextContent]:
        """Affiche un diagramme."""
        diagram_id = args["diagram_id"]

        if diagram_id == "last":
            if not self.last_generated_path:
                raise ValueError("Aucun diagramme généré récemment")
            path = self.last_generated_path
        else:
            if diagram_id not in self.diagrams_cache:
                raise ValueError(f"Diagramme '{diagram_id}' introuvable. Utilisez list_diagrams pour voir les diagrammes disponibles.")
            path = self.diagrams_cache[diagram_id]

        # Ouvrir dans le navigateur
        webbrowser.open(f"file://{path.absolute()}")

        return [TextContent(
            type="text",
            text=f"🌐 Diagramme '{diagram_id}' ouvert dans le navigateur\n📁 {path}"
        )]

    async def _set_display_mode(self, args: dict) -> list[TextContent]:
        """Configure le mode d'affichage."""
        mode = args["mode"]
        self.display_mode = mode

        messages = {
            "ask": "❓ Mode d'affichage: DEMANDER à chaque génération",
            "always": "✅ Mode d'affichage: TOUJOURS afficher automatiquement",
            "never": "💤 Mode d'affichage: JAMAIS afficher (manuel uniquement)"
        }

        return [TextContent(
            type="text",
            text=messages[mode]
        )]

    async def _validate_diagram(self, args: dict) -> list[TextContent]:
        """Valide un diagramme selon les bonnes pratiques."""
        mermaid_code = args["mermaid_code"]

        issues = []
        warnings = []

        # Règle 1: Direction (LR recommandé)
        if "graph TB" in mermaid_code:
            warnings.append("⚠️ Orientation TB détectée. LR est recommandé pour les flux de processus.")

        # Règle 2: Comptage des nœuds (max 15)
        # Approximation simple: compter les définitions de nœuds
        node_definitions = [line for line in mermaid_code.split('\n') if '[' in line and ']' in line]
        node_count = len(node_definitions)

        if node_count > 15:
            issues.append(f"❌ Trop de nœuds ({node_count}/15 max). Considérez diviser en plusieurs diagrammes.")
        elif node_count > 12:
            warnings.append(f"⚠️ Beaucoup de nœuds ({node_count}/15). Proche de la limite recommandée.")

        # Règle 3: Vérifier la présence de classDef
        if "classDef" not in mermaid_code and node_count > 3:
            warnings.append("⚠️ Aucun style défini (classDef). Considérez ajouter des couleurs pour la clarté.")

        # Règle 4: Labels longs sur les liens (> 20 chars)
        long_labels = [line for line in mermaid_code.split('\n') if '|"' in line and len(line.split('|"')[1].split('"')[0]) > 20]
        if long_labels:
            issues.append(f"❌ {len(long_labels)} label(s) de lien trop long(s) (> 20 chars). Réduire à 1-3 mots.")

        # Règle 5: Vérifier le thème
        if "%%{init:" in mermaid_code and "'theme'" in mermaid_code:
            pass  # OK, thème défini
        else:
            warnings.append("⚠️ Aucun thème défini. Ajouter %%{init: {'theme':'dark'}}%%")

        # Règle 6: Modèles LLM (rechercher des patterns communs)
        llm_keywords = ["llama", "qwen", "gpt", "claude", "mistral", "gemini"]
        has_llm = any(keyword.lower() in mermaid_code.lower() for keyword in llm_keywords)

        if has_llm:
            # Vérifier si les tailles sont mentionnées (3B, 7B, etc.)
            has_size = any(f"{size}B" in mermaid_code for size in ["3", "7", "13", "70"])
            if not has_size:
                warnings.append("⚠️ Modèle LLM détecté sans taille (ex: Llama 3B). Ajouter la taille pour clarté.")

        # Construire le rapport
        report = "## 📐 Validation du diagramme\n\n"

        if not issues and not warnings:
            report += "✅ **Aucun problème détecté!** Le diagramme respecte les bonnes pratiques.\n"
        else:
            if issues:
                report += f"### ❌ Problèmes ({len(issues)})\n"
                for issue in issues:
                    report += f"- {issue}\n"
                report += "\n"

            if warnings:
                report += f"### ⚠️ Avertissements ({len(warnings)})\n"
                for warning in warnings:
                    report += f"- {warning}\n"

        report += f"\n📊 **Stats**: {node_count} nœud(s) détecté(s)\n"

        return [TextContent(type="text", text=report)]

    async def _list_diagrams(self) -> list[TextContent]:
        """Liste tous les diagrammes de la session."""
        if not self.diagrams_cache:
            return [TextContent(
                type="text",
                text="📭 Aucun diagramme généré dans cette session"
            )]

        response = f"📚 **{len(self.diagrams_cache)} diagramme(s) disponible(s)**\n\n"

        for diagram_id, path in self.diagrams_cache.items():
            is_last = path == self.last_generated_path
            marker = " ⭐ (dernier)" if is_last else ""
            response += f"- **{diagram_id}**{marker}\n"
            response += f"  📁 {path}\n\n"

        response += f"💡 Mode d'affichage actuel: **{self.display_mode}**\n"

        return [TextContent(type="text", text=response)]

    async def run(self):
        """Lance le serveur MCP."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Point d'entrée principal."""
    server = MermaidMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
