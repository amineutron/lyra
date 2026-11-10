"""Pure-logic checks for scripts/render_mascots.py (no Chrome needed)."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "render_mascots", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "render_mascots.py"
)
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)

SVG_SRC = pathlib.Path(rm.SRC)


def test_lcm_of_loop_durations():
    assert rm.lcm(1600, 2400) == 4800
    assert rm.lcm(1, 3000) == 3000


def test_every_mascot_has_six_states_and_matching_class():
    files = sorted(SVG_SRC.glob("*.html"))
    assert len(files) == 30
    for f in files:
        text = f.read_text()
        assert f'class="mx m-{f.stem}"' in text
        for state in rm.STATES:
            assert f'class="s s-{state}' in text, (f.stem, state)


def test_build_page_sets_state_and_cell_count():
    frag = (SVG_SRC / "owl.html").read_text()
    page = rm.build_page(frag, "owl", "work", 128, 5, "", False)
    assert page.count('class="cell"') == 5
    assert 'data-state="work"' in page
    assert rm.build_page(frag, "owl", "work", 128, 5, "", True).count('class="cell"') == 1
