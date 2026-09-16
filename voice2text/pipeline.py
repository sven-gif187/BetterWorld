"""
╔══════════════════════════════════════════════════════════════╗
║  ABLAUF – Quelle rein, Transkript raus                       ║
╚══════════════════════════════════════════════════════════════╝

Der eine Weg, den Oberfläche und Kommandozeile gemeinsam gehen:

    Datei oder Link
        → Ausschnitt bestimmen (Start / Ende / Dauer)
        → Tonspur holen (ffmpeg, bei Links vorher yt-dlp)
        → Spracherkennung (Whisper)
        → Transkript mit Zeitstempeln des Originals
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import media
from .timecode import format_hms, parse_url_time, resolve_range
from .transcribe import Transcript, transcribe

__all__ = ["Job", "run_job", "safe_filename", "save_all_formats"]

ProgressFn = Callable[[float | None, str], None]


@dataclass
class Job:
    """Ein Transkriptions-Auftrag."""

    source: str                       # Dateipfad oder Link
    start: str | float | None = None  # "12:30", 750, None
    end: str | float | None = None
    duration: str | float | None = None
    backend: str = "auto"
    model: str = "small"
    language: str | None = None       # "de", "en", None = automatisch
    cookies_from_browser: str | None = None
    sprecher: bool = False            # wer sagt was? (braucht pyannote.audio)
    sprecherzahl: int | None = None   # bekannte Anzahl hilft der Erkennung
    uebersetzen_nach: str | None = None  # "en", "de", … oder None = nicht übersetzen


def safe_filename(name: str, fallback: str = "transkript") -> str:
    """Macht aus einem Videotitel einen brauchbaren Dateinamen."""
    cleaned = re.sub(r"[^\w\s.-]", "", str(name), flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] or fallback


def run_job(job: Job, progress: ProgressFn | None = None) -> Transcript:
    """Führt einen Auftrag von Anfang bis Ende aus."""
    report: ProgressFn = progress or (lambda share, message: None)

    source = str(job.source).strip()
    if not source:
        raise ValueError("Es wurde keine Quelle angegeben (Datei oder Link).")

    start, duration = resolve_range(job.start, job.end, job.duration)

    # Kein Start angegeben? Dann schauen wir, ob der Link selbst einen mitbringt
    # (z. B. …?t=90 – so kopiert YouTube die Stelle, an der man gerade war).
    if start is None and media.looks_like_url(source):
        from_link = parse_url_time(source)
        if from_link:
            start = from_link
            report(None, f"🔗 Sprungmarke aus dem Link übernommen: ab {format_hms(start)}")

    if start is not None or duration is not None:
        von = format_hms(start or 0)
        bis = format_hms((start or 0) + duration) if duration else "Ende"
        report(None, f"✂️ Ausschnitt: {von} → {bis}")

    # Ins Englische kann Whisper selbst übersetzen – kostenlos, offline und
    # mit erhaltenen Zeitstempeln. Nur für andere Zielsprachen braucht es
    # hinterher einen echten Übersetzer.
    ziel = None
    if job.uebersetzen_nach:
        from .uebersetzung import sprachkuerzel, sprachname
        ziel = sprachkuerzel(job.uebersetzen_nach)
    direkt_englisch = ziel == "en"
    if direkt_englisch:
        report(None, "🌍 Zielsprache Englisch – das erledigt Whisper gleich mit.")

    report(None, "📥 Quelle wird vorbereitet …")
    prepared = media.prepare_source(
        source,
        start=start,
        duration=duration,
        progress=lambda message: report(None, message),
        cookies_from_browser=job.cookies_from_browser,
    )

    try:
        if prepared.duration:
            report(None, f"🎧 {format_hms(prepared.duration)} Ton bereit – jetzt kommt die Spracherkennung.")
        result = transcribe(
            prepared.audio_path,
            backend=job.backend,
            model=job.model,
            language=job.language,
            offset=prepared.offset,
            title=prepared.title,
            origin=prepared.origin,
            duration=prepared.duration,
            progress=report,
            task="translate" if direkt_englisch else "transcribe",
        )

        if job.sprecher:
            _sprecher_zuordnen(job, prepared, result, report)
    finally:
        prepared.cleanup()

    if ziel and not direkt_englisch:
        _uebersetzen_anhaengen(result, ziel, report)
    elif direkt_englisch:
        result.translation_language = "Englisch"

    words = len(result.text.split())
    schluss = f"✅ Fertig: {len(result.segments)} Abschnitte · {words} Wörter"
    if result.hat_sprecher:
        schluss += f" · {len({s.speaker for s in result.segments if s.speaker})} Sprecher"
    if result.translation_language:
        schluss += f" · übersetzt nach {result.translation_language}"
    report(1.0, schluss)
    return result


def _uebersetzen_anhaengen(result: Transcript, ziel: str, report: ProgressFn) -> None:
    """
    Übersetzt ein fertiges Transkript nachträglich.

    Scheitert das, bleibt das Transkript stehen – die Arbeit der
    Spracherkennung ist zu teuer, um sie an einer fehlenden
    Übersetzung wegzuwerfen.
    """
    from .uebersetzung import UebersetzungError, sprachname, uebersetzen

    try:
        result.translation = uebersetzen(
            result.to_text(with_timestamps=False),
            nach=ziel,
            von=result.language,
            progress=report,
        )
        result.translation_language = sprachname(ziel)
    except UebersetzungError as exc:
        report(None, f"⚠️ Übersetzung übersprungen: {str(exc).splitlines()[0]}")


def _sprecher_zuordnen(job: Job, prepared, result: Transcript, report: ProgressFn) -> None:
    """
    Hängt die Sprecher-Erkennung an ein fertiges Transkript.

    Schlägt sie fehl, ist das kein Grund, die ganze Arbeit wegzuwerfen –
    das Transkript steht ja schon. Es gibt dann nur eine Meldung und
    weiter geht es ohne Namen.
    """
    from .sprecher import SprecherError, diarisieren, zuordnen

    try:
        abschnitte = diarisieren(
            prepared.audio_path,
            sprecherzahl=job.sprecherzahl,
            progress=report,
        )
    except SprecherError as exc:
        report(None, f"⚠️ Sprecher-Erkennung übersprungen: {str(exc).splitlines()[0]}")
        return

    # Die Erkennung rechnet ab Null, das Transkript ab dem Startpunkt im
    # Original – beide müssen auf dieselbe Zeitachse, sonst passt nichts.
    if prepared.offset:
        abschnitte = [
            type(a)(a.start + prepared.offset, a.end + prepared.offset, a.sprecher)
            for a in abschnitte
        ]

    zuordnen(result.segments, abschnitte)


def save_all_formats(transcript: Transcript, folder: str | Path, stem: str | None = None) -> list[Path]:
    """Legt Transkript als .txt, .srt, .vtt und .md im Ausgabeordner ab."""
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = safe_filename(stem or transcript.title or "transkript")
    written = []
    for suffix in (".txt", ".srt", ".vtt", ".md"):
        written.append(transcript.export(folder / f"{base}_{stamp}{suffix}"))
    return written
