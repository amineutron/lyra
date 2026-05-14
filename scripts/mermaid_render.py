#!/usr/bin/env python3
"""
CLI pour générer des visualiseurs HTML Mermaid.

Usage:
    python scripts/mermaid_render.py diagram.mmd -o output.html
    python scripts/mermaid_render.py diagram.mmd --title "Mon Diagramme" --open
"""

import argparse
import sys
from pathlib import Path

# Ajouter le parent au path pour importer lyra
sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.utils.mermaid_viewer import MermaidViewer


def main():
    parser = argparse.ArgumentParser(
        description="Génère un visualiseur HTML pour diagrammes Mermaid"
    )

    parser.add_argument(
        "input",
        help="Fichier Mermaid (.mmd) ou code inline"
    )

    parser.add_argument(
        "-o", "--output",
        default="output.html",
        help="Fichier HTML de sortie (défaut: output.html)"
    )

    parser.add_argument(
        "-t", "--title",
        default="Diagramme Mermaid",
        help="Titre de la page"
    )

    parser.add_argument(
        "-s", "--subtitle",
        default="",
        help="Sous-titre"
    )

    parser.add_argument(
        "--theme",
        default="dark",
        choices=["dark", "light", "forest", "neutral"],
        help="Thème Mermaid (défaut: dark)"
    )

    parser.add_argument(
        "--open",
        action="store_true",
        help="Ouvrir automatiquement dans le navigateur"
    )

    args = parser.parse_args()

    # Lire le code Mermaid
    input_path = Path(args.input)
    if input_path.exists() and input_path.suffix in [".mmd", ".mermaid", ".txt"]:
        with open(input_path, 'r', encoding='utf-8') as f:
            mermaid_code = f.read()
        filename = input_path.stem
    else:
        # Code inline
        mermaid_code = args.input
        filename = "diagram"

    # Générer le HTML
    viewer = MermaidViewer()

    try:
        output = viewer.generate(
            mermaid_code=mermaid_code,
            output_path=args.output,
            title=args.title,
            subtitle=args.subtitle,
            theme=args.theme,
            filename=filename,
            open_browser=args.open
        )

        print(f"✅ Succès ! Fichier généré: {output}")

        if not args.open:
            print(f"📖 Ouvre avec: firefox {output}")

    except Exception as e:
        print(f"❌ Erreur: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
