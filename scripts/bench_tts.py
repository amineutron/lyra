#!/usr/bin/env python3
"""Benchmark comparatif des voix TTS pour Lyra.

Mesure, pour chaque voix candidate, le temps de chargement, la latence de
synthese (a froid et a chaud), le RTF (real-time factor) et l'empreinte RAM,
puis genere des echantillons WAV a ecouter avant de choisir les voix retenues.

Usage:
    # Voix Piper (venv Lyra)
    .venv/bin/python scripts/bench_tts.py --engine piper

    # Kokoro (venv jetable, hors deps Lyra)
    <venv-kokoro>/bin/python scripts/bench_tts.py --engine kokoro \
        --kokoro-dir <dir contenant kokoro-v1.0.onnx et voices-v1.0.bin>

    # Tableau final (fusionne tous les results_*.json)
    .venv/bin/python scripts/bench_tts.py --report
"""

import argparse
import json
import sys
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"
SAMPLES_DIR = MODELS_DIR / "bench_samples"

PHRASES = {
    "courte": "La machine virtuelle preprod-01 est demarree, adresse 192.168.122.146.",
    "longue": (
        "J'ai termine la sauvegarde complete de tes machines virtuelles. "
        "Trois snapshots ont ete crees, la verification d'integrite est passee "
        "sans erreur, et l'espace disque restant sur le volume de stockage "
        "est de quarante-deux gigaoctets. Veux-tu que je lance le nettoyage "
        "des anciennes archives maintenant ?"
    ),
}

WARM_RUNS = 3


def rss_mb() -> float:
    """RSS du processus courant en Mo (lecture /proc, Linux uniquement)."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def write_wav(path: Path, audio_int16: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(audio_int16)


def bench_voice(name: str, synth_fn, sample_rate: int, load_s: float,
                load_ram_mb: float, size_mb: float) -> dict:
    """Mesure une voix : synth_fn(text) -> bytes PCM int16 mono."""
    result = {
        "voice": name,
        "load_s": round(load_s, 2),
        "load_ram_mb": round(load_ram_mb, 1),
        "size_mb": round(size_mb, 1),
        "phrases": {},
    }
    for label, text in PHRASES.items():
        t0 = time.perf_counter()
        audio = synth_fn(text)
        cold_s = time.perf_counter() - t0

        warm_times = []
        for _ in range(WARM_RUNS):
            t0 = time.perf_counter()
            audio = synth_fn(text)
            warm_times.append(time.perf_counter() - t0)
        warm_s = sum(warm_times) / len(warm_times)

        duration_s = len(audio) / 2 / sample_rate
        wav_path = SAMPLES_DIR / f"{name}_{label}.wav"
        write_wav(wav_path, audio, sample_rate)

        result["phrases"][label] = {
            "cold_s": round(cold_s, 3),
            "warm_s": round(warm_s, 3),
            "audio_s": round(duration_s, 2),
            "rtf": round(warm_s / duration_s, 3),
            "wav": str(wav_path),
        }
    return result


def bench_piper() -> list[dict]:
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    results = []
    for onnx in sorted(MODELS_DIR.glob("*.onnx")):
        meta = json.loads((onnx.parent / f"{onnx.name}.json").read_text())
        speaker_map = meta.get("speaker_id_map") or {"default": 0}
        sample_rate = meta["audio"]["sample_rate"]
        size_mb = onnx.stat().st_size / 1e6

        ram_before = rss_mb()
        t0 = time.perf_counter()
        voice = PiperVoice.load(str(onnx))
        load_s = time.perf_counter() - t0
        load_ram = rss_mb() - ram_before

        # Certains modeles (mls) ont 100+ speakers : on ne bench que les 2 premiers
        speakers = sorted(speaker_map.items(), key=lambda kv: kv[1])[:2]
        for speaker_name, speaker_id in speakers:
            syn_config = SynthesisConfig(speaker_id=speaker_id)

            def synth(text: str) -> bytes:
                chunks = [c.audio_int16_bytes for c in voice.synthesize(text, syn_config)]
                return b"".join(chunks)

            label = onnx.stem.replace("fr_FR-", "")
            if len(speaker_map) > 1:
                label = f"{label}-{speaker_name}"
            print(f"[piper] {label}...", file=sys.stderr)
            results.append(bench_voice(label, synth, sample_rate, load_s, load_ram, size_mb))
            load_s = 0.0  # modele partage entre speakers, compte une seule fois
            load_ram = 0.0
    return results


def bench_kokoro(kokoro_dir: Path) -> list[dict]:
    import numpy as np
    from kokoro_onnx import Kokoro
    from kokoro_onnx.config import EspeakConfig

    model = kokoro_dir / "kokoro-v1.0.onnx"
    voices = kokoro_dir / "voices-v1.0.bin"
    size_mb = model.stat().st_size / 1e6

    # La lib espeak embarquee (espeakng_loader) a un data path de build casse :
    # on utilise l'espeak-ng systeme.
    espeak = EspeakConfig(lib_path="/usr/lib64/libespeak-ng.so.1",
                          data_path="/usr/share/espeak-ng-data")

    ram_before = rss_mb()
    t0 = time.perf_counter()
    kokoro = Kokoro(str(model), str(voices), espeak_config=espeak)
    load_s = time.perf_counter() - t0
    load_ram = rss_mb() - ram_before

    def synth(text: str) -> bytes:
        samples, sr = kokoro.create(text, voice="ff_siwis", speed=1.0, lang="fr-fr")
        synth.sample_rate = sr
        return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

    # premier appel pour connaitre le sample rate reel
    synth("test")
    print("[kokoro] ff_siwis...", file=sys.stderr)
    return [bench_voice("kokoro-ff_siwis", synth, synth.sample_rate, load_s, load_ram, size_mb)]


def print_report() -> None:
    results = []
    for f in sorted(SAMPLES_DIR.glob("results_*.json")):
        results.extend(json.loads(f.read_text()))
    if not results:
        print("Aucun results_*.json trouve. Lancer d'abord le benchmark.")
        return

    header = (f"{'Voix':<22} {'Taille':>7} {'Charge':>7} {'RAM':>7} "
              f"{'Court chaud':>11} {'Long chaud':>10} {'RTF':>6}")
    print(header)
    print("-" * len(header))
    for r in results:
        court = r["phrases"]["courte"]
        long_ = r["phrases"]["longue"]
        load = f"{r['load_s']}s" if r["load_s"] else "(part.)"
        ram = f"{r['load_ram_mb']:.0f}Mo" if r["load_ram_mb"] else "(part.)"
        print(f"{r['voice']:<22} {r['size_mb']:>5.0f}Mo {load:>7} {ram:>7} "
              f"{court['warm_s']:>10.3f}s {long_['warm_s']:>9.3f}s {long_['rtf']:>6.3f}")
    print(f"\nEchantillons: {SAMPLES_DIR}/")
    print("Ecoute: aplay <fichier>.wav")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["piper", "kokoro"])
    parser.add_argument("--kokoro-dir", type=Path, help="Dossier des fichiers modele Kokoro")
    parser.add_argument("--report", action="store_true", help="Affiche le tableau fusionne")
    args = parser.parse_args()

    if args.report:
        print_report()
        return
    if not args.engine:
        parser.error("--engine requis (ou --report)")

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    if args.engine == "piper":
        results = bench_piper()
    else:
        if not args.kokoro_dir:
            parser.error("--kokoro-dir requis avec --engine kokoro")
        results = bench_kokoro(args.kokoro_dir)

    out = SAMPLES_DIR / f"results_{args.engine}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Resultats ecrits dans {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
