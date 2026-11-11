"""Tests de scripts/sentinel-ci/sentinel_ci.py : logique pure, table-driven."""
from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sentinel-ci" / "sentinel_ci.py"
_spec = importlib.util.spec_from_file_location("sentinel_ci", _PATH)
sc = importlib.util.module_from_spec(_spec)
sys.modules["sentinel_ci"] = sc  # requis par @dataclass avec annotations differees
_spec.loader.exec_module(sc)

REPO = "o/r"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def _run(wf, status="completed", conclusion="success", sha="abcdef123456"):
    return {"workflowName": wf, "status": status, "conclusion": conclusion,
            "headSha": sha, "url": f"https://x/{wf}"}


@pytest.mark.parametrize(
    "runs, expected_keys",
    [
        ([], []),
        ([_run("Tests")], []),
        ([_run("Tests", conclusion="failure")], ["o/r:run:main:Tests"]),
        ([_run("Tests", conclusion="timed_out")], ["o/r:run:main:Tests"]),
        ([_run("Tests", conclusion="cancelled")], []),
        # le plus recent termine gagne : echec ancien ignore si le dernier est vert
        ([_run("Tests"), _run("Tests", conclusion="failure")], []),
        # run en cours ignore : on regarde le dernier termine
        ([_run("Tests", status="in_progress", conclusion=""),
          _run("Tests", conclusion="failure")], ["o/r:run:main:Tests"]),
        ([_run("A", conclusion="failure"), _run("B", conclusion="failure")],
         ["o/r:run:main:A", "o/r:run:main:B"]),
    ],
)
def test_analyze_runs(runs, expected_keys):
    assert [a.key for a in sc.analyze_runs(REPO, "main", runs)] == expected_keys


def _pr(num=1, login="someone", created="2026-11-09T00:00:00Z", checks=()):
    return {"number": num, "author": {"login": login}, "createdAt": created,
            "url": f"https://x/pull/{num}", "statusCheckRollup": list(checks)}


def _check(name, conclusion="SUCCESS", wf=""):
    return {"__typename": "CheckRun", "name": name, "conclusion": conclusion, "workflowName": wf}


@pytest.mark.parametrize(
    "pr, kinds",
    [
        (_pr(), []),
        (_pr(checks=[_check("lint", "FAILURE")]), ["pr-checks"]),
        (_pr(checks=[_check("lint"), _check("lint", "FAILURE")]), ["pr-checks"]),
        (_pr(checks=[{"__typename": "StatusContext", "context": "ci", "state": "ERROR"}]),
         ["pr-checks"]),
        (_pr(login="app/dependabot", created="2026-11-01T00:00:00Z"), ["dependabot-stale"]),
        (_pr(login="app/dependabot", created="2026-11-05T00:00:00Z"), []),
        # une PR non Dependabot ancienne n'est pas signalee
        (_pr(created="2026-01-01T00:00:00Z"), []),
        (_pr(login="app/dependabot", checks=[_check("regenerate", "FAILURE", "Dependabot licences")]),
         ["dependabot-licenses"]),
        (_pr(login="dependabot[bot]", created="2026-10-01T00:00:00Z",
             checks=[_check("tests", "FAILURE"), _check("regenerate", "FAILURE", "Dependabot licences")]),
         ["pr-checks", "dependabot-licenses", "dependabot-stale"]),
    ],
)
def test_analyze_prs(pr, kinds):
    assert [a.kind for a in sc.analyze_prs(REPO, [pr], NOW)] == kinds


@pytest.mark.parametrize(
    "sev, expected",
    [("critical", "high"), ("high", "high"), ("medium", "medium"), ("low", "medium"),
     (None, "medium")],
)
def test_analyze_security_alerts_severity(sev, expected):
    raw = [{"number": 3, "html_url": "u", "dependency": {"package": {"name": "pkg"}},
            "security_advisory": {"severity": sev, "summary": "bad"}}]
    (alert,) = sc.analyze_security_alerts(REPO, raw)
    assert alert.severity == expected
    assert alert.key == "o/r:secalert:3"
    assert "pkg" in alert.title


