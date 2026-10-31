# Publier une version

Une version de Lyra est un tag `vX.Y.Z` signé. Le pousser déclenche
`.github/workflows/release.yml`, qui construit, prouve et publie tout seul.

## Avant le tag

1. `uv lock --check` : le lock correspond à `pyproject.toml` (la CI le vérifie aussi à
   chaque PR et refuse de construire une release sinon).
2. Monter `version` dans `pyproject.toml`, puis `uv lock` (le lock porte la version du
   projet).
3. Déplacer la section `[Unreleased]` de `CHANGELOG.md` sous `## [X.Y.Z] - AAAA-MM-JJ`.
4. Si une dépendance a changé : `make licenses` (la CI compare `THIRD_PARTY_LICENSES.md`).
5. Commit `chore(release): vX.Y.Z` fusionné sur `main`, CI verte.

## Le tag

Les tags sont signés avec la clé SSH du mainteneur (`gpg.format ssh`, `tag.gpgSign true`) :

```bash
git switch main && git pull --ff-only
git tag -s vX.Y.Z -m "lyra-assistant X.Y.Z"
git tag -v vX.Y.Z          # doit afficher « Good "git" signature »
git push origin vX.Y.Z
```

`git tag -v` lit les clés autorisées dans le fichier désigné par
`gpg.ssh.allowedSignersFile`. Une signature absente ou invalide ne bloque pas le
workflow : c'est à vérifier ici, avant de pousser.

## Ce que fait le workflow

| Étape | Résultat |
|---|---|
| `uv lock --check` | échoue si le lock est périmé : rien n'est construit |
| `uv build` | wheel et sdist dans `dist/` |
| `uv export --format cyclonedx1.5` | `sbom.json` : dépendances de base et extra `gpu`, versions exactes du lock, sans les outils de développement |
| `actions/attest` (provenance) | attestation SLSA signée par Sigstore : ces fichiers ont été construits par ce workflow, depuis ce commit de ce dépôt |
| `actions/attest` (SBOM) | le `sbom.json` attesté pour le wheel et le sdist |
| Publication | PyPI (Trusted Publishing), puis release GitHub avec les notes git-cliff, le wheel, le sdist et `sbom.json` |

## Vérifier une version publiée

Depuis n'importe quelle machine avec la CLI GitHub :

```bash
gh release download vX.Y.Z --repo amineutron/lyra --dir /tmp/lyra-vX.Y.Z
cd /tmp/lyra-vX.Y.Z
gh attestation verify lyra_assistant-X.Y.Z-py3-none-any.whl --owner amineutron
gh attestation verify lyra_assistant-X.Y.Z-py3-none-any.whl --owner amineutron \
  --predicate-type https://cyclonedx.org/bom
```

La première commande prouve l'origine du fichier, la seconde que `sbom.json` est bien
l'inventaire attesté pour lui. Le même wheel téléchargé depuis PyPI donne le même
résultat : l'attestation porte sur l'empreinte du fichier, pas sur l'endroit d'où il vient.

Le tag se vérifie avec `git tag -v vX.Y.Z` après avoir ajouté la clé publique du
mainteneur à son propre fichier `allowed_signers`.
