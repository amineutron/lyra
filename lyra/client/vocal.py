"""
Lyra Client - Mode vocal branche sur le demon.

Le client ne fait que : capture micro + STT, envoi du texte au demon,
TTS de la reponse. Le demon reste seul proprietaire du pipeline (modeles
deja charges, session multi-tours, confirmations). Les confirmations sont
posees a voix haute ; la reponse parlee est normalisee par vocal_text
(jamais de confirmation implicite) puis tranchee par le demon, qui exige un
"oui" explicite pour les actions dangereuses.

Retourne -1 si le demon ou l'interface vocale est indisponible : l'appelant
bascule alors sur le mode standalone historique.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from lyra.client.launcher import ensure_daemon
from lyra.client.render import render_output, render_progress
from lyra.client.speech_fr import confirm_question, humanize_for_speech
from lyra.client.vocal_text import (
    ANSWER_NO,
    interpret_confirmation,
    spoken_text,
)
from lyra.core.constants import DESTRUCTIVE_TOOLS
from lyra.daemon.protocol import ChannelClosed, LineChannel
from modules import ui

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CONFIRM_RETRIES = 2  # reecoutes si la reponse est vide ou ambigue, puis refus
QUIT_WORDS = ("quit", "stop", "exit", "q", "quitter", "au revoir")


def _load_voice(user_settings):
    """Construit VoiceInterface depuis config.yaml. None si indisponible."""
    try:
        import yaml

        from modules.audio import AudioConfig, VoiceInterface

        with open(REPO_ROOT / "config.yaml") as f:
            cfg = yaml.safe_load(f)
        audio_cfg = cfg.get("audio", {})
        stt_cfg = cfg.get("stt", {})
        tts_cfg = user_settings.merged_tts(cfg.get("tts", {}))
        audio_config = AudioConfig(
            sample_rate=audio_cfg.get("sample_rate", 16000),
            channels=audio_cfg.get("channels", 1),
            silence_threshold=audio_cfg.get("silence_threshold", 0.01),
            silence_duration=audio_cfg.get("silence_duration", 1.0),
            input_device=audio_cfg.get("input_device"),
            output_device=audio_cfg.get("output_device"),
        )
        ui.print_info("Chargement du modele STT (Whisper)...")
        voice = VoiceInterface(
            stt_model=stt_cfg.get("model", "base"),
            tts_model=str(REPO_ROOT / "models" / f"{tts_cfg.get('model', 'fr_FR-upmc-medium')}.onnx"),
            language=stt_cfg.get("language", "fr"),
            device=stt_cfg.get("device", "cuda"),
            compute_type=stt_cfg.get("compute_type", "float16"),
            audio_config=audio_config,
            tts_speaker_id=int(tts_cfg.get("speaker_id", 0)),
            tts_length_scale=float(tts_cfg.get("length_scale", 1.0)),
        )
        ui.print_success("Interface vocale prete")
        return voice
    except Exception as e:  # noqa: BLE001 - audio/modeles : repli standalone
        ui.print_warning(f"Mode vocal indisponible: {e}")
        return None


def _speak(voice, text: Optional[str]) -> None:
    if not text:
        return
    try:
        voice.speak(text)
    except Exception as e:  # noqa: BLE001 - un TTS en panne ne bloque pas Lyra
        ui.print_warning(f"Synthese vocale en echec: {e}")


def _ask_by_voice(voice, message: dict) -> Optional[str]:
    """Pose un ask a voix haute et renvoie la valeur a transmettre au demon,
    ou None pour annuler."""
    kind = message.get("kind", "input")
    prompt = message.get("prompt", "")
    payload = message.get("payload", {})
    danger = bool(payload.get("danger") or payload.get("dangerous"))

    print(f"\n{ui.Colors.CYAN}{prompt}{ui.Colors.RESET}", flush=True)
    tool = payload.get("tool")
    if kind == "confirm" and tool:
        # phrase lisible a la place du nom d'outil et du prompt technique
        destructive = str(tool).split(".")[-1] in DESTRUCTIVE_TOOLS
        spoken = confirm_question(str(tool), payload.get("arguments") or {},
                                  danger=danger, destructive=destructive)
    else:
        spoken = humanize_for_speech(prompt)

    if kind != "confirm":
        _speak(voice, spoken)
        answer = voice.listen().strip()
        return answer  # question libre : le texte transcrit tel quel

    for _ in range(CONFIRM_RETRIES + 1):
        _speak(voice, spoken)
        transcript = voice.listen()
        print(f">>> {transcript}", flush=True)
        value = interpret_confirmation(transcript, danger=danger)
        if value is not None:
            return value
        spoken = "Je n'ai pas compris. Oui ou non ?"
    _speak(voice, "Je n'ai pas de reponse claire, j'annule.")
    return ANSWER_NO


def _process_request(channel: LineChannel, voice, text: str, mode: str,
                     verbose: bool) -> str:
    """Meme contrat que repl._process_request : "done" ou "reconnect"."""
    try:
        channel.send({
            "type": "request",
            "text": text,
            "options": {"mode": mode, "yes": False, "verbose": verbose,
                        "interactive": True},
        })
        # La phrase "Je vais ... Tu confirmes ?" du demon precede le ask de
        # confirmation : on la retient et on ne la lit pas si une confirmation
        # decrite en francais suit (sinon elle est lue avant le message suivant).
        held: Optional[str] = None
        while True:
            message = channel.recv(timeout=600)
            mtype = message.get("type")
            if mtype == "output":
                render_output(message)
                _speak(voice, held)
                held = None
                to_say = spoken_text(message)
                if message.get("kind") == "lyra":
                    held = to_say
                else:
                    _speak(voice, to_say)
            elif mtype == "progress":
                render_progress(message, verbose=verbose)
            elif mtype == "busy":
                ui.print_info(message.get("text", "Lyra est occupee..."))
            elif mtype == "ask":
                if message.get("kind") == "confirm":
                    held = None
                else:
                    _speak(voice, held)
                    held = None
                answer = _ask_by_voice(voice, message)
                if answer is None:
                    ui.print_warning("Annule.")
                    return "reconnect"
                channel.send({"type": "answer", "value": answer})
            elif mtype == "result":
                _speak(voice, held)
                return "done"
            elif mtype == "error":
                _speak(voice, held)
                ui.print_error(message.get("text", "erreur protocole"))
                return "done"
    except KeyboardInterrupt:
        print()
        ui.print_warning("Requete annulee.")
        return "reconnect"
    except (ChannelClosed, TimeoutError, ValueError) as e:
        ui.print_error(f"Connexion au demon perdue: {e}")
        return "reconnect"


def _connect() -> Optional[LineChannel]:
    channel, _greeting = ensure_daemon(on_wait=lambda: None)
    if channel is None:
        return None
    try:
        channel.send({"type": "hello", "session": "default", "client": "vocal"})
        channel.recv(timeout=10)  # ready
        return channel
    except (ChannelClosed, TimeoutError, ValueError):
        channel.close()
        return None


def run_vocal(args) -> int:
    """Boucle vocale cliente du demon. -1 : repli standalone."""
    from lyra.core.settings import UserSettings

    user_settings = UserSettings()
    mode = "performance" if args.performance else user_settings.active_mode()

    channel = _connect()
    if channel is None:
        return -1
    voice = _load_voice(user_settings)
    if voice is None:
        channel.close()
        return -1

    ui.print_info("Mode vocal actif (via le demon). Dis \"stop\" pour quitter.")
    last_interrupt = 0.0
    while True:
        try:
            ui.print_info("Ecoute...")
            text = voice.listen().strip()
            if not text:
                continue
            print(f">>> {text}", flush=True)
            if text.lower().strip(" .!?") in QUIT_WORDS:
                _speak(voice, "Au revoir!")
                print("\nAu revoir!")
                channel.close()
                return 0
            if _process_request(channel, voice, text, mode, args.verbose) == "reconnect":
                channel.close()
                channel = _connect()
                if channel is None:
                    ui.print_error("Demon injoignable, relance lyra --vocal.")
                    return 1
        except KeyboardInterrupt:
            now = time.monotonic()
            if now - last_interrupt < 1.5:
                print("\nAu revoir!")
                channel.close()
                return 0
            last_interrupt = now
            print()
            ui.print_info("Ctrl+C a nouveau pour quitter")
