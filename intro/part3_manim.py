"""
Lyra Intro - Partie 3 : Animation Manim
Rendu : manim -pql part3_manim.py LyraIntro
Output : media/videos/part3_manim/480p15/LyraIntro.mp4

Pour un rendu haute qualite (1080p) :
  manim -pqh part3_manim.py LyraIntro
"""
from manim import *


class LyraIntro(Scene):
    def construct(self):
        # -- Couleurs ---------------------------------------------------------
        LYRA_BLUE   = ManimColor("#00D4FF")
        LYRA_DARK   = ManimColor("#001122")
        LYRA_WHITE  = WHITE
        LYRA_DIM    = ManimColor("#445566")

        self.camera.background_color = LYRA_DARK

        # -- Cercle de scan ---------------------------------------------------
        ring = Circle(radius=1.8, color=LYRA_BLUE, stroke_width=1.5)
        ring_inner = Circle(radius=1.5, color=LYRA_DIM, stroke_width=0.5)
        ring_outer = Circle(radius=2.1, color=LYRA_DIM, stroke_width=0.5)

        # -- Croix de visee ---------------------------------------------------
        cross_h = Line(LEFT * 2.5, RIGHT * 2.5, color=LYRA_DIM, stroke_width=0.5)
        cross_v = Line(UP * 2.5, DOWN * 2.5, color=LYRA_DIM, stroke_width=0.5)
        hud_group = VGroup(ring_outer, ring_inner, ring, cross_h, cross_v)

        # -- Texte LYRA -------------------------------------------------------
        title = Text("LYRA", font="Monospace", color=LYRA_BLUE, weight=BOLD)
        title.scale(2.8)

        subtitle = Text(
            "ASSISTANT DEVOPS VOCAL",
            font="Monospace",
            color=LYRA_WHITE,
            weight=NORMAL
        )
        subtitle.scale(0.45)
        subtitle.next_to(title, DOWN, buff=0.25)

        version = Text("v1.0", font="Monospace", color=LYRA_DIM)
        version.scale(0.3)
        version.next_to(subtitle, DOWN, buff=0.15)

        text_group = VGroup(title, subtitle, version)

        # -- Ligne decorative -------------------------------------------------
        line_left  = Line(LEFT * 1.8, LEFT * 0.6, color=LYRA_BLUE, stroke_width=1)
        line_right = Line(RIGHT * 0.6, RIGHT * 1.8, color=LYRA_BLUE, stroke_width=1)
        line_left.next_to(subtitle, LEFT, buff=0.1).align_to(subtitle, DOWN).shift(DOWN * 0.05)
        line_right.next_to(subtitle, RIGHT, buff=0.1).align_to(subtitle, DOWN).shift(DOWN * 0.05)

        # =====================================================================
        # SEQUENCE D'ANIMATION
        # =====================================================================

        # 1. HUD qui apparait
        self.play(
            Create(ring_outer, run_time=0.6),
            Create(ring_inner, run_time=0.6),
        )
        self.play(
            Create(ring, run_time=0.5),
            Create(cross_h, run_time=0.3),
            Create(cross_v, run_time=0.3),
        )

        # 2. Rotation lente du ring pendant que le texte apparait
        self.play(
            Rotate(ring, angle=TAU * 0.15, run_time=1.0, rate_func=smooth),
            FadeIn(title, shift=UP * 0.2, run_time=0.8),
        )
        self.play(
            FadeIn(subtitle, shift=UP * 0.1, run_time=0.5),
            Create(line_left, run_time=0.4),
            Create(line_right, run_time=0.4),
        )
        self.play(FadeIn(version, run_time=0.4))

        # 3. Pulse du ring (zoom in/out)
        self.play(
            ring.animate.scale(1.05),
            run_time=0.3, rate_func=there_and_back
        )

        # 4. Maintien court
        self.wait(0.6)

        # 5. Fade out rapide
        self.play(
            FadeOut(hud_group, run_time=0.2),
            FadeOut(text_group, run_time=0.2),
            FadeOut(line_left, run_time=0.15),
            FadeOut(line_right, run_time=0.15),
        )

        self.wait(0.05)
