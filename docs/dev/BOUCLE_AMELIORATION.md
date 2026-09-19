# La boucle d'amelioration mesuree

Methode utilisee le 2026-09-17 pour faire passer le banc des modeles de 5/21
a 21/21 avec `qwen2.5-coder:0.5b` (roadmap-github#72). Elle ne depend ni du
modele ni du sujet : elle sert des qu'on veut ameliorer un score mesurable
sans changer la production a l'aveugle.

## Le cycle

```
analyse de l'existant
   -> bench (graine fixe)
   -> 4-5 idees, chacune avec une HYPOTHESE D'IMPACT ecrite AVANT
   -> bench des idees : seules, par paires, toutes ensemble
   -> analyse : confirmees / infirmees / neutres, et POURQUOI les echecs restent
   -> recommencer tant que le seuil n'est pas atteint (ici 99 %)
```

Une iteration dure 10 a 40 minutes. Cinq ont suffi. Le socle d'une iteration
est l'ensemble des variantes retenues par les precedentes : on mesure ce que
chaque nouvelle idee ajoute a ce qui marche deja.

## Les regles, dans l'ordre ou elles ont compte

1. **Reparer le bench avant de mesurer.** Le premier chiffre etait 0/21 pour
   tous les modeles : une methode disparue, comptee en echec du modele. Un banc
   qui plante doit refuser de publier (`erreurs_techniques` -> pas de fichier),
   jamais se deguiser en resultat.

2. **Graine fixe, toujours.** Sans `LYRA_SEED`, le meme jeu donnait 4, 3 puis
   4 sur 7. A graine fixe, deux executions donnent le meme resultat : une
   difference de 1 est alors un signal, pas du bruit.

3. **Mesurer le mecanisme avant le modele.** Avant toute idee de prompt,
   verifier que le modele VOIT la bonne reponse : rang du bon outil dans les
   specs remontees, sans appeler le modele (20 secondes). Au depart, le bon
   outil etait montre pour 8 cas sur 21 et le premier essai n'en montrait
   qu'un : le score etait plafonne par le RAG, pas par le modele. Trois
   sessions avaient accuse le modele. Une idee sans effet mecanique ne merite
   pas de bench (`sans_registre`, ecartee en 20 secondes).

4. **Une idee = une variante, inactive par defaut.** `LYRA_EXP="a,b"` active
   exactement ces variantes ; la production ne change pas tant qu'on mesure.
   Le code d'une variante vit dans un module a part (`ephaistos_exp.py`) avec
   sa fonction pure et son test unitaire ; le branchement dans le pipeline
   tient en une ligne conditionnelle.

5. **Hypothese ecrite avant, chiffre apres.** Chaque variante est notee avec
   son impact suppose (fort / moyen / faible, et sur quels cas) avant le
   bench. Une hypothese infirmee vaut autant qu'une confirmee : `routage`,
   `index`, `consigne_onoff`, `deux_exemples`, `top5_direct` ont degrade,
   et on sait pourquoi.

6. **Seules, par paires, toutes ensemble.** `lexical` seule degrade (8/21)
   et forme la meilleure paire avec `top3_direct` (13/21). Sans les paires,
   elle aurait ete jetee. Inversement, en iteration 1, « tout ensemble »
   etait pire que la meilleure variante seule parce que la combinaison
   embarquait deux idees nuisibles.

7. **Lire la reponse brute et le prompt exact sur chaque echec restant.**
   C'est la seule facon de classer un echec : donnees (le bon outil n'est
   pas remonte), banc (la reponse est juste mais comptee fausse), modele (le
   bon outil est en tete et il repond autre chose). Chaque classe appelle un
   remede different, et l'iteration suivante cible la classe majoritaire.

8. **Score strict a cote du score tolerant.** Si le banc accepte des
   equivalences (`EQUIVALENCES`), il publie aussi le score strict
   (`reussis_strict`) : comparable aux iterations precedentes, et il rappelle
   que la table est une decision de banc, pas une amelioration du produit.
   Un cas irrealisable (outil inexistant) se corrige dans le banc, pas en
   « faisant passer » le modele.

9. **Retirer compte autant qu'ajouter.** La derniere iteration a gagne le
   dernier cas en supprimant une consigne jugee « neutre » trois iterations
   plus tot. Pour un petit modele, chaque phrase d'explication a coute ;
   chaque exemple tire des donnees a rapporte.

10. **Consigner au fil de l'eau.** Un commentaire d'issue par iteration
    (hypotheses AVANT, resultats APRES), un fichier de resultats par
    iteration dans `benchmarks/results/`, `BENCHMARKS.md` regenere. Le topo
    final s'ecrit tout seul.

## Outillage dans ce depot

