#!/usr/bin/env python3
"""Sentinelle CI : detecte les echecs de CI GitHub et les soucis Dependabot.

Par depot (liste configurable) : runs en echec sur la branche par defaut,
checks en echec sur les PR ouvertes, PR Dependabot trop anciennes ou dont le
workflow dependabot-licenses echoue, alertes de securite Dependabot ouvertes.
Toute erreur du detecteur (gh absent, non authentifie, reseau) devient elle
aussi une alerte : jamais d'echec silencieux.

Stdlib + `gh` uniquement (auth existante de gh, aucun jeton ecrit ici).
Lecture seule cote GitHub. Notification : notify-send (degrade en log) et
session MCP tracking optionnelle.

Usage : sentinel_ci.py [--repo OWNER/NAME ...] [--dry-run] [--json]
Env   : SENTINEL_CI_REPOS (liste separee par des virgules), SENTINEL_CI_STATE.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_REPOS = ("amineutron/lyra",)
STALE_PR_DAYS = 7
RENOTIFY_SECONDS = 24 * 3600
GH_TIMEOUT = 60
TRACKING_URL = "http://127.0.0.1:8765"
TRACKING_NAME = "Sentinel CI"
DIGEST_THRESHOLD = 3
BAD_RUN_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})
BAD_CHECK_CONCLUSIONS = frozenset({"FAILURE", "TIMED_OUT", "STARTUP_FAILURE"})
BAD_STATUS_STATES = frozenset({"FAILURE", "ERROR"})
HIGH_ALERT_SEVERITIES = frozenset({"high", "critical"})
REPO_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*/(?!\.{1,2}$)[A-Za-z0-9_.-]+$")
LICENSES_RE = re.compile(r"dependabot.?licen[cs]es", re.IGNORECASE)
DEPENDABOT_LOGINS = frozenset({"dependabot", "app/dependabot", "dependabot[bot]"})


class GhError(RuntimeError):
    """Echec d'un appel gh (message lisible, stderr tronque)."""


@dataclass(frozen=True)
class Alert:
    key: str  # identifiant stable (dedoublonnage)
    fingerprint: str  # change quand l'alerte evolue (re-notification)
    severity: str  # high | medium | low
    kind: str
    repo: str
    title: str
    url: str = ""


# --------------------------------------------------------------------------
# Logique pure : JSON gh -> alertes normalisees
# --------------------------------------------------------------------------

def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def analyze_runs(repo: str, branch: str, runs: list[dict]) -> tuple[Alert, ...]:
    """Dernier run termine de chaque workflow sur la branche : alerte si en echec."""
    seen: set[str] = set()
    out: list[Alert] = []
    for run in runs:  # gh liste du plus recent au plus ancien
        if run.get("status") != "completed":
            continue
        wf = run.get("workflowName") or "?"
        if wf in seen:
            continue
        seen.add(wf)
        if run.get("conclusion") in BAD_RUN_CONCLUSIONS:
            sha = str(run.get("headSha", ""))[:7]
            out.append(Alert(
                key=f"{repo}:run:{branch}:{wf}",
                fingerprint=f"{run.get('conclusion')}:{run.get('headSha', '')}",
                severity="high",
                kind="ci-main",
                repo=repo,
                title=f"{repo}: workflow '{wf}' en echec sur {branch} ({sha})",
                url=run.get("url", ""),
            ))
    return tuple(out)


def _failed_checks(rollup: list[dict]) -> tuple[tuple[str, str], ...]:
    """(nom du check, nom du workflow) pour chaque check en echec, sans doublon."""
    failed: dict[str, str] = {}
    for item in rollup or []:
        bad = (
            item.get("conclusion") in BAD_CHECK_CONCLUSIONS
            or item.get("state") in BAD_STATUS_STATES
        )
        if bad:
            name = item.get("name") or item.get("context") or "?"
            failed.setdefault(name, item.get("workflowName") or "")
    return tuple(sorted(failed.items()))


def analyze_prs(repo: str, prs: list[dict], now: datetime) -> tuple[Alert, ...]:
    """Checks en echec, licences Dependabot en echec, PR Dependabot trop anciennes."""
    out: list[Alert] = []
    for pr in prs:
        num = pr.get("number")
        login = (pr.get("author") or {}).get("login", "")
        is_dep = login.lower() in DEPENDABOT_LOGINS
        label = f"PR #{num}{' (Dependabot)' if is_dep else ''}"
        url = pr.get("url", "")
        failed = _failed_checks(pr.get("statusCheckRollup") or [])
        licences = tuple(f for f in failed if LICENSES_RE.search(f"{f[0]} {f[1]}"))
        others = tuple(f for f in failed if f not in licences)
        if others:
            names = ", ".join(n for n, _ in others)
            out.append(Alert(
                key=f"{repo}:pr-checks:{num}",
                fingerprint="|".join(n for n, _ in others),
                severity="medium",
                kind="pr-checks",
                repo=repo,
                title=f"{repo}: {label} checks en echec: {names}",
                url=url,
            ))
        if licences:
            out.append(Alert(
                key=f"{repo}:dep-licenses:{num}",
                fingerprint="|".join(n for n, _ in licences),
                severity="medium",
                kind="dependabot-licenses",
                repo=repo,
                title=f"{repo}: {label} workflow dependabot-licenses en echec",
                url=url,
            ))
        age = now - _parse_ts(pr["createdAt"]) if pr.get("createdAt") else None
        if is_dep and age is not None and age.days >= STALE_PR_DAYS:
            out.append(Alert(
                key=f"{repo}:dep-stale:{num}",
                fingerprint="stale",
                severity="low",
                kind="dependabot-stale",
                repo=repo,
                title=f"{repo}: {label} ouverte depuis {age.days} jours",
                url=url,
            ))
    return tuple(out)


