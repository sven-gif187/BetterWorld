"""
╔══════════════════════════════════════════════════════════════╗
║  MEDIEN – Ton aus Video holen, Online-Links anzapfen         ║
╚══════════════════════════════════════════════════════════════╝

Zwei Aufgaben:

  1. Aus einer lokalen Datei (mp4, mkv, mp3, m4a, …) die Tonspur als
     16-kHz-Mono-WAV herausschneiden – genau das mag Whisper am liebsten.

  2. Von einem Online-Link (YouTube & Co.) nur den Ausschnitt laden,
     der wirklich gebraucht wird. Wer eine Uhrzeit mitgibt, lädt keine
     zwei Stunden Video für 90 Sekunden Text.

Beides braucht ffmpeg. Wenn ffmpeg fehlt, gibt es eine klare Ansage
statt eines kryptischen Absturzes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .timecode import format_hms

__all__ = [
    "MediaError",
    "MediaSource",
    "find_ffmpeg",
    "ffmpeg_status",
    "probe_duration",
    "extract_audio",
    "split_audio",
    "looks_like_url",
    "prepare_source",
    "download_online_audio",
    "AUDIO_SUFFIXES",
    "VIDEO_SUFFIXES",
]

ProgressFn = Callable[[str], None]

VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".aiff"}

# 16 kHz Mono ist das Format, mit dem Whisper intern ohnehin rechnet.
SAMPLE_RATE = 16_000

_URL_RE = re.compile(r"^(https?|ftp)://", re.IGNORECASE)
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")


class MediaError(RuntimeError):
    """Etwas mit ffmpeg, yt-dlp oder der Quelldatei stimmt nicht."""


@dataclass
class MediaSource:
    """Fertig aufbereitetes Audio plus alles, was wir darüber wissen."""

    audio_path: Path
    title: str
    origin: str
    offset: float = 0.0          # Startpunkt im Original – für echte Zeitstempel
    duration: float | None = None
    tempdir: tempfile.TemporaryDirectory | None = None

    def cleanup(self) -> None:
        if self.tempdir is not None:
            self.tempdir.cleanup()
            self.tempdir = None


# ══════════════════════════════════════════════════════════════
# FFMPEG FINDEN
# ══════════════════════════════════════════════════════════════
def _imageio_ffmpeg() -> str | None:
    """pip install imageio-ffmpeg bringt eine fertige ffmpeg.exe mit."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def find_ffmpeg() -> str | None:
    """Pfad zu ffmpeg – aus FFMPEG_BIN, dem PATH oder von imageio-ffmpeg."""
    override = os.getenv("FFMPEG_BIN")
    if override and Path(override).exists():
        return override
    found = shutil.which("ffmpeg")
    if found:
        return found
    return _imageio_ffmpeg()


def find_ffprobe() -> str | None:
    override = os.getenv("FFPROBE_BIN")
    if override and Path(override).exists():
        return override
    return shutil.which("ffprobe")


def ensure_ffmpeg() -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise MediaError(
            "ffmpeg wurde nicht gefunden.\n\n"
            "Schnellste Lösung (funktioniert auf allen Systemen):\n"
            "    pip install imageio-ffmpeg\n\n"
            "Alternativ:\n"
            "    Windows : winget install Gyan.FFmpeg\n"
            "    macOS   : brew install ffmpeg\n"
            "    Linux   : sudo apt install ffmpeg"
        )
    return ffmpeg


def ffmpeg_status() -> str:
    """Kurze Statuszeile für die Oberfläche."""
    ffmpeg = find_ffmpeg()
    return f"✅ ffmpeg: {ffmpeg}" if ffmpeg else "❌ ffmpeg fehlt – bitte installieren"


def _run(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    """ffmpeg-Aufruf ohne aufpoppendes Konsolenfenster unter Windows."""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            creationflags=creationflags,
        )
    except FileNotFoundError as exc:
        raise MediaError(f"{what} fehlgeschlagen – Programm nicht gefunden: {cmd[0]}") from exc


# ══════════════════════════════════════════════════════════════
# LÄNGE MESSEN
# ══════════════════════════════════════════════════════════════
def probe_duration(path: str | Path) -> float | None:
    """Länge in Sekunden – erst ffprobe, sonst aus der ffmpeg-Ausgabe gelesen."""
    path = str(path)

    ffprobe = find_ffprobe()
    if ffprobe:
        # Der Pfad steht hinter "-i": sonst würde eine Datei, deren Name mit
        # einem Bindestrich beginnt, als Befehlsoption gelesen.
        result = _run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", "-i", path],
            "ffprobe",
        )
        text = (result.stdout or "").strip()
        try:
            return float(text)
        except ValueError:
            pass

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    result = _run([ffmpeg, "-i", path], "ffmpeg")
    match = _DURATION_RE.search(result.stderr or "")
    if match:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return None


