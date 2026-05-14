"""
Lyra Intro - Partie 4 : Activation finale
Concept : 6 modules s'allument un par un, envoient un flux vers le centre,
LYRA emerge de la convergence de tous les flux.
Rendu : manim -pqh part4_activation.py LyraActivation
"""
from manim import *
import numpy as np


class LyraActivation(Scene):
    def construct(self):
        np.random.seed(7)

        BLUE   = ManimColor("#00D4FF")
        BLUE2  = ManimColor("#005577")
        WHITE  = ManimColor("#E8F4FF")
        DARK   = ManimColor("#000D1A")
        DIM    = ManimColor("#041520")
        GREEN  = ManimColor("#00FF99")
        GREY   = ManimColor("#1A3040")

        self.camera.background_color = DARK

        # =====================================================================
        # CONSTRUCTION : 6 modules en cercle autour du centre
        # =====================================================================

        MODULES = [
            ("STT",      "Whisper",        GREEN),
            ("LLM",      "Ollama",         BLUE),
            ("RAG",      "ChromaDB",       WHITE),
            ("MCP",      "Fedora/TV/Hue",  GREEN),
            ("TTS",      "Piper",          BLUE),
            ("TRACKING", "API :8765",      WHITE),
        ]

        n = len(MODULES)
        radius = 2.8
        angles = [PI / 2 + i * TAU / n for i in range(n)]  # commence en haut
        positions = [radius * np.array([np.cos(a), np.sin(a), 0]) for a in angles]

        # Noeuds modules
        nodes = []
        node_labels = []
        node_subs = []
        for i, ((name, sub, color), pos) in enumerate(zip(MODULES, positions)):
            ring = Circle(radius=0.42, color=GREY, fill_color=DIM,
                          fill_opacity=1, stroke_width=1.5).move_to(pos)
            lbl = Text(name, font="Monospace", color=GREY, weight=BOLD).scale(0.26).move_to(pos)
            sublbl = Text(sub, font="Monospace", color=GREY).scale(0.16)
            sublbl.next_to(ring, DOWN, buff=0.08)
            nodes.append(ring)
            node_labels.append(lbl)
            node_subs.append(sublbl)

        nodes_g = VGroup(*nodes)
        labels_g = VGroup(*node_labels)
        subs_g = VGroup(*node_subs)

        # Centre -- noyau LYRA (dormant)
        core = Circle(radius=0.18, color=BLUE2, fill_color=DIM,
                      fill_opacity=1, stroke_width=1.5)
        core_glow = Circle(radius=0.18, color=BLUE, fill_color=BLUE,
                           fill_opacity=0, stroke_width=0)

        # Lignes grises (inactives) entre chaque module et le centre
        base_lines = VGroup(*[
            DashedLine(pos * 0.42 / radius + pos * (1 - 0.42 / radius) * 0.12,
                       pos * 0.42 / radius,
                       color=GREY, stroke_width=0.6, stroke_opacity=0.3,
                       dash_length=0.08)
            for pos in positions
        ])
        # lignes simples du bord du noeud au centre
        base_lines = VGroup(*[
            Line(pos * (1 - 0.44 / radius), ORIGIN,
                 color=GREY, stroke_width=0.5, stroke_opacity=0.2)
            for pos in positions
        ])

        # =====================================================================
        # PHASE 1 : Apparition de la structure (0 -> 1.2s)
        # =====================================================================

        self.play(
            LaggedStart(
                *[GrowFromCenter(n) for n in nodes],
                lag_ratio=0.07, run_time=0.55
            ),
            FadeIn(labels_g, run_time=0.45),
            FadeIn(subs_g, run_time=0.45),
        )
        self.play(
            FadeIn(base_lines, run_time=0.25),
            GrowFromCenter(core, run_time=0.25),
        )

        # =====================================================================
        # PHASE 2 : Chaque module s'allume et envoie un flux vers LYRA (1.2 -> 6s)
        # =====================================================================

        active_streams = []

        for i, ((name, sub, color), pos, node, lbl, sublbl) in enumerate(
            zip(MODULES, positions, nodes, node_labels, node_subs)
        ):
            # -- Allumage + flux en une seule animation --
            stream_line = Line(
                pos * (1 - 0.44 / radius), ORIGIN,
                color=color, stroke_width=1.2, stroke_opacity=0.5
            )
            active_streams.append(stream_line)

            dot = Dot(pos * (1 - 0.44 / radius), radius=0.07, color=color)
            trail = TracedPath(dot.get_center, stroke_color=color,
                               stroke_width=2.5, stroke_opacity=0.6,
                               dissipating_time=0.3)
            self.add(trail)

            self.play(
                node.animate.set_stroke(color=color, width=2.5),
                lbl.animate.set_color(color),
                sublbl.animate.set_color(color).set_opacity(0.7),
                Flash(node, color=color, flash_radius=0.5,
                      num_lines=8, line_length=0.15, run_time=0.2),
                Create(stream_line, run_time=0.2),
                dot.animate.move_to(ORIGIN).set_opacity(0),
                run_time=0.28,
                rate_func=rush_into
            )
            self.remove(dot, trail)

            self.play(
                core.animate.set_stroke(color=color, width=2 + i * 0.4)
                            .scale(1.06),
                run_time=0.12,
                rate_func=there_and_back
            )

        # =====================================================================
        # PHASE 3 : TOUS CONNECTES -- le coeur s'emballe (6 -> 7.2s)
        # =====================================================================

        streams_g = VGroup(*active_streams)

        # Flash global + pulsations
        self.play(
            *[stream.animate.set_stroke(opacity=0.9, width=2.0)
              for stream in active_streams],
            core.animate.set_stroke(color=WHITE, width=4).scale(1.4),
            run_time=0.2
        )
        for _ in range(2):
            self.play(
                core.animate.scale(1.5).set_stroke(color=BLUE, width=5),
                run_time=0.12, rate_func=there_and_back
            )

        # =====================================================================
        # PHASE 4 : CONVERGENCE -- tout fonce vers le centre (7.2 -> 8.2s)
        # =====================================================================

        # Les modules filent vers le centre
        self.play(
            *[node.animate.move_to(ORIGIN).scale(0.01).set_opacity(0)
              for node in nodes],
            FadeOut(labels_g, run_time=0.25),
            FadeOut(subs_g, run_time=0.25),
            FadeOut(streams_g, run_time=0.2),
            FadeOut(base_lines, run_time=0.2),
            run_time=0.38,
            rate_func=rush_into
        )

        # =====================================================================
        # PHASE 5 : EXPLOSION -- LYRA emerge (8.2 -> 10.5s)
        # =====================================================================

        # Onde de choc
        shock = Circle(radius=0.01, color=WHITE, stroke_width=6,
                       fill_opacity=0)
        self.add(shock)
        self.play(
            shock.animate.scale(120).set_stroke(opacity=0),
            core.animate.scale(0.1).set_opacity(0),
            run_time=0.45, rate_func=rush_from
        )
        self.remove(shock, core)

        # LYRA
        lyra = Text("LYRA", font="Monospace", weight=BOLD, color=BLUE)
        lyra.scale(3.5)

        ring   = Circle(radius=2.2, color=BLUE,  stroke_width=2.5)
        ticks  = VGroup(
            Line(UP * 2.35,    UP * 2.7,    color=BLUE, stroke_width=2),
            Line(DOWN * 2.35,  DOWN * 2.7,  color=BLUE, stroke_width=2),
            Line(RIGHT * 2.35, RIGHT * 2.7, color=BLUE, stroke_width=2),
            Line(LEFT * 2.35,  LEFT * 2.7,  color=BLUE, stroke_width=2),
        )

        label_actif = Text("SYSTEME ACTIF", font="Monospace", color=WHITE)
        label_actif.scale(0.35).next_to(lyra, DOWN, buff=0.3)

        self.play(
            FadeIn(lyra, scale=0.1, run_time=0.35),
            Create(ring, run_time=0.35),
        )
        self.play(
            LaggedStart(*[GrowFromCenter(t) for t in ticks], lag_ratio=0.08),
            FadeIn(label_actif, shift=UP * 0.1, run_time=0.3),
            Flash(lyra, color=BLUE, flash_radius=1.6,
                  num_lines=24, line_length=0.7, run_time=0.45),
            Rotate(ring, angle=TAU * 0.12, run_time=0.5, rate_func=smooth),
        )

        self.wait(0.25)

        self.play(
            FadeOut(ring, ticks, label_actif, run_time=0.2),
            lyra.animate.scale(0.01).set_opacity(0),
            run_time=0.38, rate_func=rush_into
        )
        self.wait(0.05)