def analyze_security_alerts(repo: str, alerts: list[dict]) -> tuple[Alert, ...]:
    """Alertes de securite Dependabot ouvertes ; high/critical en priorite."""
    out: list[Alert] = []
    for al in alerts:
        adv = al.get("security_advisory") or {}
        sev = str(adv.get("severity") or "unknown").lower()
        pkg = ((al.get("dependency") or {}).get("package") or {}).get("name", "?")
        summary = adv.get("summary") or adv.get("ghsa_id") or "alerte"
        out.append(Alert(
            key=f"{repo}:secalert:{al.get('number')}",
            fingerprint=sev,
            severity="high" if sev in HIGH_ALERT_SEVERITIES else "medium",
            kind="security-alert",
            repo=repo,
            title=f"{repo}: alerte Dependabot {sev} sur {pkg}: {summary}",
            url=al.get("html_url", ""),
        ))
    return tuple(out)


def detector_alert(repo: str, step: str, message: str) -> Alert:
    """Erreur du detecteur lui-meme, remontee comme une alerte."""
    msg = " ".join(message.split())[:200]
    return Alert(
        key=f"{repo}:detector:{step}",
        fingerprint=msg,
        severity="high",
        kind="detector",
        repo=repo,
        title=f"Sentinel CI: etape '{step}' impossible pour {repo}: {msg}",
    )


def decide_notifications(
    alerts: tuple[Alert, ...], state: dict, now: float, renotify: float = RENOTIFY_SECONDS
) -> tuple[tuple[Alert, ...], dict]:
    """(alertes a notifier, nouvel etat). Nouvelle, modifiee, ou non notifiee depuis `renotify` s.

    L'etat ne garde que les alertes encore actives : une alerte resolue puis
    revenue est donc notifiee de nouveau.
    """
    to_notify: list[Alert] = []
    new_state: dict = {}
    for al in alerts:
        prev = state.get(al.key)
        due = (
            prev is None
            or prev.get("fingerprint") != al.fingerprint
            or now - float(prev.get("notified_at", 0)) >= renotify
        )
        if due:
            to_notify.append(al)
            new_state[al.key] = {"fingerprint": al.fingerprint, "notified_at": now}
        else:
            new_state[al.key] = dict(prev)
    return tuple(to_notify), new_state


# --------------------------------------------------------------------------
# Entrees/sorties : gh, etat, notifications, tracking
# --------------------------------------------------------------------------