def test_alerts_are_immutable():
    al = sc.detector_alert(REPO, "runs", "boom")
    with pytest.raises(AttributeError):
        al.title = "x"


def test_decide_notifications_dedup_change_and_renotify():
    a = sc.Alert("k", "fp1", "high", "ci-main", REPO, "t")
    notify, state = sc.decide_notifications((a,), {}, now=1000.0)
    assert notify == (a,)
    # meme alerte juste apres : silence, etat conserve
    notify, state2 = sc.decide_notifications((a,), state, now=1100.0)
    assert notify == () and state2 == state
    # empreinte modifiee : re-notifie
    b = sc.Alert("k", "fp2", "high", "ci-main", REPO, "t")
    notify, state3 = sc.decide_notifications((b,), state2, now=1200.0)
    assert notify == (b,)
    # delai ecoule : re-notifie
    notify, _ = sc.decide_notifications((b,), state3, now=1200.0 + sc.RENOTIFY_SECONDS)
    assert notify == (b,)


def test_resolved_alert_is_forgotten_then_renotified():
    a = sc.Alert("k", "fp", "high", "ci-main", REPO, "t")
    _, state = sc.decide_notifications((a,), {}, now=1.0)
    _, state = sc.decide_notifications((), state, now=2.0)
    assert state == {}
    notify, _ = sc.decide_notifications((a,), state, now=3.0)
    assert notify == (a,)


def test_decide_does_not_mutate_input_state():
    a = sc.Alert("k", "fp", "high", "x", REPO, "t")
    old = {"k": {"fingerprint": "fp", "notified_at": 5.0}}
    snapshot = {"k": dict(old["k"])}
    sc.decide_notifications((a,), old, now=6.0)
    assert old == snapshot


def _fake_gh(responses):
    def gh(args):
        for needle, value in responses.items():
            if needle in " ".join(args):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"appel gh inattendu: {args}")
    return gh


def test_collect_all_green():
    gh = _fake_gh({
        "repo view": {"defaultBranchRef": {"name": "main"}},
        "run list": [_run("Tests")],
        "pr list": [],
        "dependabot/alerts": [],
    })
    assert sc.collect(REPO, gh, NOW) == ((), ())


def test_collect_security_api_forbidden_is_a_note_not_an_alert():
    gh = _fake_gh({
        "repo view": {"defaultBranchRef": {"name": "main"}},
        "run list": [],
        "pr list": [],
        "dependabot/alerts": sc.GhError("gh: Forbidden (HTTP 403)"),
    })
    alerts, notes = sc.collect(REPO, gh, NOW)
    assert alerts == () and len(notes) == 1 and "403" in notes[0]


def test_collect_gh_failure_becomes_detector_alerts_never_silent():
    err = sc.GhError("gh auth login required")
    gh = _fake_gh({"repo view": err, "pr list": err, "dependabot/alerts": err})
    alerts, notes = sc.collect(REPO, gh, NOW)
    assert [a.kind for a in alerts] == ["detector"] * 3
    assert {a.key.split(":")[-1] for a in alerts} == {"runs", "prs", "security-alerts"}


@pytest.mark.parametrize("bad", ["lyra", "a/b/c", "a b/c", "../x", ""])
def test_resolve_repos_rejects_invalid(bad):
    with pytest.raises(ValueError):
        sc.resolve_repos([bad])


def test_resolve_repos_default_and_env(monkeypatch):
    monkeypatch.delenv("SENTINEL_CI_REPOS", raising=False)
    assert sc.resolve_repos(None) == sc.DEFAULT_REPOS
    monkeypatch.setenv("SENTINEL_CI_REPOS", "a/b, c/d")
    assert sc.resolve_repos(None) == ("a/b", "c/d")


def test_state_roundtrip_and_corruption(tmp_path):
    path = tmp_path / "s" / "state.json"
    assert sc.load_state(path) == {}
    sc.save_state(path, {"alerts": {"k": 1}})
    assert sc.load_state(path) == {"alerts": {"k": 1}}
    path.write_text("{not json")
    assert sc.load_state(path) == {}
