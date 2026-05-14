#!/usr/bin/env python3
"""
Generateur PDF du rapport de campagne de tests MCP.
Utilise fpdf2.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

from fpdf import FPDF
from datetime import datetime


REPORT_PATH = os.path.join(os.path.dirname(__file__), 'test_campaign_report.txt')
PDF_PATH = os.path.join(os.path.dirname(__file__), 'test_campaign_report.pdf')


STATUS_COLORS = {
    'PASS':      (34, 139, 34),   # vert
    'PARTIAL':   (255, 165, 0),   # orange
    'RULE_MISS': (100, 149, 237), # bleu
    'FAIL':      (220, 20, 60),   # rouge
}

CATEGORY_COLORS = {
    'FEDORA':  (70, 130, 180),
    'BACKUP':  (60, 179, 113),
    'DENON':   (147, 112, 219),
    'TV':      (255, 140, 0),
    'HUE':     (255, 215, 0),
    'CATT':    (32, 178, 170),
    'EDGE':    (128, 128, 128),
}


def parse_report(path):
    """Parse le rapport texte et retourne une structure."""
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    tests = []
    scores = {}
    current = None
    section = None

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Section
        if line.startswith('=== ') and line.endswith(' ==='):
            section = line.strip('= ').strip()
            i += 1
            continue

        # Debut d'un test
        if line.startswith('[') and ']' in line:
            status_end = line.index(']')
            status = line[1:status_end].strip()
            desc = line[status_end+1:].strip()

            current = {
                'status': status,
                'desc': desc,
                'category': section,
                'query': '',
                'expected': '',
                'obtained': '',
                'args': '',
                'bug': '',
            }
            tests.append(current)
            i += 1
            continue

        if current is not None:
            if line.startswith('  Requete'):
                current['query'] = line.split(':', 1)[1].strip().strip('"')
            elif line.startswith('  Attendu'):
                current['expected'] = line.split(':', 1)[1].strip()
            elif line.startswith('  Obtenu'):
                current['obtained'] = line.split(':', 1)[1].strip()
            elif line.startswith('  Args'):
                current['args'] = line.split(':', 1)[1].strip()
            elif line.startswith('  BUG'):
                current['bug'] = line.split(':', 1)[1].strip()

        # Scores par categorie
        if line.startswith('  ') and ':' in line and 'PASS' in line and 'FAIL' in line and '//' not in line:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                cat = parts[0].strip()
                rest = parts[1].strip()
                # parse: "23 PASS  11 PARTIAL  0 RULE_MISS  1 FAIL  / 35 tests  [81%]"
                try:
                    import re
                    m = re.match(
                        r'(\d+) PASS\s+(\d+) PARTIAL\s+(\d+) RULE_MISS\s+(\d+) FAIL\s+/\s+(\d+) tests\s+\[(\d+)%\]',
                        rest
                    )
                    if m:
                        scores[cat] = {
                            'pass': int(m.group(1)),
                            'partial': int(m.group(2)),
                            'rule_miss': int(m.group(3)),
                            'fail': int(m.group(4)),
                            'total': int(m.group(5)),
                            'pct': int(m.group(6)),
                        }
                except Exception:
                    pass

        i += 1

    return tests, scores


def score_color(pct):
    if pct >= 80:
        return (34, 139, 34)
    elif pct >= 60:
        return (255, 165, 0)
    else:
        return (220, 20, 60)


class PDF(FPDF):
    def header(self):
        # Bandeau superieur
        self.set_fill_color(30, 30, 50)
        self.rect(0, 0, 210, 14, 'F')
        self.set_text_color(200, 200, 255)
        self.set_font('Helvetica', 'B', 10)
        self.set_xy(10, 3)
        self.cell(0, 8, 'Lyra RAG v2 - Campagne de Tests MCP', ln=0, align='L')
        self.set_xy(0, 3)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(150, 150, 200)
        self.cell(200, 8, f'Genere le {datetime.now().strftime("%d/%m/%Y %H:%M")}', ln=0, align='R')
        self.set_text_color(0, 0, 0)
        self.set_y(16)

    def footer(self):
        self.set_y(-12)
        self.set_fill_color(30, 30, 50)
        self.rect(0, self.get_y(), 210, 12, 'F')
        self.set_text_color(150, 150, 200)
        self.set_font('Helvetica', '', 8)
        self.cell(0, 12, f'Page {self.page_no()} / {{nb}}', align='C')
        self.set_text_color(0, 0, 0)

    def chapter_title(self, title, color=(30, 30, 80)):
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 8, f'  {title}', ln=True, fill=True)
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def status_badge(self, status, x, y, w=28, h=6):
        color = STATUS_COLORS.get(status, (128, 128, 128))
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 7)
        self.set_xy(x, y)
        self.cell(w, h, status, align='C', fill=True, border=0)
        self.set_text_color(0, 0, 0)

    def score_bar(self, label, pct, total, pass_n, partial_n, rule_miss_n, fail_n, color):
        bar_w = 130
        bar_h = 6
        x0 = 10
        y0 = self.get_y()

        # Label categorie
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 8)
        self.set_xy(x0, y0)
        self.cell(30, bar_h, f'  {label}', fill=True, border=0)
        self.set_text_color(0, 0, 0)

        # Barre proportionnelle
        x_bar = x0 + 32
        segments = [
            (pass_n, STATUS_COLORS['PASS']),
            (partial_n, STATUS_COLORS['PARTIAL']),
            (rule_miss_n, STATUS_COLORS['RULE_MISS']),
            (fail_n, STATUS_COLORS['FAIL']),
        ]
        x_cur = x_bar
        for count, col in segments:
            if count > 0:
                w = bar_w * count / total
                self.set_fill_color(*col)
                self.rect(x_cur, y0, w, bar_h, 'F')
                x_cur += w

        # Contour barre
        self.set_draw_color(180, 180, 180)
        self.rect(x_bar, y0, bar_w, bar_h)

        # Score %
        sc_col = score_color(pct)
        self.set_text_color(*sc_col)
        self.set_font('Helvetica', 'B', 9)
        self.set_xy(x_bar + bar_w + 3, y0)
        self.cell(20, bar_h, f'{pct}%', align='L')

        # Compteurs
        self.set_text_color(80, 80, 80)
        self.set_font('Helvetica', '', 7)
        self.set_xy(x_bar + bar_w + 24, y0)
        self.cell(0, bar_h, f'{pass_n}P  {partial_n}Pa  {rule_miss_n}R  {fail_n}F / {total}')

        self.set_text_color(0, 0, 0)
        self.ln(bar_h + 2)

    def test_row(self, test, row_num):
        status = test['status']
        bg = (252, 252, 255) if row_num % 2 == 0 else (245, 245, 250)

        # Fond leger selon status
        if status == 'FAIL':
            bg = (255, 240, 240)
        elif status == 'RULE_MISS':
            bg = (240, 245, 255)

        y0 = self.get_y()
        row_h = 18

        # Fond
        self.set_fill_color(*bg)
        self.rect(10, y0, 190, row_h, 'F')

        # Ligne de separation
        self.set_draw_color(220, 220, 230)
        self.line(10, y0, 200, y0)

        # Badge status
        self.status_badge(status, 10, y0 + 1, w=24, h=6)

        # Description
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(30, 30, 60)
        self.set_xy(36, y0 + 1)
        desc = test['desc']
        if len(desc) > 45:
            desc = desc[:42] + '...'
        self.cell(70, 6, desc, ln=0)

        # Outil attendu/obtenu
        self.set_font('Helvetica', '', 7)
        self.set_text_color(80, 80, 80)
        self.set_xy(108, y0 + 1)
        expected = test['expected'].replace('fedora.', '').replace('catt.', '').replace('hue.', '').replace('denon.', '').replace('tv.', '')
        if len(expected) > 25:
            expected = expected[:22] + '...'
        self.cell(50, 6, f'attendu: {expected}', ln=0)

        # Requete
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(100, 100, 100)
        self.set_xy(36, y0 + 8)
        query = f'"{test["query"]}"'
        if len(query) > 80:
            query = query[:77] + '..."'
        self.cell(155, 5, query, ln=0)

        # Args
        if test['args'] and test['args'] != '{}':
            self.set_font('Helvetica', '', 6)
            self.set_text_color(120, 120, 140)
            self.set_xy(36, y0 + 13)
            args_str = test['args']
            if len(args_str) > 80:
                args_str = args_str[:77] + '...'
            self.cell(155, 5, args_str, ln=0)

        # Bug note
        if test.get('bug'):
            self.set_font('Helvetica', 'B', 6)
            self.set_text_color(200, 40, 40)
            self.set_xy(108, y0 + 8)
            bug_str = test['bug']
            if len(bug_str) > 50:
                bug_str = bug_str[:47] + '...'
            self.cell(80, 5, f'BUG: {bug_str}', ln=0)

        self.set_text_color(0, 0, 0)
        self.set_xy(10, y0 + row_h)


def generate_pdf(tests, scores):
    pdf = PDF(orientation='P', unit='mm', format='A4')
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(10, 16, 10)

    # === PAGE DE GARDE ===
    pdf.add_page()

    # Titre principal
    pdf.set_y(35)
    pdf.set_fill_color(20, 20, 50)
    pdf.rect(10, 30, 190, 40, 'F')

    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_xy(10, 38)
    pdf.cell(190, 12, 'Campagne de Tests MCP', align='C', ln=True)
    pdf.set_font('Helvetica', '', 13)
    pdf.set_xy(10, 53)
    pdf.cell(190, 8, 'Lyra RAG v2 - Pipeline _rule_based_detect()', align='C', ln=True)
    pdf.set_text_color(0, 0, 0)

    # Date et version
    pdf.set_y(80)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f'Date : {datetime.now().strftime("%d %B %Y")}', align='C', ln=True)
    pdf.cell(0, 6, 'Environnement : Pipeline Lyra sans execution MCP reelle', align='C', ln=True)
    pdf.set_text_color(0, 0, 0)

    # Score global
    total = sum(s['total'] for s in scores.values())
    pass_n = sum(s['pass'] for s in scores.values())
    partial_n = sum(s['partial'] for s in scores.values())
    rule_miss_n = sum(s['rule_miss'] for s in scores.values())
    fail_n = sum(s['fail'] for s in scores.values())
    pct = round(100 * pass_n / total) if total else 0

    pdf.set_y(100)
    pdf.set_fill_color(240, 240, 250)
    pdf.rect(30, pdf.get_y(), 150, 55, 'F')
    pdf.set_draw_color(100, 100, 180)
    pdf.rect(30, pdf.get_y(), 150, 55)

    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(30, 30, 80)
    pdf.set_xy(30, pdf.get_y() + 5)
    pdf.cell(150, 8, 'SCORE GLOBAL', align='C', ln=True)

    sc_col = score_color(pct)
    pdf.set_text_color(*sc_col)
    pdf.set_font('Helvetica', 'B', 36)
    pdf.set_xy(30, pdf.get_y())
    pdf.cell(150, 20, f'{pct}%', align='C', ln=True)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(50, 50, 50)
    pdf.set_xy(30, pdf.get_y())
    pdf.cell(150, 6, f'{total} tests au total', align='C', ln=True)

    # Compteurs status
    y_cnt = pdf.get_y() + 2
    items = [
        ('PASS', pass_n, STATUS_COLORS['PASS']),
        ('PARTIAL', partial_n, STATUS_COLORS['PARTIAL']),
        ('RULE_MISS', rule_miss_n, STATUS_COLORS['RULE_MISS']),
        ('FAIL', fail_n, STATUS_COLORS['FAIL']),
    ]
    x_start = 35
    for label, count, color in items:
        pdf.set_fill_color(*color)
        pdf.rect(x_start, y_cnt, 32, 10, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_xy(x_start, y_cnt)
        pdf.cell(32, 5, label, align='C', ln=False)
        pdf.set_xy(x_start, y_cnt + 5)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(32, 5, str(count), align='C', ln=False)
        x_start += 35

    pdf.set_text_color(0, 0, 0)

    # Legende
    pdf.set_y(170)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(30, 30, 80)
    pdf.cell(0, 6, 'Legende des statuts', ln=True)
    pdf.set_y(pdf.get_y() + 1)

    legend = [
        ('PASS',      'Outil correct + tous les arguments attendus detectes', STATUS_COLORS['PASS']),
        ('PARTIAL',   'Outil correct + args obligatoires OK + args optionnels manquants', STATUS_COLORS['PARTIAL']),
        ('RULE_MISS', 'Aucune regle statique ne matche - traite par EPHAISTOS (LLM) en production', STATUS_COLORS['RULE_MISS']),
        ('FAIL',      'Mauvais outil detecte ou argument obligatoire manquant - BUG reel', STATUS_COLORS['FAIL']),
    ]
    for status, desc, color in legend:
        y_l = pdf.get_y()
        pdf.set_fill_color(*color)
        pdf.rect(15, y_l, 22, 6, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 7)
        pdf.set_xy(15, y_l)
        pdf.cell(22, 6, status, align='C')
        pdf.set_text_color(50, 50, 50)
        pdf.set_font('Helvetica', '', 8)
        pdf.set_xy(40, y_l)
        pdf.cell(0, 6, desc, ln=True)

    pdf.set_text_color(0, 0, 0)

    # Analyse narrative
    pdf.set_y(220)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(30, 30, 80)
    pdf.cell(0, 6, 'Analyse', ln=True)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(60, 60, 60)
    analysis = [
        "Les RULE_MISS correspondent aux outils TV, HUE complexes (brightness/color/scene),",
        "CATT (cast_play/pause/stop...) qui ne sont pas couverts par _rule_based_detect.",
        "Ces requetes sont traitees par EPHAISTOS (LLM Qwen 7B) en production - comportement attendu.",
        "",
        "Les PARTIAL indiquent que l'outil est correctement identifie mais que les arguments",
        "optionnels mentionnes dans la requete ne sont pas extraits par les regles statiques.",
        "Ex: 'vm_stop avec timeout 120' -> vm_stop(vm_name=X) sans timeout=120.",
        "",
        "Les 8 FAIL sont des bugs reels dans _rule_based_detect a corriger:",
        "- Mots-cles 'force'/'detaille'/'live' captures comme vm_name par le regex",
        "- 'lance commande' -> vm_start au lieu de vm_exec (collision 'lance')",
        "- 'sourdine' -> power_on au lieu de denon.mute_on",
        "- 'lance la scene' -> vm_start (collision 'lance')",
        "- 'backup + verifie' -> backup_verify au lieu de backup_create",
    ]
    for line in analysis:
        pdf.cell(0, 4.5, line, ln=True)

    pdf.set_text_color(0, 0, 0)

    # === PAGE SCORES PAR CATEGORIE ===
    pdf.add_page()
    pdf.chapter_title('Scores par Categorie', color=(30, 30, 80))

    pdf.ln(2)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(80, 80, 80)
    # Legende mini-barre
    x_leg = 10
    y_leg = pdf.get_y()
    for label, color in [('PASS', STATUS_COLORS['PASS']), ('PARTIAL', STATUS_COLORS['PARTIAL']),
                          ('RULE_MISS', STATUS_COLORS['RULE_MISS']), ('FAIL', STATUS_COLORS['FAIL'])]:
        pdf.set_fill_color(*color)
        pdf.rect(x_leg, y_leg, 8, 4, 'F')
        pdf.set_xy(x_leg + 9, y_leg)
        pdf.cell(20, 4, label)
        x_leg += 38
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    # Barres par categorie
    ordered = sorted(scores.items(), key=lambda x: -x[1]['pct'])
    for cat, s in ordered:
        color = CATEGORY_COLORS.get(cat, (100, 100, 100))
        pdf.score_bar(
            cat, s['pct'], s['total'],
            s['pass'], s['partial'], s['rule_miss'], s['fail'],
            color
        )
        pdf.ln(1)

    # Graphique synthese (grille simple)
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(30, 30, 80)
    pdf.cell(0, 6, 'Distribution globale des resultats', ln=True)
    pdf.ln(2)

    # Grand barre globale
    bar_w = 180
    y0 = pdf.get_y()
    x0 = 10
    total_all = pass_n + partial_n + rule_miss_n + fail_n
    segs = [(pass_n, 'PASS'), (partial_n, 'PARTIAL'), (rule_miss_n, 'RULE_MISS'), (fail_n, 'FAIL')]
    x_cur = x0
    for count, status in segs:
        w = bar_w * count / total_all if total_all else 0
        color = STATUS_COLORS[status]
        pdf.set_fill_color(*color)
        pdf.rect(x_cur, y0, w, 12, 'F')
        if w > 12:
            pdf.set_text_color(255, 255, 255)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_xy(x_cur, y0 + 3)
            pct_seg = round(100 * count / total_all)
            pdf.cell(w, 6, f'{pct_seg}%', align='C')
        x_cur += w

    pdf.set_draw_color(100, 100, 100)
    pdf.rect(x0, y0, bar_w, 12)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(18)

    # Tableau recap
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(30, 30, 80)
    pdf.set_text_color(255, 255, 255)
    cols = ['Categorie', 'PASS', 'PARTIAL', 'RULE_MISS', 'FAIL', 'Total', 'Score']
    widths = [35, 22, 22, 28, 20, 22, 22]
    for col, w in zip(cols, widths):
        pdf.cell(w, 6, col, align='C', fill=True, border=1)
    pdf.ln()

    for i, (cat, s) in enumerate(sorted(scores.items())):
        bg = (248, 248, 255) if i % 2 == 0 else (235, 235, 248)
        pdf.set_fill_color(*bg)
        pdf.set_text_color(30, 30, 60)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(widths[0], 6, cat, fill=True, border=1)
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(34, 139, 34)
        pdf.cell(widths[1], 6, str(s['pass']), align='C', fill=True, border=1)
        pdf.set_text_color(255, 165, 0)
        pdf.cell(widths[2], 6, str(s['partial']), align='C', fill=True, border=1)
        pdf.set_text_color(100, 149, 237)
        pdf.cell(widths[3], 6, str(s['rule_miss']), align='C', fill=True, border=1)
        pdf.set_text_color(220, 20, 60)
        pdf.cell(widths[4], 6, str(s['fail']), align='C', fill=True, border=1)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(widths[5], 6, str(s['total']), align='C', fill=True, border=1)
        sc_c = score_color(s['pct'])
        pdf.set_text_color(*sc_c)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(widths[6], 6, f"{s['pct']}%", align='C', fill=True, border=1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln()

    # Ligne TOTAL
    pdf.set_fill_color(20, 20, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.cell(widths[0], 6, 'TOTAL', fill=True, border=1)
    pdf.set_text_color(180, 255, 180)
    pdf.cell(widths[1], 6, str(pass_n), align='C', fill=True, border=1)
    pdf.set_text_color(255, 220, 150)
    pdf.cell(widths[2], 6, str(partial_n), align='C', fill=True, border=1)
    pdf.set_text_color(180, 200, 255)
    pdf.cell(widths[3], 6, str(rule_miss_n), align='C', fill=True, border=1)
    pdf.set_text_color(255, 150, 150)
    pdf.cell(widths[4], 6, str(fail_n), align='C', fill=True, border=1)
    pdf.set_text_color(220, 220, 220)
    pdf.cell(widths[5], 6, str(total), align='C', fill=True, border=1)
    sc_c = score_color(pct)
    pdf.set_text_color(*[min(255, c + 80) for c in sc_c])
    pdf.cell(widths[6], 6, f'{pct}%', align='C', fill=True, border=1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln()

    # === PAGES TESTS DETAILLES PAR CATEGORIE ===
    categories_order = ['FEDORA', 'BACKUP', 'DENON', 'TV', 'HUE', 'CATT', 'EDGE']

    for cat in categories_order:
        cat_tests = [t for t in tests if t.get('category') == cat]
        if not cat_tests:
            continue

        pdf.add_page()
        color = CATEGORY_COLORS.get(cat, (80, 80, 80))
        pdf.chapter_title(f'Tests {cat} ({len(cat_tests)} tests)', color=color)

        # Mini-stats
        cat_pass = sum(1 for t in cat_tests if t['status'] == 'PASS')
        cat_partial = sum(1 for t in cat_tests if t['status'] == 'PARTIAL')
        cat_rule_miss = sum(1 for t in cat_tests if t['status'] == 'RULE_MISS')
        cat_fail = sum(1 for t in cat_tests if t['status'] == 'FAIL')
        cat_score = scores.get(cat, {}).get('pct', 0)

        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(80, 80, 80)
        stats_line = (
            f'PASS: {cat_pass}  |  PARTIAL: {cat_partial}  |  '
            f'RULE_MISS: {cat_rule_miss}  |  FAIL: {cat_fail}  |  Score: {cat_score}%'
        )
        pdf.cell(0, 5, stats_line, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # En-tete colonnes
        pdf.set_fill_color(*[min(255, c + 80) for c in color])
        pdf.set_text_color(30, 30, 60)
        pdf.set_font('Helvetica', 'B', 7)
        pdf.cell(26, 5, 'Statut', fill=True, border=0, align='C')
        pdf.cell(72, 5, 'Description / Requete', fill=True, border=0)
        pdf.cell(52, 5, 'Outil / Bug', fill=True, border=0)
        pdf.cell(38, 5, 'Args extraits', fill=True, border=0)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

        for row_num, test in enumerate(cat_tests):
            if pdf.get_y() > 270:
                pdf.add_page()
                pdf.chapter_title(f'Tests {cat} (suite)', color=color)
                pdf.ln(2)

            pdf.test_row(test, row_num)

    # === PAGE BUGS ===
    fail_tests = [t for t in tests if t['status'] == 'FAIL']
    if fail_tests:
        pdf.add_page()
        pdf.chapter_title('Bugs Detectes (FAIL)', color=(180, 20, 20))

        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(80, 20, 20)
        pdf.cell(0, 5, f'{len(fail_tests)} bugs reels identifies dans _rule_based_detect() a corriger.', ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

        for i, test in enumerate(fail_tests, 1):
            y0 = pdf.get_y()

            # Numero + fond
            pdf.set_fill_color(255, 235, 235)
            pdf.rect(10, y0, 190, 26, 'F')
            pdf.set_draw_color(220, 50, 50)
            pdf.rect(10, y0, 190, 26)

            # Numero
            pdf.set_fill_color(220, 20, 60)
            pdf.rect(10, y0, 10, 26, 'F')
            pdf.set_text_color(255, 255, 255)
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_xy(10, y0 + 9)
            pdf.cell(10, 8, str(i), align='C')

            # Details
            pdf.set_text_color(30, 30, 30)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_xy(22, y0 + 2)
            pdf.cell(0, 5, f'[{test["category"]}] {test["desc"]}', ln=True)

            pdf.set_font('Helvetica', 'I', 7)
            pdf.set_text_color(80, 80, 80)
            pdf.set_xy(22, y0 + 8)
            pdf.cell(0, 4, f'Requete : "{test["query"]}"', ln=True)

            pdf.set_font('Helvetica', '', 7)
            pdf.set_xy(22, y0 + 13)
            pdf.set_text_color(150, 0, 0)
            pdf.cell(45, 4, f'Attendu : {test["expected"]}', ln=False)
            pdf.set_text_color(200, 50, 0)
            pdf.cell(45, 4, f'Obtenu : {test["obtained"]}', ln=False)

            if test.get('bug'):
                pdf.set_text_color(180, 0, 0)
                pdf.set_font('Helvetica', 'B', 7)
                pdf.set_xy(22, y0 + 19)
                pdf.cell(0, 4, f'Cause : {test["bug"]}', ln=True)

            pdf.set_text_color(0, 0, 0)
            pdf.set_xy(10, y0 + 28)

    pdf.output(PDF_PATH)
    print(f'PDF genere : {PDF_PATH}')
    return PDF_PATH


if __name__ == '__main__':
    tests, scores = parse_report(REPORT_PATH)
    print(f'Tests charges : {len(tests)}')
    print(f'Categories : {list(scores.keys())}')
    generate_pdf(tests, scores)
