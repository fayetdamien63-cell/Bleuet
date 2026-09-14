"""Point d'entrée CLI : chaque brique est testable isolément.

    bleuet devices          # lister les périphériques audio
    bleuet wakeword         # tester le mot de réveil seul
    bleuet record out.wav   # tester l'enregistrement seul
    bleuet stt out.wav      # tester la transcription seule
    bleuet tts "bonjour"    # tester la synthèse seule
    bleuet index            # (ré)indexer les documents RAG
    bleuet context          # afficher le contexte du jour (sans appeler Claude)
    bleuet ask "…"          # question en texte -> réponse texte
    bleuet say "…"          # question en texte -> réponse parlée
    bleuet run              # pipeline complet
    bleuet serve            # API HTTP
"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .logging_setup import get_logger, setup_logging

log = get_logger("bleuet.cli")


def cmd_devices(args, cfg: Config) -> int:  # noqa: ARG001
    from .audio.capture import list_devices

    print(list_devices())
    return 0


def cmd_wakeword(args, cfg: Config) -> int:  # noqa: ARG001
    from .audio.capture import AudioConfig, stream_chunks
    from .wakeword.detector import WakeWordConfig, WakeWordDetector

    audio = AudioConfig.from_config(cfg)
    detector = WakeWordDetector(WakeWordConfig.from_config(cfg), audio.sample_rate)
    print("Parle : dis le mot de réveil. Ctrl+C pour arrêter.")
    detector.listen(
        stream_chunks(audio),
        on_detect=lambda name, score: print(f"  -> déclenché par {name} ({score:.3f})"),
    )
    return 0


def cmd_record(args, cfg: Config) -> int:
    from .audio.capture import AudioConfig, record_until_silence, save_wav

    audio = AudioConfig.from_config(cfg)
    print("Parle maintenant…")
    samples = record_until_silence(audio)
    path = save_wav(samples, args.output, audio.sample_rate)
    print(f"Enregistré : {path}")
    return 0


def cmd_stt(args, cfg: Config) -> int:
    from .audio.capture import AudioConfig, load_wav, record_until_silence
    from .stt.factory import build_transcriber

    audio = AudioConfig.from_config(cfg)
    transcriber = build_transcriber(cfg)
    if args.wav:
        samples = load_wav(args.wav, audio.sample_rate)
    else:
        print("Parle maintenant…")
        samples = record_until_silence(audio)
    result = transcriber.transcribe(samples, audio.sample_rate)
    print(f"Transcription : {result.text}")
    return 0


def cmd_tts(args, cfg: Config) -> int:
    from .tts.factory import build_speaker

    path = build_speaker(cfg).speak(args.text)
    if path:
        print(f"Audio : {path}")
    return 0


def cmd_index(args, cfg: Config) -> int:  # noqa: ARG001
    from .rag.store import build_knowledge_store

    count = build_knowledge_store(cfg).index()
    print(f"{count} passage(s) indexé(s).")
    return 0


def cmd_search(args, cfg: Config) -> int:
    from .rag.store import build_knowledge_store

    chunks = build_knowledge_store(cfg).search(args.query, cfg.get("rag.top_k", 3))
    if not chunks:
        print("Aucun passage trouvé.")
    for chunk in chunks:
        print(f"\n--- {chunk.doc} (score {chunk.score:.2f}) ---\n{chunk.text}")
    return 0


def cmd_context(args, cfg: Config) -> int:
    from .context.calendar_provider import build_calendar_provider
    from .context.schedules import build_schedule_store
    from .context.weather import build_weather_provider
    from .orchestrator.prompt import build_system_prompt
    from .rag.store import build_knowledge_store

    stable, variable = build_system_prompt(
        args.question or "",
        weather=build_weather_provider(cfg),
        calendar=build_calendar_provider(cfg),
        schedules=build_schedule_store(cfg),
        knowledge=build_knowledge_store(cfg) if cfg.get("rag.enabled", True) else None,
        top_k=cfg.get("rag.top_k", 3),
    )
    print("=== Instructions (bloc stable, mis en cache) ===")
    print(stable)
    print("=== Contexte du jour (bloc variable) ===")
    print(variable)
    return 0


def cmd_ask(args, cfg: Config) -> int:
    from .orchestrator.pipeline import Orchestrator

    answer = Orchestrator(cfg).answer(args.question)
    print(f"\n{answer.text}\n")
    return 0


def cmd_say(args, cfg: Config) -> int:
    from .orchestrator.pipeline import Orchestrator
    from .tts.factory import build_speaker

    answer = Orchestrator(cfg).answer(args.question)
    build_speaker(cfg).speak(answer.text)
    return 0


def cmd_run(args, cfg: Config) -> int:  # noqa: ARG001
    from .assistant import Assistant

    try:
        Assistant(cfg).run()
    except KeyboardInterrupt:
        print("\nArrêt.")
    return 0


def cmd_serve(args, cfg: Config) -> int:
    import uvicorn

    from .server.app import create_app

    uvicorn.run(
        create_app(cfg),
        host=args.host or cfg.get("server.host", "127.0.0.1"),
        port=args.port or cfg.get("server.port", 8000),
    )
    return 0


def cmd_download_models(args, cfg: Config) -> int:  # noqa: ARG001
    from .wakeword.detector import download_pretrained_models

    download_pretrained_models()
    print("Modèles openWakeWord téléchargés.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bleuet", description="Assistant vocal familial")
    parser.add_argument("--config", help="chemin vers config.yaml")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING…")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="lister les périphériques audio").set_defaults(func=cmd_devices)
    subparsers.add_parser("wakeword", help="tester le mot de réveil").set_defaults(func=cmd_wakeword)

    record = subparsers.add_parser("record", help="enregistrer jusqu'au silence")
    record.add_argument("output", nargs="?", default="data/last_question.wav")
    record.set_defaults(func=cmd_record)

    stt = subparsers.add_parser("stt", help="transcrire un wav (ou le micro)")
    stt.add_argument("wav", nargs="?", help="fichier wav 16 kHz mono ; absent = micro")
    stt.set_defaults(func=cmd_stt)

    tts = subparsers.add_parser("tts", help="synthétiser une phrase")
    tts.add_argument("text")
    tts.set_defaults(func=cmd_tts)

    subparsers.add_parser("index", help="(ré)indexer data/knowledge").set_defaults(func=cmd_index)

    search = subparsers.add_parser("search", help="tester la recherche RAG")
    search.add_argument("query")
    search.set_defaults(func=cmd_search)

    context = subparsers.add_parser("context", help="afficher le prompt du jour")
    context.add_argument("question", nargs="?", default="")
    context.set_defaults(func=cmd_context)

    ask = subparsers.add_parser("ask", help="poser une question en texte")
    ask.add_argument("question")
    ask.set_defaults(func=cmd_ask)

    say = subparsers.add_parser("say", help="poser une question en texte, réponse parlée")
    say.add_argument("question")
    say.set_defaults(func=cmd_say)

    subparsers.add_parser("run", help="pipeline vocal complet").set_defaults(func=cmd_run)

    serve = subparsers.add_parser("serve", help="lancer l'API HTTP")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=cmd_serve)

    subparsers.add_parser(
        "download-models", help="télécharger les modèles openWakeWord"
    ).set_defaults(func=cmd_download_models)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    cfg = Config.load(args.config)
    log.debug("configuration chargée depuis %s", cfg.path)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