def run_gh(args: list[str]) -> object:
    """Execute gh et renvoie le JSON decode ; GhError explicite sinon."""
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT, check=False
        )
    except FileNotFoundError as exc:
        raise GhError("gh introuvable dans le PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"gh timeout apres {GH_TIMEOUT}s") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip() or f"code {proc.returncode}"
        raise GhError(detail[:300])
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GhError(f"sortie gh non JSON: {exc}") from exc


def collect(
    repo: str, gh=run_gh, now: datetime | None = None
) -> tuple[tuple[Alert, ...], tuple[str, ...]]:
    """Interroge GitHub pour un depot. Renvoie (alertes, notes informatives)."""
    now = now or datetime.now(UTC)
    alerts: list[Alert] = []
    notes: list[str] = []

    def step(name: str, fn) -> None:
        try:
            alerts.extend(fn())
        except GhError as exc:
            alerts.append(detector_alert(repo, name, str(exc)))

    def runs_step():
        info = gh(["repo", "view", repo, "--json", "defaultBranchRef"])
        branch = ((info or {}).get("defaultBranchRef") or {}).get("name")
        if not branch:
            raise GhError("branche par defaut introuvable")
        runs = gh(["run", "list", "-R", repo, "--branch", branch, "-L", "50", "--json",
                   "workflowName,status,conclusion,headSha,url"])
        return analyze_runs(repo, branch, runs or [])

    def prs_step():
        prs = gh(["pr", "list", "-R", repo, "--state", "open", "-L", "100", "--json",
                  "number,author,createdAt,url,statusCheckRollup"])
        return analyze_prs(repo, prs or [], now)

    def sec_step():
        try:
            data = gh(["api", f"repos/{repo}/dependabot/alerts?state=open&per_page=100"])
        except GhError as exc:
            if "HTTP 403" in str(exc) or "HTTP 404" in str(exc):
                notes.append(f"{repo}: API alertes Dependabot inaccessible ({str(exc)[:80]})")
                return ()
            raise
        return analyze_security_alerts(repo, data or [])

    step("runs", runs_step)
    step("prs", prs_step)
    step("security-alerts", sec_step)
    return tuple(alerts), tuple(notes)


def default_state_path() -> Path:
    env = os.environ.get("SENTINEL_CI_STATE")
    if env:
        return Path(env)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "sentinel-ci" / "state.json"


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"sentinel-ci: etat illisible ({exc}), repart de zero", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(path)


def notify_local(alerts: tuple[Alert, ...]) -> None:
    """notify-send ; si indisponible ou en echec, simple log (stderr)."""
    if len(alerts) > DIGEST_THRESHOLD:
        text = f"{len(alerts)} nouvelles alertes\n" + "\n".join(a.title for a in alerts[:8])
        batch = (("Sentinel CI", text, "critical"),)
    else:
        batch = tuple(
            ("Sentinel CI", f"{a.title}\n{a.url}".strip(),
             "critical" if a.severity == "high" else "normal")
            for a in alerts
        )
    for title, body, urgency in batch:
        print(f"sentinel-ci: ALERTE {body.splitlines()[0]}", file=sys.stderr)
        try:
            proc = subprocess.run(
                ["notify-send", "--app-name=sentinel-ci", f"--urgency={urgency}", title, body],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if proc.returncode != 0:
                print(f"sentinel-ci: notify-send a echoue ({proc.stderr.strip()[:100]})",
                      file=sys.stderr)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"sentinel-ci: notify-send indisponible ({exc})", file=sys.stderr)


def _tracking_call(method: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        TRACKING_URL + path, data=json.dumps(payload).encode(), method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310 (URL locale fixe)
        return json.loads(resp.read() or b"{}")


def report_tracking(alerts: tuple[Alert, ...], session_id: str | None) -> str | None:
    """Une session 'Sentinel CI' mise a jour ; optionnel, ne leve jamais. Renvoie l'id a garder."""
    try:
        if not alerts:
            if session_id:
                _tracking_call("PUT", f"/sessions/{session_id}",
                               {"status": "done", "log": "plus d'alerte"})
            return None
        log = f"{len(alerts)} alerte(s): " + " ; ".join(a.title for a in alerts[:5])
        body = {"status": "error", "log": log[:500], "extra": {"alerts": len(alerts)}}
        if session_id:
            try:
                _tracking_call("PUT", f"/sessions/{session_id}", body)
                return session_id
            except OSError:
                pass  # session disparue : on en recree une
        created = _tracking_call("POST", "/sessions", {"name": TRACKING_NAME, "template": "free"})
        sid = created.get("id")
        if sid:
            _tracking_call("PUT", f"/sessions/{sid}", body)
        return sid
    except (OSError, ValueError) as exc:
        print(f"sentinel-ci: tracking indisponible ({exc}), ignore", file=sys.stderr)
        return session_id


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def resolve_repos(cli: list[str] | None) -> tuple[str, ...]:
    env = os.environ.get("SENTINEL_CI_REPOS", "")
    repos = tuple(cli or [r.strip() for r in env.split(",") if r.strip()] or DEFAULT_REPOS)
    bad = [r for r in repos if not REPO_RE.match(r)]
    if bad:
        raise ValueError(f"depot invalide (attendu OWNER/NAME): {', '.join(bad)}")
    return repos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", action="append", help="OWNER/NAME (repetable)")
    ap.add_argument("--dry-run", action="store_true", help="affiche sans notifier ni ecrire l'etat")
    ap.add_argument("--json", action="store_true", help="sortie JSON des alertes")
    ap.add_argument("--state", type=Path, default=None, help="fichier d'etat")
    args = ap.parse_args(argv)
    try:
        repos = resolve_repos(args.repo)
    except ValueError as exc:
        print(f"sentinel-ci: {exc}", file=sys.stderr)
        return 2

    alerts: list[Alert] = []
    notes: list[str] = []
    for repo in repos:
        found, found_notes = collect(repo)
        alerts.extend(found)
        notes.extend(found_notes)
    alerts_t = tuple(alerts)

    if args.json:
        print(json.dumps({"alerts": [asdict(a) for a in alerts_t], "notes": notes}, indent=1))
    else:
        print(f"sentinel-ci: {len(repos)} depot(s), {len(alerts_t)} alerte(s)")
        for a in alerts_t:
            print(f"  [{a.severity}] {a.title} {a.url}".rstrip())
        for n in notes:
            print(f"  [info] {n}")
    if args.dry_run:
        return 0

    path = args.state or default_state_path()
    state = load_state(path)
    now = datetime.now(UTC).timestamp()
    to_notify, new_alerts = decide_notifications(alerts_t, state.get("alerts", {}), now)
    if to_notify:
        notify_local(to_notify)
    session = state.get("tracking_session")
    if to_notify or session:
        session = report_tracking(alerts_t, session)
    new_state = {"alerts": new_alerts, **({"tracking_session": session} if session else {})}
    try:
        save_state(path, new_state)
    except OSError as exc:
        print(f"sentinel-ci: ecriture de l'etat impossible ({exc})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
