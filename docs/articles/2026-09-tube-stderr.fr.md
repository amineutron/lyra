# Un tube de 64 Ko a fige mon assistant : tout client MCP stdio doit vider stderr

*Mohamed-Amine Rouabah (amineutron), septembre 2026. Version de travail. Code et correctif : https://github.com/amineutron/lyra (AGPL-3.0), commit `2c3976c`. English version: [2026-09-tube-stderr.en.md](2026-09-tube-stderr.en.md).*

## Resume

Lyra est un assistant vocal local : un demon resident (socket Unix) qui pilote la domotique, des machines virtuelles et des sauvegardes a travers des serveurs MCP lances en sous-processus et relies en stdio. Le 26 septembre 2026, apres neuf heures de fonctionnement, le demon n'acceptait plus aucune connexion : 1 127 threads, dont 1 061 en attente, et `Too many open files` dans le journal. La cause tenait en une ligne : le client MCP lancait chaque serveur avec `stderr=subprocess.PIPE` et ne lisait ce tube qu'a la mort du processus. Le serveur Hue, qui journalise en INFO sur stderr, a rempli les 64 Ko du tube, s'est bloque en ecriture, a cesse de lire ses requetes, et l'appel en cours a garde pour toujours le verrou des outils. Le correctif est un thread qui vide stderr en continu dans un tampon de 50 lignes, avec un test qui reproduisait le blocage avant la correction. Cet article montre comment le trouver en cinq commandes `/proc`, et pourquoi la regle vaut pour tout client MCP stdio.

## 1. Contexte

Le demon de Lyra ecoute sur `~/.lyra/lyra.sock` (`socketserver.ThreadingUnixStreamServer` : un thread par connexion) et execute les appels d'outils sous un verrou global, un a la fois : le modele et les serveurs MCP ne sont pas concus pour le parallelisme. neutroncore, le tableau de bord du logement, passe par ce demon pour la TV, l'ampli et les lumieres, et interroge regulierement leur etat.

Les serveurs MCP sont des sous-processus. Le client (`MCPSessionClient`, `modules/mcp.py`) ecrit les requetes JSON-RPC sur leur stdin, lit les reponses sur leur stdout, et redirigeait leur stderr vers un troisieme tube.

## 2. Symptome

Plus rien ne repondait : ni la TV, ni les lumieres, ni le chat. Le processus etait vivant (`systemctl` : active), mais :

```
$ ss -xl | grep lyra.sock
u_str LISTEN 6  5  /home/.../.lyra/lyra.sock
```

File d'attente de 6 pour un maximum de 5 : le demon n'acceptait plus. Dans le journal, depuis 21:46, le thread qui ecrit l'etat du demon toutes les quelques secondes echouait en `OSError: [Errno 24] Too many open files`. La limite souple du processus etait de 1 024 descripteurs.

## 3. Diagnostic, sans debogueur

Tout se lit dans `/proc`.

**Ou sont les threads ?** `wchan` donne la fonction du noyau ou chaque thread dort :

```
for t in /proc/$PID/task/*; do cat $t/comm $t/wchan; echo; done | sort | uniq -c | sort -rn
```

1 061 threads `python` en `futex_do_wait` (ils attendent un verrou), et **un seul** en `anon_pipe_write` : il ecrit dans un tube plein et attend que quelqu'un lise.

**Sur quel descripteur ?** `/proc/<pid>/task/<tid>/syscall` donne l'appel systeme en cours et ses arguments (le premier est le descripteur) :

```
read -r nr fd _ < /proc/$PID/task/$TID/syscall   # nr=1 : write ; fd en hexadecimal
readlink /proc/$PID/fd/$((fd))                   # -> pipe:[43773]
```

**Qui tient l'autre bout ?** On cherche le meme `pipe:[inode]` chez les autres processus :

```
for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -q 'pipe:\[43773\]' && echo "$p $(tr '\0' ' ' < $p/cmdline)"; done
```

