#!/usr/bin/env python3
"""Scenario de demonstration de Lyra en mode texte, joue par pexpect pour l'enregistrement.

1. une requete de lecture ("liste mes VMs") ;
2. une requete dangereuse ("supprime la vm test-vm") : Lyra demande confirmation, on repond n.
"""
import os
import sys
import time

import pexpect

LYRA = os.environ.get("LYRA_DIR", os.path.expanduser("~/dev/lyra"))
os.chdir(LYRA)


def say(text):
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(0.03)
    sys.stdout.write("\n")
    sys.stdout.flush()


def run(cmd, answers=(), timeout=120):
    say(f"$ {cmd}")
    child = pexpect.spawn("/bin/bash", ["-lc", cmd], encoding="utf-8", timeout=timeout, dimensions=(30, 100))
    child.logfile_read = sys.stdout
    for pattern, reply in answers:
        try:
            child.expect(pattern)
            time.sleep(1.2)
            child.sendline(reply)
        except pexpect.TIMEOUT:
            child.sendintr()
            break
    try:
        child.expect(pexpect.EOF)
    except pexpect.TIMEOUT:
        child.sendintr()
    child.close()
    sys.stdout.write("\n")
    sys.stdout.flush()
    time.sleep(1.5)


say("# Lyra, assistant DevOps vocal local : demo en mode texte")
time.sleep(1)
run('./run.sh -y "liste mes VMs"')
run('./run.sh "supprime la vm test-vm"', answers=[(r"\[O/n|\[T\]out|\(o/n\)|\[o/N|Executer", "n")])
say("# Aucune action sensible sans confirmation humaine.")
time.sleep(2)