# ══════════════════════════════════════════════════════════════
# TON HERAUSSCHNEIDEN
# ══════════════════════════════════════════════════════════════
def extract_audio(
    source: str | Path,
    target: str | Path,
    start: float | None = None,
    duration: float | None = None,
    progress: ProgressFn | None = None,
) -> Path:
    """
    Holt die Tonspur aus `source` und legt sie als 16-kHz-Mono-WAV ab.

    `start` und `duration` schneiden dabei direkt den gewünschten
    Ausschnitt heraus – ffmpeg springt vor dem Dekodieren dorthin,
    das geht auch bei langen Dateien in Sekunden.
    """
    ffmpeg = ensure_ffmpeg()
    source, target = str(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if progress:
        window = ""
        if start is not None or duration is not None:
            von = format_hms(start or 0)
            bis = format_hms((start or 0) + duration) if duration else "Ende"
            window = f" (Ausschnitt {von} → {bis})"
        progress(f"🎧 Tonspur wird extrahiert{window} …")

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]        # vor -i = schneller Sprung
    cmd += ["-i", source]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(target)]

    result = _run(cmd, "Audio-Extraktion")
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        detail = (result.stderr or "").strip().splitlines()
        hint = detail[-1] if detail else "keine Fehlermeldung"
        raise MediaError(f"Die Tonspur konnte nicht extrahiert werden: {hint}")
    return target


def split_audio(path: str | Path, chunk_seconds: float = 600.0) -> list[tuple[Path, float]]:
    """
    Zerlegt eine WAV-Datei in Häppchen von `chunk_seconds` Länge.

    Gebraucht wird das für die Cloud-Variante (OpenAI-API), die pro
    Anfrage nur ~25 MB annimmt. Rückgabe: [(datei, versatz_in_sekunden)].
    """
    path = Path(path)
    total = probe_duration(path)
    if total is None or total <= chunk_seconds:
        return [(path, 0.0)]

    chunks: list[tuple[Path, float]] = []
    offset = 0.0
    index = 0
    while offset < total:
        part = path.with_name(f"{path.stem}_teil{index:03d}.wav")
        extract_audio(path, part, start=offset, duration=min(chunk_seconds, total - offset))
        chunks.append((part, offset))
        offset += chunk_seconds
        index += 1
    return chunks


# ══════════════════════════════════════════════════════════════
# ONLINE-LINKS
# ══════════════════════════════════════════════════════════════
def looks_like_url(text: str) -> bool:
    return bool(_URL_RE.match(str(text).strip()))


def _newest_media_file(folder: Path) -> Path | None:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() != ".part"]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _download_with_module(
    url: str,
    workdir: Path,
    start: float | None,
    end: float | None,
    progress: ProgressFn | None,
    cookies_from_browser: str | None,
) -> tuple[Path, str, bool]:
    """Download über das yt-dlp-Python-Modul. Rückgabe: (datei, titel, geschnitten)."""
    import yt_dlp

    trimmed = False
    options: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 3,
    }

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        options["ffmpeg_location"] = str(Path(ffmpeg).parent)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)

    if start is not None or end is not None:
        try:
            ranges = yt_dlp.utils.download_range_func(
                None, [(start or 0.0, end if end is not None else float("inf"))]
            )
            options["download_ranges"] = ranges
            options["force_keyframes_at_cuts"] = True
            trimmed = True
        except AttributeError:
            # Sehr alte yt-dlp-Version: dann eben komplett laden und lokal schneiden.
            trimmed = False

    if progress:
        progress("🌐 Link wird geladen …" if not trimmed else "🌐 Nur der gewünschte Ausschnitt wird geladen …")

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    path: Path | None = None
    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        path = Path(downloads[0]["filepath"])
    if path is None or not path.exists():
        path = _newest_media_file(workdir)
    if path is None or not path.exists():
        raise MediaError("Der Download hat keine Datei hinterlassen.")

    title = info.get("title") or info.get("id") or url
    return path, str(title), trimmed