| Piece | Role |
|---|---|
| `lyra/models/ephaistos_exp.py` | les variantes (`VARIANTES`), la configuration retenue (`DEFAUT`), `actives()` |
| `scripts/bench_boucle.py` | rejoue le banc pour chaque configuration ; `--socle`, `--variantes`, `--seulement`, `--iteration` |
| `tests/test_campaign_llm.py` | le banc des modeles (21 cas), `EQUIVALENCES`, score strict, refus de publier en panne |
| `scripts/gen_benchmarks_md.py` | `BENCHMARKS.md` : reference, variantes, une ligne par iteration |
| `benchmarks/README.md` | protocole, machine, graine, reserves |

```bash
# une iteration : socle = acquis, variantes = idees du jour
LYRA_SEED=42 .venv/bin/python scripts/bench_boucle.py --iteration 6 \
    --socle exemples_cibles,lexical --variantes idee_a,idee_b,idee_c

# rejouer des configurations precises
LYRA_SEED=42 .venv/bin/python scripts/bench_boucle.py --iteration 6 \
    --seulement "exemples_cibles;exemples_cibles,idee_a"

# mesurer le mecanisme (rang du bon outil) sans modele : voir la section
# « phase 0 » du topo Notion du 2026-09-17 ; a industrialiser (voir ci-dessous)
```

## Pieges rencontres

- **Mesurer sous charge.** Un `pytest` en parallele d'un bench a produit des
  timeouts publies comme latences. Une mesure = machine au repos, une seule
  chose a la fois. Les durees restent indicatives, les verdicts sont surs.
- **L'index derive de ses sources.** L'index v3 datait d'avant les
  declencheurs qu'il etait cense contenir ; et un regex (`[^E]+?`) privait
  38 outils sur 88 de leurs paraphrases sans que rien ne le signale. Verifier
  le contenu reel de l'index (les documents), pas la presence des collections.
- **Un chemin qui ignore les variantes.** Les modeles autres que 0.5b
  passaient par TOON, ou `analyze()` n'applique aucune variante : comparer
  « a configuration egale » exigeait de le savoir.
- **Une dependance installee a la main.** `rank_bm25` etait dans le venv et
  dans l'installeur, pas dans `uv.lock` : CI rouge, et une variante active
  par defaut aurait leve en production. Le code se degrade sans lever, le
  test fait `importorskip`.
- **Deux dictionnaires aux memes cles** (`triggers_map`, `examples_map`) :
  un patch par regex globale touche les deux. Patcher par plage.

## Ce que la methode ne garantit pas

- Elle optimise le score sur LE banc : 21 cas, 3 serveurs, formulations
  proches des regles. La generalisation se mesure sur un jeu tenu a l'ecart
  (paraphrases inedites, tous les serveurs), qui n'existe pas encore.
- Elle a ete reglee sur un modele (le 0.5b). Les autres en profitent
  (1b 8 -> 18, 3b 6 -> 18, 7b 6 -> 19) sans avoir ete cibles.
- Un seul run par configuration, a graine fixe : reproductible, mais pas une
  distribution. Changer de graine changerait des cas a la marge.

## Le second banc : ce que la boucle a appris le lendemain

