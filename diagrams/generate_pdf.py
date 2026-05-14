#!/usr/bin/env python3
"""
Génère un PDF à partir du HTML avec rendu JavaScript (Mermaid)
Format A4 paysage pour meilleure lisibilité des diagrammes
"""
import asyncio
from playwright.async_api import async_playwright
import sys

async def generate_pdf(html_path: str, pdf_path: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Viewport large comme un écran plein (1920x1080)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        # Charger la page HTML
        await page.goto(f'file://{html_path}')

        # Attendre que Mermaid ait fini de rendre les diagrammes
        # On attend que tous les SVG soient générés
        await page.wait_for_timeout(3000)  # 3 secondes pour le rendu Mermaid

        # Générer le PDF en format A4 portrait
        await page.pdf(
            path=pdf_path,
            format='A4',
            landscape=False,  # Portrait (vertical)
            print_background=True,  # Inclure les couleurs de fond
            margin={
                'top': '10mm',
                'right': '10mm',
                'bottom': '10mm',
                'left': '10mm'
            },
            scale=0.8  # Légèrement réduit pour mieux tenir en A4 portrait
        )

        await browser.close()
        print(f"✅ PDF généré avec succès: {pdf_path}")

if __name__ == "__main__":
    html_file = "/home/amineutron/dev/lyra/diagrams/mcp-fedora-tools-reference.html"
    pdf_file = "/home/amineutron/dev/lyra/diagrams/mcp-fedora-reference-complete.pdf"

    if len(sys.argv) > 1:
        html_file = sys.argv[1]
    if len(sys.argv) > 2:
        pdf_file = sys.argv[2]

    asyncio.run(generate_pdf(html_file, pdf_file))