def _download_with_binary(
    url: str,
    workdir: Path,
    start: float | None,
    end: float | None,
    progress: ProgressFn | None,
) -> tuple[Path, str, bool]:
    """Notnagel: yt-dlp als Kommandozeilen-Programm."""
    binary = shutil.which("yt-dlp") or shutil.which("youtube-dl")
    if not binary:
        raise MediaError(
            "Für Online-Links wird yt-dlp gebraucht:\n\n"
            "    pip install yt-dlp\n\n"
            "Danach die App neu starten."
        )

    trimmed = False
    cmd = [binary, "-f", "bestaudio/best", "--no-playlist",
           "-o", str(workdir / "%(id)s.%(ext)s"), "--quiet", "--no-warnings"]
    if start is not None or end is not None:
        von = f"{start or 0:.2f}"
        bis = f"{end:.2f}" if end is not None else "inf"
        cmd += ["--download-sections", f"*{von}-{bis}", "--force-keyframes-at-cuts"]
        trimmed = True
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        cmd += ["--ffmpeg-location", str(Path(ffmpeg).parent)]
    cmd.append(url)

    if progress:
        progress("🌐 Link wird geladen (yt-dlp) …")
    result = _run(cmd, "yt-dlp")
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise MediaError("yt-dlp konnte den Link nicht laden: " + (detail[-1] if detail else "unbekannter Fehler"))

    path = _newest_media_file(workdir)
    if path is None:
        raise MediaError("Der Download hat keine Datei hinterlassen.")
    return path, path.stem, trimmed


def download_online_audio(
    url: str,
    workdir: Path,
    start: float | None = None,
    duration: float | None = None,
    progress: ProgressFn | None = None,
    cookies_from_browser: str | None = None,
) -> tuple[Path, str, bool]:
    """
    Lädt den Ton eines Online-Videos – wenn möglich nur den Ausschnitt.

    Rückgabe: (heruntergeladene_datei, titel, wurde_bereits_geschnitten)
    """
    end = None if duration is None else (start or 0.0) + duration
    try:
        return _download_with_module(url, workdir, start, end, progress, cookies_from_browser)
    except ImportError:
        return _download_with_binary(url, workdir, start, end, progress)
    except MediaError:
        raise
    except Exception as exc:                       # yt-dlp wirft eigene Fehlertypen
        message = str(exc).strip() or exc.__class__.__name__
        if "Sign in" in message or "cookies" in message.lower():
            message += (
                "\n\nTipp: Bei Videos mit Altersfreigabe oder Login hilft es, in den "
                "Einstellungen den Browser für Cookies zu hinterlegen."
            )
        raise MediaError(f"Der Link konnte nicht geladen werden:\n{message}") from exc


# ══════════════════════════════════════════════════════════════
# EINE QUELLE – EGAL OB DATEI ODER LINK
# ══════════════════════════════════════════════════════════════
def prepare_source(
    source: str | Path,
    start: float | None = None,
    duration: float | None = None,
    progress: ProgressFn | None = None,
    cookies_from_browser: str | None = None,
) -> MediaSource:
    """
    Macht aus irgendeiner Quelle fertiges Whisper-Futter.

    `source` darf eine lokale Datei **oder** ein Online-Link sein.
    Start und Dauer schneiden in beiden Fällen den gewünschten
    Ausschnitt heraus; die Zeitstempel im Transkript beziehen sich
    danach trotzdem auf das Original (siehe `MediaSource.offset`).
    """
    ensure_ffmpeg()
    tempdir = tempfile.TemporaryDirectory(prefix="voice2text_")
    workdir = Path(tempdir.name)
    target = workdir / "audio_16k.wav"

    try:
        if looks_like_url(str(source)):
            raw, title, trimmed = download_online_audio(
                str(source), workdir, start, duration, progress, cookies_from_browser
            )
            origin = str(source)
            if trimmed:
                # yt-dlp hat schon geschnitten – jetzt nur noch umwandeln.
                extract_audio(raw, target, progress=progress)
            else:
                extract_audio(raw, target, start=start, duration=duration, progress=progress)
            try:
                raw.unlink()
            except OSError:
                pass
        else:
            path = Path(source).expanduser()
            if not path.exists():
                raise MediaError(f"Datei nicht gefunden: {path}")
            extract_audio(path, target, start=start, duration=duration, progress=progress)
            title = path.stem
            origin = str(path)

        return MediaSource(
            audio_path=target,
            title=title,
            origin=origin,
            offset=start or 0.0,
            duration=probe_duration(target),
            tempdir=tempdir,
        )
    except Exception:
        tempdir.cleanup()
        raise
