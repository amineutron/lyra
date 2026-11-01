"""Hook MkDocs du site de documentation : inclusions et liens.

Le site reprend des fichiers qui vivent ailleurs dans le dépôt (README, README de
l'installeur, BENCHMARKS, CHANGELOG) sans les recopier. Une page les appelle par
une ligne seule :

    <!-- inclure: installer/README.md#Derrière un proxy d'entreprise -->

(chemin depuis la racine du dépôt ; après `#`, le titre de la section à reprendre,
sous-sections comprises ; sans `#`, le fichier entier). Le titre repris est
décalé au niveau `niveau=N` si on le précise : `<!-- inclure: README.md#Licence niveau=2 -->` ;
`sans-titre` reprend la section sans sa ligne de titre (la page a déjà le sien).

Les liens relatifs sont ensuite réécrits d'après le fichier qui les contient :
vers la page du site si la cible en fait partie, vers GitHub sinon (code,
scripts, fichiers hors du site). Sans cela un lien comme `lyra/core/constants.py`
mènerait à une page introuvable.

La logique est pure et testée (tests/unit/test_docs_site.py) ; seule
`on_page_markdown` dépend de MkDocs.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

REPO_URL = "https://github.com/amineutron/lyra"
BRANCH = "main"

_INCLUDE = re.compile(r"^<!--\s*inclure:\s*(?P<path>[^#\s]+)(?:#(?P<section>.+?))?"
                      r"(?P<opts>(?:\s+(?:niveau=[1-6]|sans-titre))*)\s*-->\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# [texte](cible "titre") et ![alt](cible) ; la cible s'arrête au premier espace ou ')'
_INLINE = re.compile(r"(!?\[[^\]\n]*\]\()(<[^>\n]+>|[^)\s]+)((?:\s+\"[^\"\n]*\")?\))")
_REFDEF = re.compile(r"^(\s{0,3}\[[^\]\n]+\]:\s*)(\S+)(.*)$")
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")


class IncludeError(ValueError):
    """Inclusion impossible : fichier ou section introuvable."""


def _outside_fences(lines: list[str]):
    """(index, ligne, hors_bloc_de_code) pour chaque ligne."""
    fence = None
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
                yield i, line, False
                continue
            if line.strip().startswith(fence):
                fence = None
                yield i, line, False
                continue
        yield i, line, fence is None


def extract_section(markdown: str, title: str) -> str:
    """La section `title` (titre compris) jusqu'au titre suivant de même niveau ou plus haut."""
    lines = markdown.splitlines()
    start = level = None
    for i, line, outside in _outside_fences(lines):
        if not outside:
            continue
        m = _HEADING.match(line)
        if not m:
            continue
        if start is None:
            if m.group(2).strip() == title.strip():
                start, level = i, len(m.group(1))
        elif len(m.group(1)) <= level:
            return "\n".join(lines[start:i]).rstrip() + "\n"
    if start is None:
        raise IncludeError(f"section introuvable : {title!r}")
    return "\n".join(lines[start:]).rstrip() + "\n"


def shift_headings(markdown: str, level: int) -> str:
    """Décale les titres pour que le premier soit au niveau `level` (bornés entre 1 et 6)."""
    lines = markdown.splitlines()
    first = None
    for _, line, outside in _outside_fences(lines):
        m = _HEADING.match(line) if outside else None
        if m:
            first = len(m.group(1))
            break
    if first is None or first == level:
        return markdown
    delta = level - first
    out = []
    for _, line, outside in _outside_fences(lines):
        m = _HEADING.match(line) if outside else None
        if m:
            new = min(6, max(1, len(m.group(1)) + delta))
            line = "#" * new + " " + m.group(2)
        out.append(line)
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else "")


def drop_first_heading(markdown: str) -> str:
    """Retire la première ligne de titre (hors blocs de code) et les lignes vides qui la suivent."""
    lines = markdown.splitlines()
    for i, line, outside in _outside_fences(lines):
        if outside and _HEADING.match(line):
            rest = lines[i + 1:]
            while rest and not rest[0].strip():
                rest.pop(0)
            return "\n".join(lines[:i] + rest) + ("\n" if markdown.endswith("\n") else "")
    return markdown


