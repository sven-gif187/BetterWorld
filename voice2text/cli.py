"""
╔══════════════════════════════════════════════════════════════╗
║  KOMMANDOZEILE – für alle, die keine Fenster brauchen        ║
╚══════════════════════════════════════════════════════════════╝

Beispiele:

    # ganzes Video transkribieren
    python -m voice2text video.mp4

    # nur von Minute 12:30 bis 14:00
    python -m voice2text video.mp4 --start 12:30 --ende 14:00

    # Online-Link ab einer bestimmten Stelle, 90 Sekunden lang
    python -m voice2text "https://www.youtube.com/watch?v=…" --start 1:05:20 --dauer 90

    # Link mit eingebauter Sprungmarke – Start wird automatisch übernommen
    python -m voice2text "https://youtu.be/abc?t=90" --dauer 60

    # als Untertitel speichern
    python -m voice2text video.mp4 --ausgabe untertitel.srt

    # Text vorlesen lassen
    python -m voice2text --sprich "Hallo Sven, das Transkript ist fertig."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import tts
from .media import ffmpeg_status
from .pipeline import Job, run_job, save_all_formats
from .timecode import format_hms
from .transcribe import LANGUAGES, MODELS, backend_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice2text",
        description="🎙️ Video, Audio oder Online-Link in lesbaren Text verwandeln.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("quelle", nargs="?", help="Dateipfad oder Online-Link")

    schnitt = parser.add_argument_group("Ausschnitt")
    schnitt.add_argument("--start", "-s", help="Startzeit, z. B. 12:30 · 1:05:20 · 90 · 1h2m3s")
    schnitt.add_argument("--ende", "-e", dest="ende", help="Endzeit (statt --dauer)")
    schnitt.add_argument("--dauer", "-d", help="Länge des Ausschnitts in Sekunden oder als Zeitangabe")

    erkennung = parser.add_argument_group("Erkennung")
    erkennung.add_argument("--modell", "-m", default="small", choices=list(MODELS),
                           help="Whisper-Modell (Standard: small)")
    erkennung.add_argument("--sprache", "-l", default="de",
                           help="Sprachkürzel wie de/en/fr, oder 'auto' (Standard: de)")
    erkennung.add_argument("--backend", "-b", default="auto",
                           choices=["auto", "faster-whisper", "whisper", "openai-api"],
                           help="Welcher Erkenner benutzt wird (Standard: auto)")
    erkennung.add_argument("--cookies", help="Browser für Cookies bei Login-Videos: chrome, firefox, edge …")

    ausgabe = parser.add_argument_group("Ausgabe")
    ausgabe.add_argument("--ausgabe", "-o", help="Zieldatei (.txt · .srt · .vtt · .md)")
    ausgabe.add_argument("--ordner", help="Alle vier Formate in diesen Ordner schreiben")
    ausgabe.add_argument("--zeitstempel", action="store_true", help="Zeitstempel mit ausgeben")
    ausgabe.add_argument("--still", action="store_true", help="Keine Fortschrittsmeldungen")

    extra = parser.add_argument_group("Sonstiges")
    extra.add_argument("--sprich", help="Diesen Text vorlesen (Text → Sprache)")
    extra.add_argument("--sprachdatei", help="Sprachausgabe in Datei speichern (.wav oder .mp3)")
    extra.add_argument("--status", action="store_true", help="Zeigt, was installiert ist")
    extra.add_argument("--oberflaeche", "--gui", action="store_true", dest="gui",
                       help="Grafische Oberfläche starten")
    return parser


def _print_status() -> None:
    print("🩺 Systemstatus")
    print("   " + ffmpeg_status())
    print("   " + backend_status())
    print("   " + tts.tts_status())
    try:
        import yt_dlp  # noqa: F401
        print("   ✅ Online-Links: yt-dlp bereit")
    except ImportError:
        print("   ⚠️ Online-Links brauchen yt-dlp (pip install yt-dlp)")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        from .app import main as gui_main
        gui_main()
        return 0

    if args.status:
        _print_status()
        return 0

    # ── Text → Sprache ────────────────────────────────────────
    if args.sprich:
        try:
            if args.sprachdatei:
                path = tts.save_speech(args.sprich, args.sprachdatei)
                print(f"💾 Gespeichert: {path}")
            else:
                tts.speak(args.sprich)
        except tts.TtsError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        return 0

    if not args.quelle:
        parser.print_help()
        return 1

    # ── Sprache → Text ────────────────────────────────────────
    sprache = None if str(args.sprache).lower() in ("auto", "automatisch", "") else args.sprache
    if sprache and sprache in LANGUAGES:          # auch "Deutsch" statt "de" erlauben
        sprache = LANGUAGES[sprache]

    def report(share, message):
        if args.still or not message:
            return
        prefix = f"[{share * 100:3.0f}%] " if isinstance(share, float) else "       "
        print(prefix + str(message), file=sys.stderr)

    job = Job(
        source=args.quelle,
        start=args.start,
        end=args.ende,
        duration=args.dauer,
        backend=args.backend,
        model=args.modell,
        language=sprache,
        cookies_from_browser=args.cookies,
    )

    try:
        transcript = run_job(job, progress=report)
    except Exception as exc:
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1

    if args.ausgabe:
        path = transcript.export(args.ausgabe, with_timestamps=args.zeitstempel)
        print(f"💾 Gespeichert: {path}")
    elif args.ordner:
        for path in save_all_formats(transcript, args.ordner):
            print(f"💾 {path}")
    else:
        print(transcript.to_text(with_timestamps=args.zeitstempel))

    if not args.still:
        info = f"🗣️ {transcript.language or '?'} · {len(transcript.segments)} Abschnitte"
        if transcript.duration:
            info += f" · {format_hms(transcript.duration)}"
        print(info, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