Le jeu « hors regles » (`tests/cases_hors_regles.py`, 51 formulations inedites,
5 serveurs, controle mecanique contre les regles et l'index) a ete rejoue avec
la meme boucle le 2026-09-18 :

- **Le 21/21 ne generalisait pas** : 13/51 au depart. Quatre iterations :
  13 -> 14 -> 21 -> 26/51, puis plateau. Le rendement a ete porte par les
  **donnees** (paraphrases pour les 34 outils qui n'en avaient pas, index sans
  doublon, lexique des mots d'equipement), les reglages de code valant +1 a +3.
- **Le recall ne suffit pas** : en iteration 1 le bon outil est passe de 7 a 20
  fois en tete et le score n'a pas bouge. Sans exemple attache a la spec, un
  0.5b baptise l'outil avec un mot de la requete. Lire la reponse brute reste
  l'etape qui classe l'echec.
- **Une regle fausse est pire qu'un modele faux** : six regles repondaient a
  cote sur des phrases inedites, sans confirmation vocale en mode performance.
  Ecrire un jeu hors regles est aussi un test des regles.
- **Optimiser un jeu coute a l'autre** : la configuration hors regles fait 19/21
  sur le premier banc. Decider sur les deux jeux ensemble, et verifier ce que
  les regles interceptent en usage reel.
- **Sur du langage libre, la taille du modele compte** (0.5b 51 %, 3b 63 %,
  7b 71 %) alors qu'elle ne comptait pas sur le premier banc -- jusqu'a ce que
  le tri des specs soit assez sur pour decider a la place du modele.
- **Quand le tri est net, ne pas demander au modele.** Mesure sans modele : le
  rang 1 du tri, quand son score est net, etait le bon outil 27 fois sur 27.
  `outil_force_si_net` impose alors l'outil et laisse au modele les arguments et
  les cas ambigus. Avec les cartes de tri, c'est ce qui a mene le 0.5b de 39 a
  51/51 -- et le 1.5b ne faisait pas mieux que le 0.5b a configuration egale.
- **Le vote n'aide pas un modele systematique.** Trois appels sur trois ordres
  de specs ont degrade le score : le 0.5b n'est pas bruite, il est attire par
  le meme voisin a chaque fois. Corriger ce qu'on lui montre vaut mieux que
  le reinterroger.
- **Un jeu qui a servi a onze iterations n'est plus une mesure de
  generalisation**, meme sans copie de phrase : les cartes ont ete completees
  en regardant ses echecs. Le troisieme jeu, tenu a l'ecart, dira ce que vaut
  le 72/72.

## Le troisieme jeu : ce que valait le 72/72, et comment on repart

Le troisieme jeu (`tests/cases_hors_regles_2.py`, 100 phrases, ecrit apres la
boucle) a donne **56/100** en mesure unique a la configuration qui faisait
72/72 : un jeu itere mesure la boucle, pas le produit. La suite, le 2026-09-19
au soir, a fixe le protocole a trois jeux :

1. **Sceller le jeu suivant avant de toucher a quoi que ce soit.** Le
   quatrieme jeu (`tests/cases_hors_regles_3.py`, 50 phrases, vrais noms de
   machines, dix outils jamais mesures) a ete ecrit et controle AVANT les
   leviers ; le troisieme devient le jeu de developpement. Le controle du jeu
   a encore trouve trois regles fausses (corrigees, tests de regression).
2. **Des leviers qui ne dependent pas des phrases.** L'inventaire reel des
   machines (`vm_status` au demarrage du pipeline, ou `LYRA_VMS`) a la place
   d'un motif de nom ; un lexique de langue courante ecrit domaine par domaine
   (allumage, extinction, volume, lumiere, lecture, machines, sauvegardes) ;
   les memes verbes dans les cartes de tri. Mesure mecanique avant le banc :
   rang 1 pour 41 -> 60 cas sur 100, absents 13 -> 5.
3. **Le banc confirme le mecanisme** : 56 -> 58 / 64 / 64 seules, 67 / 66 / 68
   par paires, **70** les trois ensemble (it14) ; regression 21/21 et 50/51.
4. **Lire les echecs restants avec le classement automatique** : le 0.5b copie
   parfois l'entite en nom d'outil (`fedora_base` pour "reveille
   fedora-base") -> `outil_par_machine` (+2, comme prevu) ; une seconde table
   de mots ordinaires (+9) ; assouplir le critere net (seuil 1) est
   **infirme** (-4 : la precision mecanique 36/5 contre 29/2 l'annoncait, trois
   faux nets imposent trois mauvais outils). It15 : **82/100** sur le jeu 3.
5. **Une seule mesure du jeu scelle**, et c'est le seul chiffre qu'on publie
   comme generalisation : **41/50** sur le quatrieme jeu. Ses neuf echecs
   (sept confusions dont trois sur un nombre, deux questions d'etat lues comme
   des ordres) ont guide l'iteration 16 -- il ne sera donc pas remesure, et un
   **cinquieme jeu** a ete scelle avant d'ecrire une ligne.
6. **It16, la premiere iteration ou le mecanisme a refuse une idee avant le
   banc** : la premiere version de `nombres_tri` creait deux faux nets ("tu
   peux me mettre la tele ?" est un ordre poli, "combien de temps ... avec
   uptime" une commande) et faisait cibler `seek` par "trente pour cent" ;
   `scripts/bench_recall.py` l'a montre en vingt secondes, la version corrigee
   a une precision inchangee (38/2) et gagne 4 rangs 1. Le banc dit ensuite
   82 -> 83 sur le jeu 3 : les deux idees visaient les echecs du jeu 4, pas
   ceux du jeu 3, et le jeu 2 perd un cas (50/51 : "verifie l'integrite des
   sauvegardes ?" -- la question d'etat pousse `backup_status` devant
   `backup_verify`, qui n'est pas dans les cibles d'etat ; prochaine
   hypothese, pas de retouche apres coup). Cinquieme jeu, mesure unique :
   **35/50** -- six echecs sur dix cote Hue, deux noms de machines rendus
   comme des outils TV. Un jeu scelle mesure aussi la variance entre jeux :
   41/50 puis 35/50 pour deux configurations a un point d'ecart sur le jeu 3.

Pieges de ces deux iterations : un guetteur `until ! pgrep -f "<ligne du
banc>"` matche sa propre ligne de commande et ne rend jamais la main (guetter
un fichier marqueur) ; un mot ordinaire peut etre nuisible sur l'autre jeu
("point" -> status casse "point de restauration" = snapshot) : le recall
mecanique sur les deux jeux le voit en vingt secondes, avant le banc.

## A industrialiser

- Le releve de recall (rang du bon outil sans modele, precision du critere
  net) est un script de session : en faire `scripts/bench_recall.py` publie
  dans `benchmarks/`.
- Un cinquieme jeu, tenu a l'ecart a son tour, le jour ou le quatrieme aura
  servi a une iteration.