def resolve_link(target: str, base_dir: str, page_dir: str, site_files: set[str],
                 repo_root: Path) -> str:
    """Cible réécrite d'un lien relatif écrit dans un fichier de `base_dir` (chemins du dépôt).

    `site_files` : chemins (depuis la racine du dépôt) des fichiers publiés par le site.
    """
    bracketed = target.startswith("<") and target.endswith(">")
    raw = target[1:-1] if bracketed else target
    if not raw or raw.startswith(("#", "/")) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw):
        return target
    path, sep, anchor = raw.partition("#")
    repo_path = posixpath.normpath(posixpath.join(base_dir, path))
    if repo_path.startswith(".."):
        return target
    suffix = sep + anchor
    if repo_path in site_files:
        new = posixpath.relpath(repo_path, page_dir) + suffix
    elif (repo_root / repo_path).is_file():
        new = f"{REPO_URL}/blob/{BRANCH}/{repo_path}{suffix}"
    elif (repo_root / repo_path).is_dir():
        new = f"{REPO_URL}/tree/{BRANCH}/{repo_path.rstrip('/')}"
    else:
        return target
    return f"<{new}>" if bracketed else new


def rewrite_links(markdown: str, base_dir: str, page_dir: str, site_files: set[str],
                  repo_root: Path) -> str:
    """Réécrit les liens relatifs hors des blocs et du code en ligne."""
    def fix(target: str) -> str:
        return resolve_link(target, base_dir, page_dir, site_files, repo_root)

    def fix_inline(text: str) -> str:
        # le code en ligne est mis de côté le temps de la réécriture
        codes: list[str] = []

        def keep(m: re.Match) -> str:
            codes.append(m.group(0))
            return f"\x00{len(codes) - 1}\x00"

        hidden = _INLINE_CODE.sub(keep, text)
        hidden = _INLINE.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), hidden)
        return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], hidden)

    lines = markdown.splitlines()
    out = []
    for _, line, outside in _outside_fences(lines):
        if outside:
            ref = _REFDEF.match(line)
            line = ref.group(1) + fix(ref.group(2)) + ref.group(3) if ref else fix_inline(line)
        out.append(line)
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else "")


def render_page(markdown: str, page_repo_path: str, site_files: set[str], repo_root: Path) -> str:
    """Page finale : liens de la page réécrits, inclusions remplacées par leur contenu réécrit."""
    page_dir = posixpath.dirname(page_repo_path)
    out: list[str] = []
    chunk: list[str] = []

    def flush() -> None:
        if chunk:
            text = "\n".join(chunk) + "\n"
            out.append(rewrite_links(text, page_dir, page_dir, site_files, repo_root))
            chunk.clear()

    for _, line, outside in _outside_fences(markdown.splitlines()):
        m = _INCLUDE.match(line) if outside else None
        if not m:
            chunk.append(line)
            continue
        flush()
        src = m.group("path")
        source = repo_root / src
        if not source.is_file():
            raise IncludeError(f"{page_repo_path} : fichier à inclure introuvable : {src}")
        text = source.read_text(encoding="utf-8")
        if m.group("section"):
            try:
                text = extract_section(text, m.group("section"))
            except IncludeError as exc:
                raise IncludeError(f"{page_repo_path} : {src} : {exc}") from None
        opts = m.group("opts").split()
        if "sans-titre" in opts:
            text = drop_first_heading(text)
        level = next((int(o.split("=")[1]) for o in opts if o.startswith("niveau=")), None)
        if level:
            text = shift_headings(text, level)
        out.append(rewrite_links(text, posixpath.dirname(src), page_dir, site_files, repo_root))
    flush()
    return "".join(out)


def on_page_markdown(markdown, page, config, files):  # pragma: no cover - appelé par MkDocs
    docs_dir = Path(config["docs_dir"])
    repo_root = docs_dir.parent
    prefix = docs_dir.name
    # les fichiers exclus (exclude_docs) restent dans `files` mais ne sont pas publiés
    site_files = {f"{prefix}/{f.src_uri}" for f in files
                  if getattr(f, "inclusion", None) is None or f.inclusion.is_included()}
    return render_page(markdown, f"{prefix}/{page.file.src_uri}", site_files, repo_root)