Le demon ecrivait une requete au serveur Hue (`hue_server.py`, lance depuis 8 h 51). Et le serveur Hue, lui aussi, avait un thread en `anon_pipe_write`, sur son descripteur 2, stderr. Sa table de descripteurs racontait le reste : le canal du protocole avait ete deplace hors des descripteurs standards (fd 6 et 7), fd 0 pointait sur `/dev/null`, et fd 1 et 2 allaient au meme tube, tenu par le demon sur son descripteur 20. Ce tube, le demon ne le lisait jamais.

## 4. Cause

Un interblocage classique, en trois temps :

1. Le client lance le serveur avec `stderr=subprocess.PIPE` et ne lit ce tube que si le serveur meurt, pour citer son message d'erreur.
2. Le serveur Hue journalise en INFO sur stderr (`logging.basicConfig`). En neuf heures, il a rempli la capacite du tube : 65 536 octets sous Linux par defaut. Son ecriture suivante bloque ; il ne lit plus stdin.
3. Le demon, qui lui envoie une requete, bloque a son tour en ecriture sur stdin, en tenant le verrou des outils. Chaque nouvelle requete de neutroncore ouvre une connexion et un thread qui attendent ce verrou. Au millier, plus de descripteur libre : le demon n'accepte plus rien.

Aucun des deux processus n'etait en panne. Chacun attendait que l'autre lise.

## 5. Correctif et test

Le client vide maintenant stderr en continu, dans un thread demon, et n'en garde que les 50 dernieres lignes, qui servent toujours a expliquer la mort d'un serveur :

```python
self._stderr_tail = collections.deque(maxlen=self.STDERR_TAIL_LINES)
threading.Thread(target=self._drain_stderr, args=(self._process.stderr, self._stderr_tail),
                 name=f"mcp-stderr-{self.name}", daemon=True).start()
```

Le test de regression (`tests/unit/test_mcp_session_stderr.py`) lance un faux serveur MCP qui ecrit environ 100 Ko sur stderr avant chaque reponse, et enchaine trois requetes. Avant le correctif, il echoue au bout du delai de 5 s ; apres, il passe en 0,2 s. Un second test verifie que la fin de stderr est bien citee quand le serveur meurt au demarrage.

## 6. La regle, pour tout client MCP stdio

Un serveur MCP a le droit d'ecrire sur stderr : c'est meme la seule sortie ou il peut journaliser sans corrompre le protocole, qui occupe stdout. Un client qui redirige ce stderr vers un tube doit donc le lire en continu, ou ne pas le rediriger du tout. Le client stdio du SDK officiel Python (`mcp.client.stdio`, version 2.2 verifiee) choisit la seconde option : il passe au sous-processus `stderr=errlog`, par defaut le `sys.stderr` du client. Les clients maison, comme l'etait celui de Lyra, sont les plus exposes.

Le piege est lent : il faut que le volume de journal depasse 64 Ko, ce qui prend des heures en usage leger et n'arrive jamais dans un test de quelques secondes.

> **Comment verifier chez vous.** Serveur MCP en cours d'execution, pid `$SRV` :
>
> ```
> ls -l /proc/$SRV/fd/2            # un pipe:[...] ? alors quelqu'un doit le lire
> cat /proc/$SRV/task/*/wchan | sort | uniq -c   # anon_pipe_write = bloque en ecriture
> ```
>
> Pour le reproduire volontairement : un serveur qui ecrit 100 Ko sur stderr a chaque requete (voir le test cite plus haut). Si votre client tient trois requetes, il vide stderr.

## 7. Limites

Un seul incident, sur une seule machine, avec un seul serveur bavard. Le correctif retire la cause, pas la fragilite qu'elle a revelee : le demon accepte encore un nombre illimite de connexions, qui attendent sans delai le verrou des outils ; un autre blocage durable d'un appel d'outil produirait la meme accumulation. Borner les connexions et donner un delai a l'attente du verrou restent a faire. Enfin, l'ecriture de la requete vers le serveur n'a toujours pas de delai propre : seule la lecture de la reponse en a un.

## Reproduire

```
git clone https://github.com/amineutron/lyra && cd lyra
git checkout 2c3976c~1 -- modules/mcp.py && .venv/bin/python -m pytest tests/unit/test_mcp_session_stderr.py   # echoue (delai)
git checkout 2c3976c -- modules/mcp.py && .venv/bin/python -m pytest tests/unit/test_mcp_session_stderr.py     # passe
```
