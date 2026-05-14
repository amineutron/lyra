#!/usr/bin/env python3
"""
Générateur de visualiseur HTML pour diagrammes Mermaid.
Utilise un template pour créer des pages HTML interactives.
"""

import os
import webbrowser
from pathlib import Path
from typing import Optional


class MermaidViewer:
    """Générateur de visualiseur HTML pour diagrammes Mermaid."""

    def __init__(self, template_path: Optional[str] = None):
        """
        Initialise le viewer avec un template.

        Args:
            template_path: Chemin vers le template HTML (optionnel)
        """
        if template_path is None:
            # Template par défaut dans docs/
            template_path = Path(__file__).parent.parent.parent / "docs" / "mermaid_template.html"

        self.template_path = Path(template_path)

        if not self.template_path.exists():
            raise FileNotFoundError(f"Template non trouvé: {self.template_path}")

        with open(self.template_path, 'r', encoding='utf-8') as f:
            self.template = f.read()

    def generate(
        self,
        mermaid_code: str,
        output_path: str,
        title: str = "Diagramme Mermaid",
        subtitle: str = "",
        theme: str = "dark",
        extra_content: str = "",
        filename: str = "diagram",
        open_browser: bool = False
    ) -> Path:
        """
        Génère un fichier HTML à partir du code Mermaid.

        Args:
            mermaid_code: Code du diagramme Mermaid
            output_path: Chemin de sortie du fichier HTML
            title: Titre de la page
            subtitle: Sous-titre (optionnel)
            theme: Thème Mermaid (dark/light/forest/etc)
            extra_content: Contenu HTML additionnel (légende, infos, etc)
            filename: Nom de base pour les exports (SVG/PNG)
            open_browser: Ouvrir automatiquement dans le navigateur

        Returns:
            Path: Chemin du fichier généré
        """
        # Remplacer les placeholders
        html = self.template.replace("{{TITLE}}", title)
        html = html.replace("{{SUBTITLE}}", subtitle)
        html = html.replace("{{THEME}}", theme)
        html = html.replace("{{MERMAID_CODE}}", mermaid_code)
        html = html.replace("{{EXTRA_CONTENT}}", extra_content)
        html = html.replace("{{FILENAME}}", filename)

        # Écrire le fichier
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"✅ Diagramme généré: {output_path}")

        # Ouvrir dans le navigateur si demandé
        if open_browser:
            webbrowser.open(f"file://{output_path.absolute()}")

        return output_path

    @staticmethod
    def create_legend(colors: dict[str, dict[str, str]]) -> str:
        """
        Crée une section légende HTML à partir d'un dictionnaire de couleurs.

        Args:
            colors: Dict {label: {"color": "#hex", "description": "..."}}

        Returns:
            HTML de la légende

        Example:
            colors = {
                "Input": {"color": "#ff6b6b", "description": "User, Whisper STT"},
                "Intent": {"color": "#4ecdc4", "description": "Classifier (Llama 3B)"}
            }
        """
        legend_html = '''
        <div class="info">
            <h2>📊 Légende des composants</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
        '''

        for label, data in colors.items():
            color = data.get("color", "#ccc")
            description = data.get("description", "")

            legend_html += f'''
                <div style="padding: 10px; border-radius: 5px; background: {color}33; display: flex; align-items: center; gap: 10px;">
                    <div style="width: 30px; height: 30px; border-radius: 4px; background: {color}; border: 2px solid #fff;"></div>
                    <div>
                        <strong>{label}</strong><br/>
                        <span style="font-size: 0.9em;">{description}</span>
                    </div>
                </div>
            '''

        legend_html += '''
            </div>
        </div>
        '''

        return legend_html

    @staticmethod
    def create_info_section(title: str, content: str, icon: str = "ℹ️") -> str:
        """
        Crée une section d'information HTML.

        Args:
            title: Titre de la section
            content: Contenu HTML
            icon: Emoji ou icône

        Returns:
            HTML de la section
        """
        return f'''
        <div class="info">
            <h2>{icon} {title}</h2>
            {content}
        </div>
        '''


def main():
    """Exemple d'utilisation."""
    viewer = MermaidViewer()

    # Exemple simple
    mermaid_code = """
graph LR
    A[User] --> B[Intent]
    B --> C[LYRA]
    B --> D[EPHAISTOS]
    D --> E[MCP]
    C --> F[Response]
    E --> F
    """

    # Créer une légende
    colors = {
        "User": {"color": "#ff6b6b", "description": "Utilisateur"},
        "Intent": {"color": "#4ecdc4", "description": "Classification"},
        "LYRA": {"color": "#95e1d3", "description": "Dialogue"},
        "EPHAISTOS": {"color": "#feca57", "description": "Analyse"},
        "MCP": {"color": "#a29bfe", "description": "Serveurs"}
    }

    legend = viewer.create_legend(colors)

    info = viewer.create_info_section(
        "À propos",
        "<p>Ceci est un exemple de diagramme Mermaid généré automatiquement.</p>",
        "📝"
    )

    extra_content = legend + info

    # Générer
    viewer.generate(
        mermaid_code=mermaid_code,
        output_path="docs/exemple_mermaid.html",
        title="Exemple Mermaid",
        subtitle="Généré automatiquement",
        extra_content=extra_content,
        filename="exemple",
        open_browser=True
    )


if __name__ == "__main__":
    main()
