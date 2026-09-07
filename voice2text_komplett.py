#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║   🎙️  VOICE2TEXT – Video und Sprache zu Text                         ║
║                                                                      ║
║   Alles in einer Datei. Speichern, doppelklicken, loslegen.          ║
╚══════════════════════════════════════════════════════════════════════╝

WAS DIESE DATEI KANN
────────────────────
  🎬  Video oder Tonaufnahme  →  geschriebener Text
  🌐  YouTube-Link            →  geschriebener Text
  ⏱️  Link mit Uhrzeit        →  nur diese Stelle, nicht das ganze Video
  💾  Speichern als Text, Untertitel oder Notiz
  🔊  Text wieder vorlesen lassen

  Läuft auf deinem Rechner. Kein Konto, keine Gebühr, keine Anmeldung.
  Der Ton verlässt deinen Computer nicht.


SO STARTEST DU
──────────────
  Windows :  Doppelklick auf diese Datei
  Mac     :  Rechtsklick → Öffnen mit → Python Launcher
  Konsole :  python voice2text_komplett.py

  Beim allerersten Start fehlen noch ein paar Bausteine. Die App fragt
  dich dann, ob sie sie holen darf – einfach "j" tippen und Enter.
  Das dauert ein paar Minuten und passiert nur ein einziges Mal.


DIESE DATEI WURDE ERZEUGT, NICHT VON HAND GESCHRIEBEN
──────────────────────────────────────────────────────
  Sie entsteht aus dem Ordner voice2text/ durch
      python werkzeug/einzeldatei_bauen.py
  Änderungen also bitte dort machen, nicht hier – hier wären sie beim
  nächsten Bauen wieder weg.

  Zuhause: https://github.com/sven-gif187/BetterWorld
  Lizenz:  GPL-3.0
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import itertools
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import parse_qs, urlparse


# ══════════════════════════════════════════════════════════════════════
# ERSTHILFE – fehlende Bausteine beim ersten Start nachinstallieren
# ══════════════════════════════════════════════════════════════════════
PFLICHT = [
    ("customtkinter", "customtkinter>=5.2.0", "das Fenster"),
    ("faster_whisper", "faster-whisper>=1.0.0", "die Spracherkennung"),
    ("imageio_ffmpeg", "imageio-ffmpeg>=0.4.9", "das Lesen von Videodateien"),
]
KUER = [
    ("yt_dlp", "yt-dlp>=2024.1.0", "YouTube-Links"),
    ("pyttsx3", "pyttsx3>=2.90", "das Vorlesen"),
    ("tkinterdnd2", "tkinterdnd2>=0.3.0", "Videos ins Fenster ziehen"),
]


def _fehlt(modul: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(modul) is None
    except (ImportError, ValueError, ModuleNotFoundError):
        return True


def ersthilfe() -> None:
    """
    Beim ersten Start fehlt noch alles. Statt mit einem unverständlichen
    Fehler abzustürzen, fragt die App höflich nach und holt es selbst.
    """
    fehlend = [(m, p, z) for m, p, z in PFLICHT + KUER if _fehlt(m)]
    if not fehlend:
        return

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   🎙️  VOICE2TEXT – erster Start                          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("  Es fehlen noch ein paar Bausteine:")
    print()
    for _modul, paket, zweck in fehlend:
        print(f"     • {paket.split('>=')[0]:<18} für {zweck}")
    print()
    print("  Das sind rund 100 MB. Es passiert nur dieses eine Mal.")
    print()

    if not sys.stdin or not sys.stdin.isatty():
        # Kein Mensch davor (Skript, Pipeline): nichts ungefragt installieren.
        print("  Von Hand:  pip install " + " ".join(p for _m, p, _z in fehlend))
        print()
        return

    try:
        antwort = input("  Jetzt holen? [J/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if antwort and antwort not in ("j", "ja", "y", "yes"):
        print()
        print("  Gut, dann nicht. Von Hand ginge es so:")
        print("     pip install " + " ".join(p for _m, p, _z in fehlend))
        print()
        input("  Enter zum Beenden ")
        sys.exit(0)

    print()
    print("  📦 Wird geholt – das dauert ein paar Minuten …")
    print()
    ergebnis = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade",
         *[p for _m, p, _z in fehlend]],
        check=False,
    )
    print()
    if ergebnis.returncode != 0:
        print("  ❌ Das hat nicht geklappt.")
        print()
        print("  Häufigste Ursachen:")
        print("     • keine Internetverbindung")
        print("     • pip ist veraltet:")
        print(f"       {Path(sys.executable).name} -m pip install --upgrade pip")
        print()
        input("  Enter zum Beenden ")
        sys.exit(1)

    print("  ✅ Fertig. Die App startet jetzt.")
    print()


# Muss laufen, BEVOR weiter unten die Fenster-Klassen gebaut werden –
# die brauchen customtkinter bereits beim Einlesen der Datei.
ersthilfe()



# ══════════════════════════════════════════════════════════════════════
# aus konfig.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  KONFIGURATION – die .env-Datei einlesen                     ║
╚══════════════════════════════════════════════════════════════╝

Schlüssel und Token gehören nicht in den Quelltext, sondern in eine
Datei namens `.env`, die nie auf GitHub landet:

    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    HUGGINGFACE_TOKEN=hf_...

Dieses Modul liest sie ein – ohne Zusatzpaket, damit die App auch dann
funktioniert, wenn python-dotenv nicht installiert ist.

Zwei Regeln, die man kennen sollte:

  • Echte Umgebungsvariablen haben Vorrang. Wer einen Schlüssel in der
    Konsole setzt, will ihn auch benutzen – die Datei überschreibt ihn nicht.
  • Werte werden niemals protokolliert. Was hier gelesen wird, taucht in
    keiner Meldung und in keinem Protokoll auf.
  • Variablen, die steuern, welche Programme und Bibliotheken geladen
    werden (PATH, LD_PRELOAD, PYTHONPATH …), werden aus einer Datei
    grundsätzlich nicht übernommen – siehe GESPERRTE_NAMEN.
"""


import os
from pathlib import Path

__all__ = [
    "env_datei_finden", "env_lesen", "env_laden",
    "gesetzte_schluessel", "GESPERRTE_NAMEN",
]

# Die Namen, auf die es ankommt – nur zur Anzeige, nie mit Wert.
BEKANNTE_SCHLUESSEL = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HUGGINGFACE_TOKEN",
    "HF_TOKEN",
)

# Diese Variablen werden aus einer .env NIEMALS übernommen.
#
# Der Grund: die App startet ffmpeg und yt-dlp als eigene Programme.
# Wer bestimmen kann, welche Bibliotheken dabei geladen werden oder wo
# nach Programmen gesucht wird, kann eigenen Code ausführen lassen.
# Und eine .env liegt nicht immer da, wo man sie vermutet – gesucht wird
# auch in den übergeordneten Ordnern, also womöglich in einem fremden
# Projekt, das man sich gerade heruntergeladen hat.
#
# Wer diese Variablen wirklich braucht, setzt sie in der Konsole. Von dort
# kommen sie aus einer bewussten Entscheidung, nicht aus einer Datei.
GESPERRTE_NAMEN = frozenset({
    # Programme und Bibliotheken finden
    "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    # Python selbst umbiegen
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONEXECUTABLE",
    "PYTHONWARNINGS", "PYTHONINSPECT",
    # Shell-Einsprungpunkte
    "BASH_ENV", "ENV", "IFS", "SHELL", "COMSPEC",
    # Unsere eigenen Programmpfade – zeigen direkt auf eine ausführbare Datei
    "FFMPEG_BIN", "FFPROBE_BIN",
})


def env_datei_finden(start: str | Path | None = None) -> Path | None:
    """
    Sucht die nächste `.env` – erst im Startverzeichnis, dann aufwärts.

    So findet sie sich auch dann, wenn die App aus einem Unterordner
    heraus gestartet wird. Gesucht wird höchstens fünf Ebenen weit,
    damit nicht versehentlich eine fremde Datei vom halben Dateisystem
    eingelesen wird.
    """
    kandidaten = []
    if start is not None:
        kandidaten.append(Path(start))
    kandidaten.append(Path.cwd())
    kandidaten.append(Path(__file__).resolve().parent.parent)

    for basis in kandidaten:
        basis = Path(basis).resolve()
        for ordner in [basis, *list(basis.parents)[:5]]:
            datei = ordner / ".env"
            if datei.is_file():
                return datei
    return None


def env_lesen(pfad: str | Path) -> dict[str, str]:
    """
    Liest eine .env-Datei und gibt die Paare zurück – ohne etwas zu setzen.

    Verstanden werden:
        KEY=wert
        export KEY=wert
        KEY="wert mit Leerzeichen"
        KEY=wert            # Kommentar dahinter wird abgeschnitten

    Kaputte Zeilen werden übersprungen statt zu einem Absturz zu führen.
    """
    werte: dict[str, str] = {}
    pfad = Path(pfad)
    try:
        inhalt = pfad.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return werte

    for zeile in inhalt.splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        if zeile.startswith("export "):
            zeile = zeile[len("export "):].lstrip()

        name, _, wert = zeile.partition("=")
        name = name.strip()
        if not name or not name.replace("_", "").replace(".", "").isalnum():
            continue

        wert = wert.strip()
        if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in ("'", '"'):
            wert = wert[1:-1]                  # Anführungszeichen gehören nicht zum Wert
        else:
            # Kommentar am Zeilenende abschneiden – aber nur mit Leerzeichen
            # davor, damit ein "#" im Schlüssel selbst erhalten bleibt.
            for trenner in (" #", "\t#"):
                if trenner in wert:
                    wert = wert.split(trenner, 1)[0].rstrip()
        werte[name] = wert
    return werte


def env_laden(pfad: str | Path | None = None, ueberschreiben: bool = False) -> list[str]:
    """
    Liest die .env und legt die Werte in die Umgebung.

    Rückgabe: die Namen der gesetzten Variablen – **ohne** die Werte,
    damit nichts Geheimes in einem Protokoll landen kann.
    """
    datei = Path(pfad) if pfad else env_datei_finden()
    if not datei or not Path(datei).is_file():
        return []

    gesetzt = []
    for name, wert in env_lesen(datei).items():
        if name.upper() in GESPERRTE_NAMEN:
            continue                           # siehe GESPERRTE_NAMEN oben
        if ueberschreiben or not os.getenv(name):
            os.environ[name] = wert
            gesetzt.append(name)
    return gesetzt


def gesetzte_schluessel() -> list[str]:
    """Welche der bekannten Schlüssel vorhanden sind – nur die Namen."""
    return [name for name in BEKANNTE_SCHLUESSEL if os.getenv(name)]



# ══════════════════════════════════════════════════════════════════════
# aus timecode.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  ZEITCODES – Zeitangaben lesen, rechnen und formatieren      ║
╚══════════════════════════════════════════════════════════════╝

Hier landet alles, was mit Zeit zu tun hat:

  • "1:23:45", "12:30", "90", "1h2m3s", "90s"  →  Sekunden
  • Sekunden                                    →  "00:01:30,500" (SRT)
  • YouTube-Link mit "?t=90"                    →  90.0

Kein externes Paket nötig – reine Standard-Bibliothek.
"""


import re
from urllib.parse import parse_qs, urlparse

__all__ = [
    "parse_timecode",
    "format_timestamp",
    "format_hms",
    "parse_url_time",
    "resolve_range",
]

# 1h2m3s / 90s / 90 / 2m
_HMS_RE = re.compile(
    r"^(?:(?P<h>\d+)\s*h)?"
    r"(?:(?P<m>\d+)\s*m(?!s))?"
    r"(?:(?P<s>\d+(?:[.,]\d+)?)\s*s?)?$",
    re.IGNORECASE,
)


def parse_timecode(value) -> float | None:
    """
    Wandelt eine Zeitangabe in Sekunden um.

    Erlaubt sind:
        "1:23:45"   → 5025.0     (Stunden:Minuten:Sekunden)
        "12:30"     →  750.0     (Minuten:Sekunden)
        "90"        →   90.0     (nackte Sekunden)
        "1h2m3s"    → 3723.0     (YouTube-Schreibweise)
        "1m30s"     →   90.0
        "90.5"      →   90.5     (Komma geht auch: "90,5")
        None / ""   → None       (= "nicht angegeben")

    Wirft ValueError, wenn die Eingabe keinen Sinn ergibt.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds < 0:
            raise ValueError("Zeitangabe darf nicht negativ sein.")
        return seconds

    text = str(value).strip().lower().replace(" ", "")
    if not text:
        return None
    if text.startswith("-"):
        raise ValueError("Zeitangabe darf nicht negativ sein.")

    if ":" in text:
        parts = text.split(":")
        if len(parts) > 3 or any(p == "" for p in parts):
            raise ValueError(f"Unverständliche Zeitangabe: {value!r}")
        total = 0.0
        for part in parts:
            try:
                total = total * 60 + float(part.replace(",", "."))
            except ValueError:
                raise ValueError(f"Unverständliche Zeitangabe: {value!r}") from None
        return total

    match = _HMS_RE.match(text)
    if not match or not any(match.group(g) for g in ("h", "m", "s")):
        raise ValueError(f"Unverständliche Zeitangabe: {value!r}")

    hours = float(match.group("h") or 0)
    minutes = float(match.group("m") or 0)
    seconds = float((match.group("s") or "0").replace(",", "."))
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float, sep: str = ",") -> str:
    """Sekunden → "00:01:30,500" (SRT) bzw. "00:01:30.500" (WebVTT)."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, total_ms = divmod(total_ms, 3_600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def format_hms(seconds: float) -> str:
    """Sekunden → kompakte Anzeige: "3:07" oder "1:02:03"."""
    total = max(0, int(round(float(seconds))))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_url_time(url: str) -> float | None:
    """
    Holt die Sprungmarke aus einem Link.

        https://youtu.be/abc?t=90          → 90.0
        https://youtube.com/watch?v=x&t=1h2m3s → 3723.0
        https://example.com/video#t=42     → 42.0

    Gibt None zurück, wenn der Link keine Zeit enthält.
    """
    if not url:
        return None
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return None

    candidates: list[str] = []
    query = parse_qs(parsed.query)
    for key in ("t", "start", "time_continue", "begin"):
        candidates.extend(query.get(key, []))

    fragment = parsed.fragment or ""
    if fragment:
        frag_query = parse_qs(fragment)
        for key in ("t", "start"):
            candidates.extend(frag_query.get(key, []))
        if "=" not in fragment:
            candidates.append(fragment)

    for candidate in candidates:
        try:
            value = parse_timecode(candidate)
        except ValueError:
            continue
        if value is not None:
            return value
    return None


def resolve_range(start=None, end=None, duration=None) -> tuple[float | None, float | None]:
    """
    Bringt Start / Ende / Dauer auf einen gemeinsamen Nenner.

    Rückgabe: (start_sekunden, dauer_sekunden) – beides darf None sein
    ("von Anfang an" bzw. "bis zum Schluss").

    "Ende" und "Dauer" schließen sich gegenseitig aus; ist beides gesetzt,
    gewinnt das konkretere "Ende".
    """
    start_s = parse_timecode(start)
    end_s = parse_timecode(end)
    dur_s = parse_timecode(duration)

    if end_s is not None:
        base = start_s or 0.0
        if end_s <= base:
            raise ValueError(
                f"Das Ende ({format_hms(end_s)}) liegt vor dem Start ({format_hms(base)})."
            )
        return start_s, end_s - base

    return start_s, dur_s



# ══════════════════════════════════════════════════════════════════════
# aus media.py
# ══════════════════════════════════════════════════════════════════════

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


import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


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



# ══════════════════════════════════════════════════════════════════════
# aus sprecher.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  SPRECHER-ERKENNUNG – wer sagt was                           ║
╚══════════════════════════════════════════════════════════════╝

Aus

    Und wie war dein Wochenende? Ganz gut, wir waren wandern.

wird

    Sprecher 1: Und wie war dein Wochenende?
    Sprecher 2: Ganz gut, wir waren wandern.

Die eigentliche Erkennung übernimmt pyannote.audio – ein zusätzliches
Paket, das ein kostenloses Hugging-Face-Konto voraussetzt. Ohne das
Paket läuft alles wie bisher, nur eben ohne Sprecher-Namen.

Der interessante Teil steht trotzdem hier und braucht gar nichts:
das Zuordnen von Sprecher-Abschnitten zu Transkript-Abschnitten.
Beide Seiten haben eigene Grenzen, die selten sauber aufeinander
passen – entscheidend ist, wer im jeweiligen Satz am längsten redet.
"""


import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

__all__ = [
    "Sprecherabschnitt",
    "SprecherError",
    "verfuegbar",
    "sprecher_status",
    "diarisieren",
    "namen_vergeben",
    "zuordnen",
    "nach_sprecher_buendeln",
]

ProgressFn = Callable[[float | None, str], None]

# Das Modell, das die Sprecherwechsel findet.
PYANNOTE_MODELL = "pyannote/speaker-diarization-3.1"

ANLEITUNG = (
    "Für die Sprecher-Erkennung sind drei Schritte nötig:\n\n"
    "  1. pip install pyannote.audio\n"
    "  2. Kostenloses Konto auf huggingface.co anlegen und unter\n"
    f"     huggingface.co/{PYANNOTE_MODELL} die Nutzungsbedingungen bestätigen\n"
    "  3. Zugriffs-Token (huggingface.co/settings/tokens) in die .env eintragen:\n"
    "     HUGGINGFACE_TOKEN=hf_...\n\n"
    "Ohne all das funktioniert die Transkription weiterhin – nur eben\n"
    "ohne die Zuordnung, wer gerade spricht."
)


class SprecherError(RuntimeError):
    """Die Sprecher-Erkennung konnte nicht durchgeführt werden."""


@dataclass
class Sprecherabschnitt:
    """Von wann bis wann eine bestimmte Stimme zu hören ist."""

    start: float
    end: float
    sprecher: str

    @property
    def dauer(self) -> float:
        return max(0.0, self.end - self.start)


# ══════════════════════════════════════════════════════════════
# VERFÜGBARKEIT
# ══════════════════════════════════════════════════════════════
def _token() -> str | None:
    for name in ("HUGGINGFACE_TOKEN", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        wert = os.getenv(name)
        if wert:
            return wert
    return None


def _pyannote_da() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def verfuegbar() -> bool:
    """True, wenn Paket und Token beide da sind."""
    return _pyannote_da() and bool(_token())


def sprecher_status() -> str:
    """Statuszeile für die Oberfläche."""
    if verfuegbar():
        return "✅ Sprecher-Erkennung: bereit"
    if _pyannote_da():
        return "⚠️ Sprecher-Erkennung: pyannote.audio da, aber HUGGINGFACE_TOKEN fehlt"
    return "⚠️ Sprecher-Erkennung: nicht eingerichtet (optional)"


# ══════════════════════════════════════════════════════════════
# ERKENNUNG
# ══════════════════════════════════════════════════════════════
_PIPELINE_CACHE: dict[str, object] = {}


def diarisieren(
    audio_pfad: str | Path,
    sprecherzahl: int | None = None,
    progress: ProgressFn | None = None,
) -> list[Sprecherabschnitt]:
    """
    Findet heraus, wann welche Stimme spricht.

    `sprecherzahl` hilft dem Modell, wenn die Anzahl bekannt ist
    (zwei Personen im Interview zum Beispiel); ohne Angabe rät es selbst.
    """
    melden: ProgressFn = progress or (lambda anteil, text: None)

    if not _pyannote_da():
        raise SprecherError("pyannote.audio ist nicht installiert.\n\n" + ANLEITUNG)
    token = _token()
    if not token:
        raise SprecherError("Es ist kein Hugging-Face-Token hinterlegt.\n\n" + ANLEITUNG)

    audio_pfad = Path(audio_pfad)
    if not audio_pfad.exists():
        raise SprecherError(f"Audiodatei nicht gefunden: {audio_pfad}")

    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise SprecherError("pyannote.audio ließ sich nicht laden.\n\n" + ANLEITUNG) from exc

    if PYANNOTE_MODELL not in _PIPELINE_CACHE:
        melden(None, "📦 Sprecher-Modell wird geladen (beim ersten Mal dauert das) …")
        try:
            _PIPELINE_CACHE[PYANNOTE_MODELL] = Pipeline.from_pretrained(
                PYANNOTE_MODELL, use_auth_token=token
            )
        except Exception as exc:
            raise SprecherError(
                f"Das Sprecher-Modell konnte nicht geladen werden: {exc}\n\n"
                "Meist fehlt die Bestätigung der Nutzungsbedingungen auf der\n"
                f"Modellseite huggingface.co/{PYANNOTE_MODELL}.\n\n" + ANLEITUNG
            ) from exc
    pipeline = _PIPELINE_CACHE[PYANNOTE_MODELL]

    melden(None, "👥 Sprecher werden auseinandergehalten …")
    argumente = {}
    if sprecherzahl:
        argumente["num_speakers"] = int(sprecherzahl)

    try:
        ergebnis = pipeline(str(audio_pfad), **argumente)
    except Exception as exc:
        raise SprecherError(f"Die Sprecher-Erkennung ist fehlgeschlagen: {exc}") from exc

    abschnitte = [
        Sprecherabschnitt(float(fenster.start), float(fenster.end), str(name))
        for fenster, _spur, name in ergebnis.itertracks(yield_label=True)
    ]
    abschnitte.sort(key=lambda a: a.start)
    melden(None, f"👥 {len({a.sprecher for a in abschnitte})} Stimmen gefunden.")
    return namen_vergeben(abschnitte)


# ══════════════════════════════════════════════════════════════
# ZUORDNUNG – der Teil, der ohne Zusatzpakete auskommt
# ══════════════════════════════════════════════════════════════
def namen_vergeben(abschnitte: Sequence[Sprecherabschnitt]) -> list[Sprecherabschnitt]:
    """
    Macht aus "SPEAKER_00" ein lesbares "Sprecher 1".

    Nummeriert wird in der Reihenfolge des ersten Auftretens – wer
    zuerst spricht, ist Sprecher 1. Das liest sich natürlicher als
    die zufälligen Modell-Kennungen.
    """
    zuordnung: dict[str, str] = {}
    ergebnis = []
    for abschnitt in sorted(abschnitte, key=lambda a: a.start):
        if abschnitt.sprecher not in zuordnung:
            zuordnung[abschnitt.sprecher] = f"Sprecher {len(zuordnung) + 1}"
        ergebnis.append(
            Sprecherabschnitt(abschnitt.start, abschnitt.end, zuordnung[abschnitt.sprecher])
        )
    return ergebnis


def zuordnen(segmente: Iterable, abschnitte: Sequence[Sprecherabschnitt]):
    """
    Schreibt jedem Transkript-Abschnitt seinen Sprecher hinein.

    Whisper schneidet nach Sätzen, die Sprecher-Erkennung nach Stimmen –
    die Grenzen liegen fast nie übereinander. Deshalb gewinnt, wer
    innerhalb des Satzes am längsten zu hören ist. Überlappt gar nichts
    (Musik, Stille, Hintergrundgeräusch), bleibt der Sprecher leer.
    """
    segmente = list(segmente)
    if not abschnitte:
        return segmente

    for segment in segmente:
        bester: str | None = None
        beste_dauer = 0.0
        for abschnitt in abschnitte:
            if abschnitt.end <= segment.start:
                continue
            if abschnitt.start >= segment.end:
                break                          # Abschnitte sind sortiert – ab hier kommt nichts mehr
            ueberlappung = min(segment.end, abschnitt.end) - max(segment.start, abschnitt.start)
            if ueberlappung > beste_dauer:
                bester, beste_dauer = abschnitt.sprecher, ueberlappung
        segment.speaker = bester
    return segmente


def nach_sprecher_buendeln(segmente: Sequence, luecke: float = 1.5) -> list[tuple[str | None, float, float, str]]:
    """
    Fasst aufeinanderfolgende Abschnitte desselben Sprechers zusammen.

    Sonst steht bei jedem Halbsatz aufs Neue "Sprecher 1:", was den
    Text unlesbar macht. Bei einer Pause länger als `luecke` wird
    trotzdem getrennt – dann ist es ein neuer Wortbeitrag.

    Rückgabe: [(sprecher, start, ende, text), …]
    """
    gebuendelt: list[list] = []
    for segment in segmente:
        text = str(getattr(segment, "text", "")).strip()
        if not text:
            continue
        sprecher = getattr(segment, "speaker", None)
        if (
            gebuendelt
            and gebuendelt[-1][0] == sprecher
            and segment.start - gebuendelt[-1][2] <= luecke
        ):
            gebuendelt[-1][2] = segment.end
            gebuendelt[-1][3] += " " + text
        else:
            gebuendelt.append([sprecher, segment.start, segment.end, text])
    return [(s, a, e, t) for s, a, e, t in gebuendelt]



# ══════════════════════════════════════════════════════════════════════
# aus transcribe.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  TRANSKRIPTION – aus Gesprochenem wird lesbarer Text         ║
╚══════════════════════════════════════════════════════════════╝

Drei Wege, dasselbe Ziel:

  ⚡ faster-whisper  – läuft offline auf dem eigenen Rechner, schnell,
                       kostenlos, keine Anmeldung. Standard-Empfehlung.
  🐢 whisper         – das Original von OpenAI, ebenfalls offline,
                       braucht aber deutlich mehr Rechenzeit.
  ☁️  openai-api      – die Cloud erledigt die Arbeit. Braucht einen
                       OPENAI_API_KEY, dafür reicht ein schwacher Laptop.

Welcher Weg zur Verfügung steht, entscheidet sich zur Laufzeit:
`available_backends()` fragt nach, `transcribe()` nimmt mit "auto"
automatisch den besten installierten.
"""


import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence


__all__ = [
    "Segment",
    "Transcript",
    "TranscriptionError",
    "MODELS",
    "LANGUAGES",
    "available_backends",
    "backend_status",
    "transcribe",
    "MODELL_MB",
    "modell_ordner",
    "modell_schon_da",
    "ordner_groesse",
]

ProgressFn = Callable[[float | None, str], None]

# Modell → (Beschreibung, ungefährer Speicherbedarf)
MODELS: dict[str, str] = {
    "tiny":     "winzig · blitzschnell · für schnelle Notizen  (~1 GB RAM)",
    "base":     "klein · schnell · brauchbare Qualität         (~1 GB RAM)",
    "small":    "ausgewogen · EMPFOHLEN für Deutsch            (~2 GB RAM)",
    "medium":   "gründlich · spürbar langsamer                 (~5 GB RAM)",
    "large-v3": "beste Qualität · braucht Geduld oder GPU      (~10 GB RAM)",
}

LANGUAGES: dict[str, str | None] = {
    "Automatisch erkennen": None,
    "Deutsch": "de",
    "Englisch": "en",
    "Französisch": "fr",
    "Spanisch": "es",
    "Italienisch": "it",
    "Türkisch": "tr",
    "Russisch": "ru",
    "Polnisch": "pl",
    "Niederländisch": "nl",
}

_MODEL_CACHE: dict[tuple, object] = {}

# Ungefähre Größe der Modelldateien in MB – nur zum Anzeigen des
# Fortschritts, deshalb dürfen die Zahlen ruhig gerundet sein.
MODELL_MB = {"tiny": 75, "base": 145, "small": 484, "medium": 1530, "large-v3": 3090}


def modell_ordner(model: str) -> Path:
    """
    Wo Hugging Face das Modell ablegt.

    Der Ort lässt sich über Umgebungsvariablen verschieben; ohne die
    landet alles unter ~/.cache/huggingface/hub.
    """
    cache = os.getenv("HF_HUB_CACHE")
    if cache:
        basis = Path(cache)
    else:
        basis = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return basis / f"models--Systran--faster-whisper-{model}"


def ordner_groesse(ordner: Path) -> int:
    """Belegte Bytes eines Ordners. Fehlt er, sind es null."""
    try:
        return sum(f.stat().st_size for f in ordner.rglob("*") if f.is_file())
    except OSError:
        return 0


def modell_schon_da(model: str) -> bool:
    """
    Liegt das Modell schon vollständig auf der Platte?

    Als Maßstab dient die halbe erwartete Größe – ein abgebrochener
    Download hinterlässt Bruchstücke, die nicht als "fertig" durchgehen
    sollen.
    """
    erwartet = MODELL_MB.get(model)
    if not erwartet:
        return modell_ordner(model).exists()
    return ordner_groesse(modell_ordner(model)) > erwartet * 500_000


def _download_beobachten(model: str, melden: ProgressFn, fertig: threading.Event) -> None:
    """
    Meldet, wie weit der Modell-Download ist.

    Ohne das schweigt die App beim ersten Start fünf bis zehn Minuten
    am Stück – man sieht den Fortschritt nur im Konsolenfenster, wo
    niemand hinschaut. Gemessen wird schlicht, wie der Ordner wächst.
    """
    ordner = modell_ordner(model)
    ziel = MODELL_MB.get(model)
    begonnen = time.monotonic()

    while not fertig.wait(2.0):
        mb = ordner_groesse(ordner) / 1_000_000
        vergangen = int(time.monotonic() - begonnen)
        uhr = f"{vergangen // 60}:{vergangen % 60:02d}"
        if ziel and mb >= 1:
            melden(min(mb / ziel, 0.99),
                   f"📦 Modell wird geladen … {mb:.0f} von rund {ziel} MB   ({uhr})")
        else:
            melden(None, f"📦 Verbindung zum Modell-Server …   ({uhr})")


class TranscriptionError(RuntimeError):
    """Die Spracherkennung konnte nicht durchgeführt werden."""


# ══════════════════════════════════════════════════════════════
# ERGEBNIS-DATENTYPEN
# ══════════════════════════════════════════════════════════════
@dataclass
class Segment:
    """Ein gesprochener Abschnitt mit Anfang, Ende und Wortlaut."""

    start: float
    end: float
    text: str
    speaker: str | None = None      # gefüllt, wenn die Sprecher-Erkennung lief

    def shifted(self, offset: float) -> "Segment":
        return Segment(self.start + offset, self.end + offset, self.text, self.speaker)

    def mit_sprecher(self) -> str:
        """Text mit vorangestelltem Sprecher, falls bekannt."""
        text = self.text.strip()
        return f"{self.speaker}: {text}" if self.speaker else text


@dataclass
class Transcript:
    """Das komplette Ergebnis – Text, Zeitstempel und Herkunft."""

    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    backend: str = ""
    model: str = ""
    title: str = ""
    origin: str = ""
    offset: float = 0.0
    duration: float | None = None
    summary: str = ""               # gefüllt, wenn zusammengefasst wurde

    # ── Text in verschiedenen Geschmacksrichtungen ────────────
    @property
    def hat_sprecher(self) -> bool:
        """True, wenn zu mindestens einem Abschnitt ein Sprecher bekannt ist."""
        return any(s.speaker for s in self.segments)

    @property
    def text(self) -> str:
        """Nur der Fließtext, ohne Zeitangaben."""
        return " ".join(s.text.strip() for s in self.segments if s.text.strip()).strip()

    def to_text(self, with_timestamps: bool = False) -> str:
        if not with_timestamps:
            return self.to_dialog() if self.hat_sprecher else self.text
        return "\n".join(
            f"[{format_hms(s.start)} – {format_hms(s.end)}] {s.mit_sprecher()}"
            for s in self.segments
            if s.text.strip()
        )

    def to_dialog(self, with_timestamps: bool = False) -> str:
        """
        Als Gespräch aufbereitet – ein Absatz je Wortbeitrag.

        Ohne Sprecher-Erkennung ist das schlicht der Fließtext; sonst
        werden aufeinanderfolgende Sätze derselben Person gebündelt,
        damit nicht vor jedem Halbsatz erneut der Name steht.
        """

        if not self.hat_sprecher:
            return self.text

        zeilen = []
        for sprecher, start, ende, text in nach_sprecher_buendeln(self.segments):
            kopf = f"[{format_hms(start)}] " if with_timestamps else ""
            name = f"{sprecher}: " if sprecher else ""
            zeilen.append(f"{kopf}{name}{text}")
        return "\n\n".join(zeilen)

    def to_srt(self) -> str:
        """Untertitel-Format für VLC, YouTube, Premiere & Co."""
        blocks = []
        for index, seg in enumerate(self.segments, start=1):
            if not seg.text.strip():
                continue
            blocks.append(
                f"{index}\n"
                f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n"
                f"{seg.mit_sprecher()}\n"
            )
        return "\n".join(blocks)

    def to_vtt(self) -> str:
        """Untertitel-Format fürs Web."""
        lines = ["WEBVTT", ""]
        for seg in self.segments:
            if not seg.text.strip():
                continue
            lines.append(
                f"{format_timestamp(seg.start, '.')} --> {format_timestamp(seg.end, '.')}"
            )
            lines.append(seg.mit_sprecher())
            lines.append("")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Hübsch aufbereitet mit Kopfzeile – gut zum Archivieren."""
        head = [f"# {self.title or 'Transkript'}", ""]
        if self.origin:
            head.append(f"- **Quelle:** {self.origin}")
        if self.offset:
            head.append(f"- **Ausschnitt ab:** {format_hms(self.offset)}")
        if self.duration:
            head.append(f"- **Länge:** {format_hms(self.duration)}")
        head.append(f"- **Sprache:** {self.language or 'unbekannt'}")
        head.append(f"- **Erkannt mit:** {self.backend} / {self.model}")
        if self.hat_sprecher:
            stimmen = len({s.speaker for s in self.segments if s.speaker})
            head.append(f"- **Sprecher:** {stimmen}")
        head += ["", "---", ""]
        if self.summary:
            head += ["## Zusammenfassung", "", self.summary, "", "---", ""]
        koerper = (self.to_dialog(with_timestamps=True) if self.hat_sprecher
                   else self.to_text(with_timestamps=True))
        return "\n".join(head) + "\n" + koerper + "\n"

    def export(self, path: str | Path, with_timestamps: bool = True) -> Path:
        """Speichert je nach Dateiendung als .srt, .vtt, .md oder .txt."""
        path = Path(path)
        suffix = path.suffix.lower()
        content = {
            ".srt": self.to_srt,
            ".vtt": self.to_vtt,
            ".md": self.to_markdown,
        }.get(suffix, lambda: self.to_text(with_timestamps))()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


# ══════════════════════════════════════════════════════════════
# WELCHE BACKENDS SIND DA?
# ══════════════════════════════════════════════════════════════
def _module_available(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available_backends() -> list[str]:
    """Liste der tatsächlich nutzbaren Backends, bestes zuerst."""
    backends = []
    if _module_available("faster_whisper"):
        backends.append("faster-whisper")
    if _module_available("whisper"):
        backends.append("whisper")
    if _module_available("openai") and os.getenv("OPENAI_API_KEY"):
        backends.append("openai-api")
    return backends


def backend_status() -> str:
    """Statuszeile für die Oberfläche."""
    backends = available_backends()
    if not backends:
        return "❌ Kein Spracherkenner installiert – siehe README (pip install faster-whisper)"
    return "✅ Spracherkennung: " + " · ".join(backends)


def _pick_backend(backend: str) -> str:
    available = available_backends()
    if backend and backend != "auto":
        if backend not in available:
            raise TranscriptionError(
                f"Das Backend '{backend}' steht nicht zur Verfügung.\n"
                f"Verfügbar wäre: {', '.join(available) or 'nichts'}\n\n"
                "Installation:  pip install faster-whisper"
            )
        return backend
    if not available:
        raise TranscriptionError(
            "Es ist noch kein Spracherkenner installiert.\n\n"
            "Empfohlen (offline, kostenlos):\n"
            "    pip install faster-whisper\n\n"
            "Oder Cloud (schnell auch auf schwachen Rechnern):\n"
            "    pip install openai   und OPENAI_API_KEY in die .env eintragen"
        )
    return available[0]


# ══════════════════════════════════════════════════════════════
# DIE EINZELNEN BACKENDS
# ══════════════════════════════════════════════════════════════
def _run_faster_whisper(
    audio: Path, model: str, language: str | None, total: float | None, progress: ProgressFn
) -> tuple[list[Segment], str | None]:
    from faster_whisper import WhisperModel

    key = ("faster-whisper", model)
    if key not in _MODEL_CACHE:
        erstmalig = not modell_schon_da(model)
        if erstmalig:
            groesse = MODELL_MB.get(model, "?")
            progress(None, f"📦 Modell '{model}' fehlt noch – rund {groesse} MB werden geholt.")
            progress(None, "   Das passiert nur dieses eine Mal und dauert ein paar Minuten.")
        else:
            progress(None, f"📦 Modell '{model}' wird geladen …")

        # Während das Modell kommt, alle zwei Sekunden melden, wie weit es ist.
        fertig = threading.Event()
        if erstmalig:
            threading.Thread(
                target=_download_beobachten, args=(model, progress, fertig), daemon=True
            ).start()

        try:
            try:
                _MODEL_CACHE[key] = WhisperModel(model, device="auto", compute_type="int8")
            except Exception:
                # Manche Umgebungen mögen device="auto" nicht – dann eben CPU.
                _MODEL_CACHE[key] = WhisperModel(model, device="cpu", compute_type="int8")
        finally:
            fertig.set()

        if erstmalig:
            progress(None, "📦 Modell liegt jetzt auf der Platte – beim nächsten Mal geht es sofort los.")
    whisper_model = _MODEL_CACHE[key]

    progress(0.0, "🧠 Spracherkennung läuft …")
    segment_iter, info = whisper_model.transcribe(
        str(audio),
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    length = total or getattr(info, "duration", None)

    segments: list[Segment] = []
    for seg in segment_iter:
        segments.append(Segment(float(seg.start), float(seg.end), str(seg.text).strip()))
        share = min(seg.end / length, 1.0) if length else None
        progress(share, f"🧠 {format_hms(seg.end)} · {seg.text.strip()[:60]}")
    return segments, getattr(info, "language", None) or language


def _run_openai_whisper(
    audio: Path, model: str, language: str | None, total: float | None, progress: ProgressFn
) -> tuple[list[Segment], str | None]:
    import whisper

    key = ("whisper", model)
    if key not in _MODEL_CACHE:
        progress(None, f"📦 Modell '{model}' wird geladen …")
        _MODEL_CACHE[key] = whisper.load_model(model)
    whisper_model = _MODEL_CACHE[key]

    progress(0.0, "🧠 Spracherkennung läuft (das Original-Whisper meldet sich erst am Ende) …")
    result = whisper_model.transcribe(str(audio), language=language, verbose=False)
    segments = [
        Segment(float(s["start"]), float(s["end"]), str(s["text"]).strip())
        for s in result.get("segments", [])
    ]
    progress(1.0, "🧠 fertig")
    return segments, result.get("language") or language


def _run_openai_api(
    audio: Path, model: str, language: str | None, total: float | None, progress: ProgressFn
) -> tuple[list[Segment], str | None]:
    from openai import OpenAI


    client = OpenAI()
    api_model = "whisper-1"

    chunks = split_audio(audio, chunk_seconds=600.0)
    segments: list[Segment] = []
    detected = language

    for index, (chunk_path, offset) in enumerate(chunks, start=1):
        progress(
            (index - 1) / len(chunks),
            f"☁️ Teil {index}/{len(chunks)} wird an OpenAI geschickt …",
        )
        with open(chunk_path, "rb") as handle:
            response = client.audio.transcriptions.create(
                model=api_model,
                file=handle,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        detected = getattr(response, "language", None) or detected
        for seg in getattr(response, "segments", None) or []:
            start = float(seg["start"] if isinstance(seg, dict) else seg.start)
            end = float(seg["end"] if isinstance(seg, dict) else seg.end)
            text = str(seg["text"] if isinstance(seg, dict) else seg.text).strip()
            segments.append(Segment(start + offset, end + offset, text))
        if chunk_path != audio:
            try:
                chunk_path.unlink()
            except OSError:
                pass

    progress(1.0, "☁️ fertig")
    return segments, detected


_RUNNERS = {
    "faster-whisper": _run_faster_whisper,
    "whisper": _run_openai_whisper,
    "openai-api": _run_openai_api,
}


# ══════════════════════════════════════════════════════════════
# HAUPT-EINSTIEG
# ══════════════════════════════════════════════════════════════
def transcribe(
    audio_path: str | Path,
    backend: str = "auto",
    model: str = "small",
    language: str | None = None,
    offset: float = 0.0,
    title: str = "",
    origin: str = "",
    duration: float | None = None,
    progress: ProgressFn | None = None,
) -> Transcript:
    """
    Erkennt die Sprache in einer Audiodatei und liefert ein `Transcript`.

    `offset` wird auf alle Zeitstempel addiert. Wer also ab Minute 12
    eines Videos transkribiert, bekommt trotzdem Zeitstempel, die zum
    Original passen – praktisch zum Zitieren und Wiederfinden.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise TranscriptionError(f"Audiodatei nicht gefunden: {audio_path}")

    report: ProgressFn = progress or (lambda share, message: None)
    chosen = _pick_backend(backend)

    try:
        segments, detected = _RUNNERS[chosen](audio_path, model, language, duration, report)
    except TranscriptionError:
        raise
    except ImportError as exc:
        raise TranscriptionError(f"Backend '{chosen}' ist nicht vollständig installiert: {exc}") from exc
    except Exception as exc:
        raise TranscriptionError(f"Die Spracherkennung ist fehlgeschlagen: {exc}") from exc

    if offset:
        segments = [seg.shifted(offset) for seg in segments]

    return Transcript(
        segments=segments,
        language=detected,
        backend=chosen,
        model=model if chosen != "openai-api" else "whisper-1",
        title=title,
        origin=origin,
        offset=offset,
        duration=duration,
    )



# ══════════════════════════════════════════════════════════════════════
# aus zusammenfassung.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  ZUSAMMENFASSUNG – aus einer Stunde Text werden zehn Zeilen  ║
╚══════════════════════════════════════════════════════════════╝

Ein Transkript ist selten das, was man eigentlich wissen will.
Nach einer Stunde Besprechung interessiert: Was wurde beschlossen?
Wer macht was? Worum ging es überhaupt?

Genau dafür ist dieses Modul da. Es schickt den Text an ein
Sprachmodell und bekommt eine Zusammenfassung zurück.

  🧠 Anthropic (Claude)  – wenn ANTHROPIC_API_KEY gesetzt ist
  🤖 OpenAI              – wenn OPENAI_API_KEY gesetzt ist
                           (den hat, wer schon die Cloud-Transkription nutzt)

Beides kostet Geld pro Anfrage und schickt den Text aus dem Haus.
Ohne Schlüssel passiert nichts – die Transkription selbst läuft
weiterhin vollständig offline.

Lange Transkripte werden in Häppchen zerlegt, einzeln zusammengefasst
und die Teilergebnisse anschließend noch einmal verdichtet.
"""


import os
import re
from typing import Callable

__all__ = [
    "ARTEN",
    "ZusammenfassungError",
    "verfuegbare_dienste",
    "zusammenfassung_status",
    "zusammenfassen",
    "haeppchen",
    "anweisung_bauen",
]

ProgressFn = Callable[[float | None, str], None]

# Ab hier wird stückweise gearbeitet. Rund 12 000 Zeichen sind etwa
# 20 Minuten gesprochener Text – das passt bequem in eine Anfrage.
MAX_ZEICHEN = 12_000

ANTHROPIC_MODELL = "claude-opus-5"
OPENAI_MODELL = "gpt-4o-mini"

ARTEN: dict[str, str] = {
    "stichpunkte": "Die wichtigsten Punkte als übersichtliche Liste",
    "fliesstext": "Ein zusammenhängender Absatz, wie man ihn jemandem erzählen würde",
    "protokoll": "Besprechungsprotokoll: Themen, Beschlüsse, offene Fragen",
    "aufgaben": "Nur die Aufgaben: wer macht was bis wann",
    "kurz": "Drei Sätze, mehr nicht",
}


class ZusammenfassungError(RuntimeError):
    """Die Zusammenfassung konnte nicht erstellt werden."""


# ══════════════════════════════════════════════════════════════
# WELCHE DIENSTE STEHEN BEREIT?
# ══════════════════════════════════════════════════════════════
def _paket_da(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def verfuegbare_dienste() -> list[str]:
    """Dienste, die tatsächlich nutzbar sind – bester zuerst."""
    dienste = []
    if _paket_da("anthropic") and os.getenv("ANTHROPIC_API_KEY"):
        dienste.append("anthropic")
    if _paket_da("openai") and os.getenv("OPENAI_API_KEY"):
        dienste.append("openai")
    return dienste


def zusammenfassung_status() -> str:
    """Statuszeile für die Oberfläche."""
    dienste = verfuegbare_dienste()
    if dienste:
        return "✅ Zusammenfassung: " + " · ".join(dienste)
    return "⚠️ Zusammenfassung: kein API-Schlüssel hinterlegt (optional)"


def _dienst_waehlen(dienst: str) -> str:
    verfuegbar = verfuegbare_dienste()
    if dienst and dienst != "auto":
        if dienst not in verfuegbar:
            raise ZusammenfassungError(
                f"Der Dienst '{dienst}' steht nicht zur Verfügung.\n"
                f"Nutzbar wäre: {', '.join(verfuegbar) or 'nichts'}"
            )
        return dienst
    if not verfuegbar:
        raise ZusammenfassungError(
            "Für die Zusammenfassung wird ein Sprachmodell gebraucht.\n\n"
            "Variante A – Claude:\n"
            "    pip install anthropic\n"
            "    ANTHROPIC_API_KEY=sk-ant-... in die .env eintragen\n\n"
            "Variante B – OpenAI:\n"
            "    pip install openai\n"
            "    OPENAI_API_KEY=sk-... in die .env eintragen\n\n"
            "Beides kostet pro Anfrage und schickt den Text an einen\n"
            "Online-Dienst. Die Transkription selbst bleibt davon unberührt."
        )
    return verfuegbar[0]


# ══════════════════════════════════════════════════════════════
# TEXT VORBEREITEN – ohne Netz, deshalb gut testbar
# ══════════════════════════════════════════════════════════════
def haeppchen(text: str, max_zeichen: int = MAX_ZEICHEN) -> list[str]:
    """
    Zerlegt langen Text in handliche Stücke.

    Getrennt wird an Satzenden, nicht mitten im Wort – sonst fehlt dem
    Modell am Rand der Zusammenhang. Ein einzelner Satz, der länger ist
    als das erlaubte Stück (kommt bei Transkripten ohne Satzzeichen vor),
    wird notgedrungen hart geschnitten.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_zeichen:
        return [text]

    saetze = re.split(r"(?<=[.!?…])\s+", text)
    stuecke: list[str] = []
    aktuell = ""

    for satz in saetze:
        while len(satz) > max_zeichen:            # Notfall: Bandwurmsatz
            if aktuell:
                stuecke.append(aktuell.strip())
                aktuell = ""
            stuecke.append(satz[:max_zeichen])
            satz = satz[max_zeichen:]
        if not aktuell:
            aktuell = satz
        elif len(aktuell) + 1 + len(satz) <= max_zeichen:
            aktuell += " " + satz
        else:
            stuecke.append(aktuell.strip())
            aktuell = satz

    if aktuell.strip():
        stuecke.append(aktuell.strip())
    return [s for s in stuecke if s.strip()]


def anweisung_bauen(art: str = "stichpunkte", sprache: str = "Deutsch") -> str:
    """Baut die Anweisung an das Sprachmodell."""
    if art not in ARTEN:
        raise ZusammenfassungError(
            f"Unbekannte Art '{art}'. Möglich: {', '.join(ARTEN)}"
        )

    vorgaben = {
        "stichpunkte": (
            "Fasse den Text als Stichpunktliste zusammen. Jeder Punkt eine Zeile, "
            "beginnend mit '- '. Sortiere nach Wichtigkeit, nicht nach Reihenfolge."
        ),
        "fliesstext": (
            "Fasse den Text in zusammenhängenden Absätzen zusammen, so wie du es "
            "jemandem erzählen würdest, der nicht dabei war."
        ),
        "protokoll": (
            "Erstelle ein Besprechungsprotokoll mit den Überschriften "
            "'Themen', 'Beschlüsse' und 'Offene Fragen'. Lass eine Überschrift weg, "
            "wenn es dazu nichts gibt."
        ),
        "aufgaben": (
            "Liste ausschließlich die Aufgaben auf, im Format "
            "'- [Wer]: [Was] (bis [Wann])'. Ist etwas davon unklar, schreibe "
            "'unklar' statt zu raten. Gibt es keine Aufgaben, schreibe das."
        ),
        "kurz": "Fasse den Text in höchstens drei Sätzen zusammen.",
    }

    return (
        f"{vorgaben[art]}\n\n"
        f"Antworte auf {sprache}.\n\n"
        "Der Text stammt aus einer automatischen Spracherkennung und enthält "
        "deshalb Hörfehler, abgebrochene Sätze und fehlende Satzzeichen. "
        "Gib nur wieder, was tatsächlich dasteht – ergänze nichts aus eigenem "
        "Wissen. Ist eine Stelle unverständlich, lass sie weg, statt zu raten."
    )


# ══════════════════════════════════════════════════════════════
# DIE DIENSTE
# ══════════════════════════════════════════════════════════════
def _frag_anthropic(anweisung: str, text: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic()
    argumente = dict(
        model=ANTHROPIC_MODELL,
        max_tokens=max_tokens,
        system=anweisung,
        messages=[{"role": "user", "content": text}],
        # Zusammenfassen ist Fleißarbeit, kein Knobeln – niedriger Aufwand
        # liefert hier dasselbe Ergebnis für einen Bruchteil der Kosten.
        output_config={"effort": "low"},
    )

    try:
        antwort = client.messages.create(**argumente)
    except TypeError:
        # Ältere SDK-Fassungen kennen output_config noch nicht.
        argumente.pop("output_config", None)
        antwort = client.messages.create(**argumente)
    except anthropic.BadRequestError:
        argumente.pop("output_config", None)
        antwort = client.messages.create(**argumente)
    except anthropic.AuthenticationError as exc:
        raise ZusammenfassungError("Der ANTHROPIC_API_KEY wird nicht akzeptiert.") from exc
    except anthropic.RateLimitError as exc:
        raise ZusammenfassungError("Zu viele Anfragen – bitte kurz warten.") from exc
    except anthropic.APIConnectionError as exc:
        raise ZusammenfassungError("Keine Verbindung zu Anthropic.") from exc
    except anthropic.APIStatusError as exc:
        raise ZusammenfassungError(f"Anthropic meldet einen Fehler: {exc}") from exc

    if getattr(antwort, "stop_reason", None) == "refusal":
        raise ZusammenfassungError(
            "Das Modell hat die Zusammenfassung abgelehnt. "
            "Das kann bei heiklen Inhalten passieren – das Transkript selbst "
            "bleibt davon unberührt."
        )

    return "\n".join(
        block.text for block in antwort.content if getattr(block, "type", "") == "text"
    ).strip()


def _frag_openai(anweisung: str, text: str, max_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI()
    try:
        antwort = client.chat.completions.create(
            model=OPENAI_MODELL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": anweisung},
                {"role": "user", "content": text},
            ],
        )
    except Exception as exc:
        raise ZusammenfassungError(f"OpenAI meldet einen Fehler: {exc}") from exc

    return (antwort.choices[0].message.content or "").strip()


_DIENSTE = {"anthropic": _frag_anthropic, "openai": _frag_openai}


# ══════════════════════════════════════════════════════════════
# HAUPT-EINSTIEG
# ══════════════════════════════════════════════════════════════
def zusammenfassen(
    text: str,
    art: str = "stichpunkte",
    sprache: str = "Deutsch",
    dienst: str = "auto",
    progress: ProgressFn | None = None,
) -> str:
    """
    Fasst ein Transkript zusammen.

    Lange Texte werden in Häppchen zerlegt, einzeln zusammengefasst und
    die Teilergebnisse danach noch einmal verdichtet – sonst passt eine
    zweistündige Aufnahme in keine einzelne Anfrage.
    """
    melden: ProgressFn = progress or (lambda anteil, meldung: None)

    text = (text or "").strip()
    if not text:
        raise ZusammenfassungError("Es gibt nichts zusammenzufassen – der Text ist leer.")

    gewaehlt = _dienst_waehlen(dienst)
    anweisung = anweisung_bauen(art, sprache)
    frage = _DIENSTE[gewaehlt]

    stuecke = haeppchen(text)
    if len(stuecke) == 1:
        melden(None, f"📝 Zusammenfassung wird erstellt ({gewaehlt}) …")
        return frage(anweisung, stuecke[0], 4096)

    melden(None, f"📝 Text ist lang – wird in {len(stuecke)} Teilen bearbeitet ({gewaehlt}) …")
    teilergebnisse = []
    for nummer, stueck in enumerate(stuecke, start=1):
        melden((nummer - 1) / (len(stuecke) + 1), f"📝 Teil {nummer}/{len(stuecke)} …")
        teilergebnisse.append(
            frage(anweisung_bauen("stichpunkte", sprache), stueck, 2048)
        )

    melden(len(stuecke) / (len(stuecke) + 1), "📝 Teile werden zusammengeführt …")
    gesammelt = "\n\n".join(
        f"--- Abschnitt {i} ---\n{teil}" for i, teil in enumerate(teilergebnisse, start=1)
    )
    schluss = frage(
        anweisung
        + "\n\nDu bekommst die Zusammenfassungen einzelner Abschnitte einer "
          "längeren Aufnahme. Führe sie zu einem Ganzen zusammen, ohne "
          "Wiederholungen und ohne die Abschnittsnummern zu erwähnen.",
        gesammelt,
        4096,
    )
    melden(1.0, "📝 Zusammenfassung fertig.")
    return schluss



# ══════════════════════════════════════════════════════════════════════
# aus tts.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  TEXT → SPRACHE – der Rückweg                                ║
╚══════════════════════════════════════════════════════════════╝

Damit lässt sich ein fertiges Transkript (oder beliebiger Text)
wieder vorlesen bzw. als Audiodatei speichern.

  🔊 pyttsx3 – offline, nutzt die Stimmen des Betriebssystems
               (Windows SAPI5, macOS NSSpeechSynthesizer, Linux espeak)
  🌐 gTTS    – online, klingt natürlicher, speichert MP3

Beide Pakete sind optional. Fehlt beides, sagt die App das freundlich.
"""


import contextlib
import io
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Voice", "TtsError", "available_engines", "tts_status", "list_voices", "speak", "save_speech"]


class TtsError(RuntimeError):
    """Vorlesen oder Speichern hat nicht geklappt."""


@dataclass
class Voice:
    """Eine Stimme des Systems."""

    id: str
    name: str

    def __str__(self) -> str:
        return self.name


def _module_available(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available_engines() -> list[str]:
    engines = []
    if _module_available("pyttsx3"):
        engines.append("pyttsx3")
    if _module_available("gtts"):
        engines.append("gtts")
    return engines


def tts_status() -> str:
    engines = available_engines()
    if not engines:
        return "❌ Kein Sprachausgabe-Paket installiert (pip install pyttsx3)"
    return "✅ Sprachausgabe: " + " · ".join(engines)


def _new_engine(voice: str | None = None, rate: int | None = None):
    """
    Für jeden Vorlese-Auftrag eine frische Engine.

    pyttsx3 verträgt es schlecht, wenn eine einmal gestoppte Engine
    erneut benutzt wird – eine neue ist billiger als ein Hänger.
    """
    try:
        import pyttsx3
    except ImportError as exc:
        raise TtsError(
            "Für die Sprachausgabe wird pyttsx3 gebraucht:\n\n"
            "    pip install pyttsx3\n\n"
            "(Unter Linux zusätzlich:  sudo apt install espeak-ng)"
        ) from exc

    try:
        engine = pyttsx3.init()
    except Exception as exc:
        raise TtsError(f"Die Sprachausgabe konnte nicht gestartet werden: {exc}") from exc

    if voice:
        engine.setProperty("voice", voice)
    if rate:
        engine.setProperty("rate", int(rate))
    return engine


def list_voices() -> list[Voice]:
    """Alle Stimmen, die das Betriebssystem anbietet."""
    try:
        engine = _new_engine()
    except TtsError:
        return []
    try:
        return [
            Voice(id=str(v.id), name=str(getattr(v, "name", v.id)))
            for v in engine.getProperty("voices")
        ]
    except Exception:
        return []
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def speak(text: str, voice: str | None = None, rate: int | None = None) -> None:
    """Liest `text` laut vor. Blockiert, bis der Satz zu Ende ist."""
    text = (text or "").strip()
    if not text:
        raise TtsError("Es gibt nichts vorzulesen – der Text ist leer.")

    engine = _new_engine(voice, rate)
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        raise TtsError(f"Beim Vorlesen ist etwas schiefgegangen: {exc}") from exc
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def save_speech(
    text: str,
    path: str | Path,
    voice: str | None = None,
    rate: int | None = None,
    language: str = "de",
) -> Path:
    """
    Schreibt gesprochenen Text in eine Datei.

    .mp3 → über gTTS (online, natürlichere Stimme)
    sonst → über pyttsx3 (offline, WAV)
    """
    text = (text or "").strip()
    if not text:
        raise TtsError("Es gibt nichts zu speichern – der Text ist leer.")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".mp3":
        try:
            from gtts import gTTS
        except ImportError as exc:
            raise TtsError(
                "MP3 braucht gTTS (und eine Internetverbindung):\n\n"
                "    pip install gTTS\n\n"
                "Alternativ die Datei auf .wav enden lassen – das geht offline."
            ) from exc
        try:
            gTTS(text=text, lang=language or "de").save(str(path))
        except Exception as exc:
            raise TtsError(f"gTTS konnte die Datei nicht erzeugen: {exc}") from exc
        return path

    engine = _new_engine(voice, rate)
    try:
        # Der espeak-Treiber schreibt ungefragt "Audio saved to …" auf die
        # Konsole – das gehört nicht in unsere Ausgabe.
        with contextlib.redirect_stdout(io.StringIO()):
            engine.save_to_file(text, str(path))
            engine.runAndWait()
    except Exception as exc:
        raise TtsError(f"Die Audiodatei konnte nicht geschrieben werden: {exc}") from exc
    finally:
        try:
            engine.stop()
        except Exception:
            pass

    if not path.exists() or path.stat().st_size == 0:
        raise TtsError(
            "Die Audiodatei blieb leer. Unter Linux fehlt meistens die Sprach-Engine:\n"
            "    sudo apt install espeak-ng"
        )
    return path



# ══════════════════════════════════════════════════════════════════════
# aus pipeline.py
# ══════════════════════════════════════════════════════════════════════

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


import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


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
    if start is None and looks_like_url(source):
        from_link = parse_url_time(source)
        if from_link:
            start = from_link
            report(None, f"🔗 Sprungmarke aus dem Link übernommen: ab {format_hms(start)}")

    if start is not None or duration is not None:
        von = format_hms(start or 0)
        bis = format_hms((start or 0) + duration) if duration else "Ende"
        report(None, f"✂️ Ausschnitt: {von} → {bis}")

    report(None, "📥 Quelle wird vorbereitet …")
    prepared = prepare_source(
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
        )

        if job.sprecher:
            _sprecher_zuordnen(job, prepared, result, report)
    finally:
        prepared.cleanup()

    words = len(result.text.split())
    schluss = f"✅ Fertig: {len(result.segments)} Abschnitte · {words} Wörter"
    if result.hat_sprecher:
        schluss += f" · {len({s.speaker for s in result.segments if s.speaker})} Sprecher"
    report(1.0, schluss)
    return result


def _sprecher_zuordnen(job: Job, prepared, result: Transcript, report: ProgressFn) -> None:
    """
    Hängt die Sprecher-Erkennung an ein fertiges Transkript.

    Schlägt sie fehl, ist das kein Grund, die ganze Arbeit wegzuwerfen –
    das Transkript steht ja schon. Es gibt dann nur eine Meldung und
    weiter geht es ohne Namen.
    """

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



# ══════════════════════════════════════════════════════════════════════
# aus warteschlange.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  WARTESCHLANGE – mehrere Videos am Stück                     ║
╚══════════════════════════════════════════════════════════════╝

Wer zehn Videos hat, will nicht zehnmal danebensitzen. Hier landen
Aufträge in einer Liste und werden der Reihe nach abgearbeitet –
im Hintergrund, während die Oberfläche bedienbar bleibt.

Das Modul kennt keine Fenster und keine Knöpfe. Es meldet nur, was
passiert; wer zuhört, entscheidet selbst, wie er es anzeigt. Genau
deshalb lässt es sich ohne Bildschirm testen.
"""


import itertools
import threading
from dataclasses import dataclass, field
from typing import Callable


__all__ = ["Auftrag", "Warteschlange", "WARTET", "LAEUFT", "FERTIG", "FEHLER", "ABGEBROCHEN"]

WARTET = "wartet"
LAEUFT = "läuft"
FERTIG = "fertig"
FEHLER = "Fehler"
ABGEBROCHEN = "abgebrochen"

# Ereignisse, die nach draußen gemeldet werden
EreignisFn = Callable[[str, object], None]

_zaehler = itertools.count(1)


@dataclass
class Auftrag:
    """Ein Eintrag in der Warteschlange."""

    job: Job
    nummer: int = field(default_factory=lambda: next(_zaehler))
    status: str = WARTET
    transcript: Transcript | None = None
    fehler: str = ""

    @property
    def name(self) -> str:
        """
        Kurzer, lesbarer Name für die Anzeige.

        Bei Dateien reicht der Dateiname. Bei Links darf nicht einfach am
        letzten "/" abgeschnitten werden – aus einem YouTube-Link würde
        sonst nur die kryptische Video-Kennung übrig bleiben.
        """
        if self.transcript and self.transcript.title:
            return self.transcript.title

        quelle = str(self.job.source).strip()
        if looks_like_url(quelle):
            gekuerzt = quelle.split("://", 1)[-1]
            return gekuerzt if len(gekuerzt) <= 60 else gekuerzt[:57] + "…"
        if "/" in quelle or "\\" in quelle:
            return quelle.replace("\\", "/").rstrip("/").split("/")[-1] or quelle
        return quelle

    @property
    def erledigt(self) -> bool:
        return self.status in (FERTIG, FEHLER, ABGEBROCHEN)


class Warteschlange:
    """
    Arbeitet Aufträge nacheinander ab – immer nur einer gleichzeitig.

    Zwei Videos parallel zu transkribieren macht nichts schneller; beide
    teilen sich denselben Prozessor und beide dauern doppelt so lang.
    Nacheinander ist ehrlicher und der Fortschrittsbalken stimmt.
    """

    def __init__(self, ereignis: EreignisFn | None = None, ausfuehren=run_job):
        self._auftraege: list[Auftrag] = []
        self._sperre = threading.Lock()
        self._thread: threading.Thread | None = None
        self._abbruch = threading.Event()
        self._ereignis = ereignis or (lambda art, wert: None)
        self._ausfuehren = ausfuehren        # zum Testen austauschbar

    # ── Zustand ───────────────────────────────────────────────
    @property
    def auftraege(self) -> list[Auftrag]:
        with self._sperre:
            return list(self._auftraege)

    @property
    def laeuft(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def offen(self) -> int:
        return sum(1 for a in self.auftraege if a.status == WARTET)

    def zusammenfassung(self) -> str:
        auftraege = self.auftraege
        if not auftraege:
            return "Warteschlange ist leer."
        fertig = sum(1 for a in auftraege if a.status == FERTIG)
        fehler = sum(1 for a in auftraege if a.status == FEHLER)
        teile = [f"{len(auftraege)} Einträge", f"{fertig} fertig"]
        if fehler:
            teile.append(f"{fehler} mit Fehler")
        if self.offen:
            teile.append(f"{self.offen} offen")
        return " · ".join(teile)

    # ── Bestücken ─────────────────────────────────────────────
    def hinzufuegen(self, job: Job) -> Auftrag:
        auftrag = Auftrag(job=job)
        with self._sperre:
            self._auftraege.append(auftrag)
        self._melden("aenderung", auftrag)
        return auftrag

    def entfernen(self, auftrag: Auftrag) -> bool:
        """Entfernt einen Eintrag – laufende bleiben unangetastet."""
        if auftrag.status == LAEUFT:
            return False
        with self._sperre:
            if auftrag not in self._auftraege:
                return False
            self._auftraege.remove(auftrag)
        self._melden("aenderung", auftrag)
        return True

    def erledigte_entfernen(self) -> int:
        with self._sperre:
            vorher = len(self._auftraege)
            self._auftraege = [a for a in self._auftraege if not a.erledigt]
            entfernt = vorher - len(self._auftraege)
        if entfernt:
            self._melden("aenderung", None)
        return entfernt

    # ── Abarbeiten ────────────────────────────────────────────
    def starten(self) -> bool:
        """Startet die Abarbeitung. Läuft sie schon, passiert nichts."""
        if self.laeuft:
            return False
        if not self.offen:
            return False
        self._abbruch.clear()
        self._thread = threading.Thread(target=self._schleife, daemon=True)
        self._thread.start()
        return True

    def abbrechen(self) -> None:
        """
        Stoppt nach dem aktuellen Eintrag.

        Mittendrin abzuwürgen würde halbe Dateien und verwaiste
        Temp-Ordner hinterlassen – der laufende Eintrag wird deshalb
        noch fertig gerechnet, alle weiteren nicht mehr begonnen.
        """
        self._abbruch.set()
        self._melden("log", "🛑 Abbruch vorgemerkt – der laufende Eintrag wird noch beendet.")

    def _naechster(self) -> Auftrag | None:
        with self._sperre:
            for auftrag in self._auftraege:
                if auftrag.status == WARTET:
                    return auftrag
        return None

    def _schleife(self) -> None:
        while not self._abbruch.is_set():
            auftrag = self._naechster()
            if auftrag is None:
                break

            auftrag.status = LAEUFT
            self._melden("aenderung", auftrag)
            self._melden("log", f"▶️ [{auftrag.nummer}] {auftrag.name}")

            try:
                auftrag.transcript = self._ausfuehren(
                    auftrag.job,
                    progress=lambda anteil, text: self._fortschritt(anteil, text),
                )
                auftrag.status = FERTIG
                self._melden("fertig", auftrag)
            except Exception as exc:
                auftrag.fehler = str(exc) or exc.__class__.__name__
                auftrag.status = FEHLER
                self._melden("fehler", auftrag)
            self._melden("aenderung", auftrag)

        # Was nach einem Abbruch übrig ist, sauber kennzeichnen
        if self._abbruch.is_set():
            for auftrag in self.auftraege:
                if auftrag.status == WARTET:
                    auftrag.status = ABGEBROCHEN
            self._melden("aenderung", None)

        self._melden("leer", None)

    def _fortschritt(self, anteil, text) -> None:
        if text:
            self._melden("log", text)
        self._melden("fortschritt", anteil)

    def _melden(self, art: str, wert) -> None:
        try:
            self._ereignis(art, wert)
        except Exception:
            pass                              # ein kaputter Zuhörer darf die Schlange nicht anhalten



# ══════════════════════════════════════════════════════════════════════
# aus app.py
# ══════════════════════════════════════════════════════════════════════

"""
╔══════════════════════════════════════════════════════════════╗
║  🎙️  VOICE2TEXT – Oberfläche                                 ║
╚══════════════════════════════════════════════════════════════╝

Video rein → Text raus. Sechs Reiter:

  🎬 Datei         Video oder Audio vom Rechner – auch per Drag & Drop
  🌐 Online-Link   Link einwerfen, optional Uhrzeit – nur die Stelle wird geholt
  📚 Warteschlange Mehrere Videos am Stück, einer nach dem anderen
  📝 Transkript    Ergebnis lesen, kopieren, als TXT/SRT/VTT/MD speichern
  🔊 Vorlesen      Text zu Sprache – auch das fertige Transkript
  ⚙️ Einstellungen Modell, Sprache, Backend, Ausgabeordner

Start:  python -m voice2text
"""


import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

try:
    import customtkinter as ctk
    from tkinter import StringVar, filedialog, messagebox
except ImportError as exc:  # pragma: no cover – nur ohne GUI-Pakete
    fehlt_tkinter = "tkinter" in str(exc)
    raise SystemExit(
        ("Für die Oberfläche fehlt tkinter – das gehört zu Python selbst:\n\n"
         "    Linux :  sudo apt install python3-tk\n"
         "    Mac   :  brew install python-tk\n"
         "    Windows: Python neu installieren und dabei 'tcl/tk' anhaken\n\n"
         if fehlt_tkinter else
         "Für die Oberfläche fehlt customtkinter:\n\n"
         "    pip install customtkinter\n\n")
        + "Ohne Oberfläche geht es auch:  python -m voice2text --hilfe\n"
        + f"(Ursprünglicher Fehler: {exc})"
    )

ZF_ARTEN = ARTEN

# ── DRAG & DROP (optional) ────────────────────────────────────
# Ohne tkinterdnd2 läuft alles wie gehabt, nur eben ohne Ziehen.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_DA = True
except Exception:
    DND_DA = False

if DND_DA:
    class _Fenster(ctk.CTk, TkinterDnD.DnDWrapper):
        """customtkinter-Fenster, das zusätzlich Dateien per Maus annimmt."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:                                       # pragma: no cover
    _Fenster = ctk.CTk

# ── FARBEN (gleiche Handschrift wie der Trading-Bot) ──────────
CLR_BG     = "#0a0a0b"
CLR_CARD   = "#141417"
CLR_ACCENT = "#f1c40f"
CLR_GREEN  = "#00ff88"
CLR_RED    = "#ff4655"
CLR_BLUE   = "#4fa3e0"
CLR_GREY   = "#8a8a92"

STATUS_FARBE = {WARTET: CLR_GREY, LAEUFT: CLR_ACCENT, FERTIG: CLR_GREEN, FEHLER: CLR_RED}
STATUS_ZEICHEN = {WARTET: "⏳", LAEUFT: "▶️", FERTIG: "✅", FEHLER: "❌"}

SETTINGS_FILE = Path.home() / ".voice2text.json"
DEFAULT_OUTPUT = Path.home() / "Transkripte"

FILETYPES = [
    ("Video & Audio", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mp3 *.wav *.m4a *.aac *.ogg *.opus *.flac"),
    ("Alle Dateien", "*.*"),
]


# ══════════════════════════════════════════════════════════════
# EINSTELLUNGEN – überleben den Neustart
# ══════════════════════════════════════════════════════════════
def load_settings() -> dict:
    defaults = {
        "backend": "auto",
        "model": "small",
        "language": "Deutsch",
        "output_dir": str(DEFAULT_OUTPUT),
        "auto_save": True,
        "cookies_browser": "",
        "sprecher": False,
        "sprecherzahl": "",
        "zf_art": "stichpunkte",
    }
    try:
        if SETTINGS_FILE.exists():
            defaults.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass                                   # kaputte Datei? Dann eben Standardwerte.
    return defaults


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def open_folder(path: str | Path) -> None:
    """Ausgabeordner im Datei-Explorer zeigen."""
    path = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)                 # noqa: S606 – gewollt
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# DIE APP
# ══════════════════════════════════════════════════════════════
class VoiceApp(_Fenster):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.transcript: Transcript | None = None
        self.messages: queue.Queue = queue.Queue()
        self.zf_laeuft = False
        self.schlange = Warteschlange(ereignis=self._schlangen_ereignis)

        self.title("🎙️ Voice2Text – Video & Sprache zu Text")
        self.geometry("1060x820")
        self.minsize(900, 660)
        self.configure(fg_color=CLR_BG)
        ctk.set_appearance_mode("dark")

        self._build_header()
        self._build_tabs()
        self._build_footer()

        self.after(120, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._log("👋 Willkommen! Video oder Link auswählen und loslegen.")
        if DND_DA:
            self._log("🖱️ Tipp: Videos lassen sich direkt ins Fenster ziehen.")
            self._drop_ziel(self, self._drop_irgendwo)
        self._check_environment()

    # ── KOPFZEILE ─────────────────────────────────────────────
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=CLR_CARD, corner_radius=0, height=64)
        head.pack(fill="x")
        head.pack_propagate(False)

        ctk.CTkLabel(
            head, text="🎙️ VOICE2TEXT",
            font=ctk.CTkFont(size=22, weight="bold"), text_color=CLR_ACCENT,
        ).pack(side="left", padx=20)

        ctk.CTkLabel(
            head, text="Video · Audio · Online-Link  →  lesbarer Text",
            font=ctk.CTkFont(size=13), text_color=CLR_GREY,
        ).pack(side="left")

        self.env_label = ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=12), text_color=CLR_GREY, justify="right",
        )
        self.env_label.pack(side="right", padx=20)

    # ── REITER ────────────────────────────────────────────────
    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(
            self, fg_color=CLR_CARD, segmented_button_selected_color=CLR_ACCENT,
            segmented_button_selected_hover_color=CLR_ACCENT, text_color="#ffffff",
        )
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(12, 6))

        self.tab_file = self.tabs.add("🎬 Datei")
        self.tab_link = self.tabs.add("🌐 Online-Link")
        self.tab_queue = self.tabs.add("📚 Warteschlange")
        self.tab_text = self.tabs.add("📝 Transkript")
        self.tab_sum = self.tabs.add("🧾 Zusammenfassung")
        self.tab_tts = self.tabs.add("🔊 Vorlesen")
        self.tab_cfg = self.tabs.add("⚙️ Einstellungen")

        self._build_tab_file()
        self._build_tab_link()
        self._build_tab_queue()
        self._build_tab_text()
        self._build_tab_sum()
        self._build_tab_tts()
        self._build_tab_settings()

    # ---------- 🎬 DATEI ----------
    def _build_tab_file(self):
        frame = self.tab_file
        ctk.CTkLabel(
            frame, text="Video oder Audio vom Rechner transkribieren",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))

        hinweis = "Unterstützt mp4, mkv, mov, webm, mp3, m4a, wav … – alles, was ffmpeg lesen kann."
        if DND_DA:
            hinweis += "\n🖱️ Datei einfach ins Fenster ziehen – mehrere landen in der Warteschlange."
        ctk.CTkLabel(frame, text=hinweis, text_color=CLR_GREY, justify="left").pack(
            anchor="w", padx=18, pady=(0, 14))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=18)
        self.file_var = StringVar()
        self.file_entry = ctk.CTkEntry(
            row, textvariable=self.file_var, height=40,
            placeholder_text="Pfad zur Datei – oder rechts auf „Durchsuchen“ klicken",
        )
        self.file_entry.pack(side="left", fill="x", expand=True)
        self._drop_ziel(self.file_entry, self._drop_auf_dateifeld)

        ctk.CTkButton(
            row, text="📂 Durchsuchen", width=140, height=40, command=self._choose_file,
        ).pack(side="left", padx=(10, 0))

        self.file_start, self.file_end, self.file_dur = self._build_range_row(frame)

        knoepfe = ctk.CTkFrame(frame, fg_color="transparent")
        knoepfe.pack(fill="x", padx=18, pady=(22, 10))
        ctk.CTkButton(
            knoepfe, text="▶️  TRANSKRIPTION STARTEN", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=CLR_GREEN, hover_color="#00cc6d", text_color="#04120a",
            command=self._start_file_job,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            knoepfe, text="➕ In die Warteschlange", height=48, width=200,
            command=lambda: self._start_file_job(sofort=False),
        ).pack(side="left", padx=(10, 0))

    # ---------- 🌐 LINK ----------
    def _build_tab_link(self):
        frame = self.tab_link
        ctk.CTkLabel(
            frame, text="Direkt von einem Online-Video",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame,
            text=("Link einfügen – wahlweise mit Uhrzeit. Dann wird nur genau diese Stelle geladen\n"
                  "statt des ganzen Videos. Enthält der Link schon eine Sprungmarke (…?t=90),\n"
                  "wird sie automatisch übernommen."),
            text_color=CLR_GREY, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        self.url_var = StringVar()
        ctk.CTkEntry(
            frame, textvariable=self.url_var, height=40,
            placeholder_text="https://www.youtube.com/watch?v=…    oder jeder andere Video-Link",
        ).pack(fill="x", padx=18)

        self.url_start, self.url_end, self.url_dur = self._build_range_row(frame)

        ctk.CTkLabel(
            frame,
            text="ℹ️ Bitte nur Inhalte laden, die du auch laden darfst – die Nutzungsbedingungen der Plattform gelten weiterhin.",
            text_color=CLR_GREY, font=ctk.CTkFont(size=11), wraplength=900, justify="left",
        ).pack(anchor="w", padx=18, pady=(14, 0))

        knoepfe = ctk.CTkFrame(frame, fg_color="transparent")
        knoepfe.pack(fill="x", padx=18, pady=(16, 10))
        ctk.CTkButton(
            knoepfe, text="▶️  LINK TRANSKRIBIEREN", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=CLR_BLUE, hover_color="#3d87bd",
            command=self._start_link_job,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            knoepfe, text="➕ In die Warteschlange", height=48, width=200,
            command=lambda: self._start_link_job(sofort=False),
        ).pack(side="left", padx=(10, 0))

    def _build_range_row(self, parent):
        """Drei Felder für Start / Ende / Dauer – identisch in beiden Reitern."""
        box = ctk.CTkFrame(parent, fg_color=CLR_BG, corner_radius=10)
        box.pack(fill="x", padx=18, pady=(16, 0))

        ctk.CTkLabel(
            box, text="✂️  Ausschnitt (optional)   ·   Schreibweisen: 12:30 · 1:05:20 · 90 · 1h2m3s",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_ACCENT,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 8))

        start_var, end_var, dur_var = StringVar(), StringVar(), StringVar()
        for column, (label, var, hint) in enumerate((
            ("Start", start_var, "z. B. 12:30"),
            ("Ende", end_var, "z. B. 14:00"),
            ("oder Dauer", dur_var, "z. B. 90"),
        )):
            cell = ctk.CTkFrame(box, fg_color="transparent")
            cell.grid(row=1, column=column, sticky="ew", padx=14, pady=(0, 14))
            box.grid_columnconfigure(column, weight=1)
            ctk.CTkLabel(cell, text=label, text_color=CLR_GREY, font=ctk.CTkFont(size=12)).pack(anchor="w")
            ctk.CTkEntry(cell, textvariable=var, height=36, placeholder_text=hint).pack(fill="x")

        return start_var, end_var, dur_var

    # ---------- 📚 WARTESCHLANGE ----------
    def _build_tab_queue(self):
        frame = self.tab_queue
        ctk.CTkLabel(
            frame, text="Mehrere Videos am Stück",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))

        hinweis = ("Einträge werden nacheinander abgearbeitet – parallel wäre nicht schneller,\n"
                   "beide würden sich denselben Prozessor teilen.")
        if DND_DA:
            hinweis += "\n🖱️ Mehrere Dateien gleichzeitig ins Fenster ziehen füllt die Liste auf einmal."
        ctk.CTkLabel(frame, text=hinweis, text_color=CLR_GREY, justify="left").pack(
            anchor="w", padx=18, pady=(0, 12))

        leiste = ctk.CTkFrame(frame, fg_color="transparent")
        leiste.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkButton(
            leiste, text="▶️ Alle abarbeiten", fg_color=CLR_GREEN, text_color="#04120a",
            hover_color="#00cc6d", command=self._queue_start,
        ).pack(side="left")
        ctk.CTkButton(leiste, text="🛑 Abbrechen", fg_color=CLR_RED, hover_color="#cc3644",
                      command=self._queue_abbrechen).pack(side="left", padx=8)
        ctk.CTkButton(leiste, text="🧹 Erledigte entfernen",
                      command=self._queue_aufraeumen).pack(side="left")
        ctk.CTkButton(leiste, text="📁 Ausgabeordner",
                      command=lambda: open_folder(self.output_var.get())).pack(side="right")

        self.queue_info = ctk.CTkLabel(frame, text="Warteschlange ist leer.", text_color=CLR_GREY)
        self.queue_info.pack(anchor="w", padx=18)

        self.queue_list = ctk.CTkScrollableFrame(frame, fg_color=CLR_BG)
        self.queue_list.pack(fill="both", expand=True, padx=18, pady=(8, 14))
        self._drop_ziel(self.queue_list, self._drop_in_warteschlange)

    # ---------- 📝 TRANSKRIPT ----------
    def _build_tab_text(self):
        frame = self.tab_text

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(14, 8))

        self.timestamp_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            bar, text="Mit Zeitstempeln", variable=self.timestamp_var,
            command=self._render_transcript, fg_color=CLR_ACCENT, hover_color=CLR_ACCENT,
        ).pack(side="left")

        for text, command in (
            ("📋 Kopieren", self._copy_transcript),
            ("💾 Speichern …", self._save_transcript_as),
            ("📦 Alle Formate", self._save_all_formats),
            ("🔊 Vorlesen", self._speak_transcript),
        ):
            ctk.CTkButton(bar, text=text, width=130, command=command).pack(side="right", padx=(8, 0))

        self.transcript_info = ctk.CTkLabel(
            frame, text="Noch kein Transkript – starte oben mit einer Datei oder einem Link.",
            text_color=CLR_GREY,
        )
        self.transcript_info.pack(anchor="w", padx=18)

        self.transcript_box = ctk.CTkTextbox(
            frame, fg_color=CLR_BG, font=ctk.CTkFont(size=14), wrap="word",
        )
        self.transcript_box.pack(fill="both", expand=True, padx=18, pady=(8, 14))

    # ---------- 🧾 ZUSAMMENFASSUNG ----------
    def _build_tab_sum(self):
        frame = self.tab_sum
        ctk.CTkLabel(
            frame, text="Das Wichtigste in Kürze",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame,
            text=("Aus einer Stunde Transkript werden zehn Zeilen.\n"
                  "Dafür wird der Text an ein Sprachmodell geschickt – das kostet pro Anfrage\n"
                  "und verlässt den Rechner. Ohne API-Schlüssel bleibt dieser Reiter untätig,\n"
                  "alles andere funktioniert weiterhin."),
            text_color=CLR_GREY, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        leiste = ctk.CTkFrame(frame, fg_color="transparent")
        leiste.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(leiste, text="Art", text_color=CLR_GREY).pack(side="left")
        self.zf_art_menu = ctk.CTkOptionMenu(
            leiste, values=list(ZF_ARTEN), width=180, command=self._on_zf_art_change)
        self.zf_art_menu.set(self.settings.get("zf_art", "stichpunkte"))
        self.zf_art_menu.pack(side="left", padx=(8, 12))
        self.zf_hint = ctk.CTkLabel(
            leiste, text=ZF_ARTEN.get(self.settings.get("zf_art", "stichpunkte"), ""),
            text_color=CLR_GREY)
        self.zf_hint.pack(side="left")

        ctk.CTkButton(leiste, text="📋 Kopieren", width=120,
                      command=self._copy_summary).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            leiste, text="🧾 Zusammenfassen", width=180,
            fg_color=CLR_ACCENT, text_color="#101010", hover_color="#d4ac0d",
            command=self._zusammenfassen_klick,
        ).pack(side="right")

        self.summary_box = ctk.CTkTextbox(
            frame, fg_color=CLR_BG, font=ctk.CTkFont(size=14), wrap="word")
        self.summary_box.pack(fill="both", expand=True, padx=18, pady=(4, 14))

    def _on_zf_art_change(self, wert: str):
        self.zf_hint.configure(text=ZF_ARTEN.get(wert, ""))

    def _zusammenfassen_klick(self):
        if not self._require_transcript():
            return
        if self.zf_laeuft:
            self._log("🧾 Läuft bereits.")
            return

        text = self.transcript.text
        art = self.zf_art_menu.get()
        self.zf_laeuft = True
        self._log(f"🧾 Zusammenfassung wird erstellt ({art}) …")

        def arbeit():
            try:
                ergebnis = zusammenfassen(
                    text, art=art,
                    progress=lambda anteil, meldung: self.messages.put(("log", meldung)),
                )
                self.messages.put(("zusammenfassung", ergebnis))
            except ZusammenfassungError as exc:
                self.messages.put(("zusammenfassung_fehler", str(exc)))
            except Exception as exc:
                self.messages.put(("zusammenfassung_fehler", str(exc)))

        threading.Thread(target=arbeit, daemon=True).start()

    def _zeige_zusammenfassung(self, text: str):
        self.zf_laeuft = False
        if self.transcript:
            self.transcript.summary = text
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", text)
        self.tabs.set("🧾 Zusammenfassung")
        self._log("🧾 Zusammenfassung fertig.")

    def _copy_summary(self):
        text = self.summary_box.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Noch nichts da", "Es gibt noch keine Zusammenfassung.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log("📋 Zusammenfassung kopiert.")

    # ---------- 🔊 VORLESEN ----------
    def _build_tab_tts(self):
        frame = self.tab_tts
        ctk.CTkLabel(
            frame, text="Text vorlesen lassen", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame, text="Eigenen Text eintippen oder das fertige Transkript übernehmen.",
            text_color=CLR_GREY,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        self.tts_box = ctk.CTkTextbox(frame, fg_color=CLR_BG, height=260, font=ctk.CTkFont(size=14), wrap="word")
        self.tts_box.pack(fill="both", expand=True, padx=18)

        controls = ctk.CTkFrame(frame, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=12)

        ctk.CTkLabel(controls, text="Stimme", text_color=CLR_GREY).pack(side="left")
        self.voice_menu = ctk.CTkOptionMenu(controls, values=["Standard"], width=260)
        self.voice_menu.pack(side="left", padx=(8, 18))

        ctk.CTkLabel(controls, text="Tempo", text_color=CLR_GREY).pack(side="left")
        self.rate_slider = ctk.CTkSlider(controls, from_=100, to=260, number_of_steps=32, width=180)
        self.rate_slider.set(175)
        self.rate_slider.pack(side="left", padx=(8, 0))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(buttons, text="📝 Transkript übernehmen", command=self._tts_take_transcript).pack(side="left")
        ctk.CTkButton(
            buttons, text="🔊 Vorlesen", fg_color=CLR_GREEN, text_color="#04120a",
            hover_color="#00cc6d", command=self._speak_textbox,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(buttons, text="💾 Als Audiodatei", command=self._save_speech).pack(side="right")

        self._voices: list = []
        threading.Thread(target=self._load_voices, daemon=True).start()

    # ---------- ⚙️ EINSTELLUNGEN ----------
    def _build_tab_settings(self):
        frame = self.tab_cfg
        wrap = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)

        def section(title: str) -> ctk.CTkFrame:
            ctk.CTkLabel(wrap, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=CLR_ACCENT).pack(anchor="w", padx=10, pady=(16, 6))
            box = ctk.CTkFrame(wrap, fg_color=CLR_BG, corner_radius=10)
            box.pack(fill="x", padx=10)
            return box

        # Modell
        box = section("🧠 Erkennungs-Modell")
        self.model_menu = ctk.CTkOptionMenu(box, values=list(MODELS), width=200, command=self._on_model_change)
        self.model_menu.set(self.settings.get("model", "small"))
        self.model_menu.pack(side="left", padx=14, pady=14)
        self.model_hint = ctk.CTkLabel(box, text=MODELS.get(self.settings.get("model", "small"), ""),
                                       text_color=CLR_GREY)
        self.model_hint.pack(side="left", padx=(4, 14))

        # Sprache
        box = section("🗣️ Gesprochene Sprache")
        self.language_menu = ctk.CTkOptionMenu(box, values=list(LANGUAGES), width=240)
        self.language_menu.set(self.settings.get("language", "Deutsch"))
        self.language_menu.pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="Fest eingestellt ist meist genauer als „automatisch“.",
                     text_color=CLR_GREY).pack(side="left")

        # Backend
        box = section("⚙️ Backend")
        options = ["auto"] + (available_backends() or [])
        self.backend_menu = ctk.CTkOptionMenu(box, values=options, width=200)
        self.backend_menu.set(self.settings.get("backend", "auto") if self.settings.get("backend") in options else "auto")
        self.backend_menu.pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="„auto“ nimmt das schnellste installierte Verfahren.",
                     text_color=CLR_GREY).pack(side="left")

        # Ausgabeordner
        box = section("📁 Ausgabeordner")
        self.output_var = StringVar(value=self.settings.get("output_dir", str(DEFAULT_OUTPUT)))
        ctk.CTkEntry(box, textvariable=self.output_var, height=36).pack(
            side="left", fill="x", expand=True, padx=(14, 8), pady=14)
        ctk.CTkButton(box, text="Wählen", width=90, command=self._choose_output_dir).pack(side="left")
        ctk.CTkButton(box, text="Öffnen", width=90,
                      command=lambda: open_folder(self.output_var.get())).pack(side="left", padx=(8, 14))

        self.autosave_var = ctk.BooleanVar(value=bool(self.settings.get("auto_save", True)))
        ctk.CTkCheckBox(wrap, text="Fertige Transkripte automatisch dort speichern (txt · srt · vtt · md)",
                        variable=self.autosave_var, fg_color=CLR_ACCENT,
                        hover_color=CLR_ACCENT).pack(anchor="w", padx=10, pady=(10, 0))

        # Sprecher
        box = section("👥 Sprecher-Erkennung (optional)")
        self.sprecher_var = ctk.BooleanVar(value=bool(self.settings.get("sprecher", False)))
        ctk.CTkCheckBox(box, text="Wer sagt was?", variable=self.sprecher_var,
                        fg_color=CLR_ACCENT, hover_color=CLR_ACCENT).pack(
            side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="Anzahl (falls bekannt)", text_color=CLR_GREY).pack(side="left")
        self.sprecherzahl_var = StringVar(value=str(self.settings.get("sprecherzahl", "")))
        ctk.CTkEntry(box, textvariable=self.sprecherzahl_var, width=60,
                     placeholder_text="z. B. 2").pack(side="left", padx=(8, 14))
        ctk.CTkLabel(box, text="Braucht pyannote.audio und ein Hugging-Face-Token.",
                     text_color=CLR_GREY).pack(side="left")

        # Cookies
        box = section("🍪 Browser-Cookies für Online-Links (optional)")
        self.cookies_var = StringVar(value=self.settings.get("cookies_browser", ""))
        ctk.CTkOptionMenu(box, values=["", "chrome", "firefox", "edge", "brave", "safari"],
                          variable=self.cookies_var, width=200).pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="Nur nötig bei Videos, die eine Anmeldung verlangen.",
                     text_color=CLR_GREY).pack(side="left")

        # Systemstatus
        box = section("🩺 Systemstatus")
        self.status_text = ctk.CTkLabel(box, text="", justify="left", text_color=CLR_GREY)
        self.status_text.pack(anchor="w", padx=14, pady=14)
        ctk.CTkButton(wrap, text="🔄 Status neu prüfen", command=self._check_environment).pack(
            anchor="w", padx=10, pady=(10, 4))
        ctk.CTkButton(wrap, text="💾 Einstellungen speichern", fg_color=CLR_ACCENT, text_color="#101010",
                      hover_color="#d4ac0d", command=self._save_settings_clicked).pack(
            anchor="w", padx=10, pady=(4, 16))

    # ── FUSSZEILE: Fortschritt & Protokoll ────────────────────
    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color=CLR_CARD, corner_radius=10)
        foot.pack(fill="both", padx=14, pady=(0, 12))

        line = ctk.CTkFrame(foot, fg_color="transparent")
        line.pack(fill="x", padx=14, pady=(12, 4))
        self.status_label = ctk.CTkLabel(line, text="Bereit.", text_color=CLR_GREY, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress = ctk.CTkProgressBar(foot, height=10, progress_color=CLR_ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=14, pady=(0, 8))

        self.log_box = ctk.CTkTextbox(foot, height=120, fg_color=CLR_BG,
                                      font=ctk.CTkFont(size=12, family="monospace"))
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    # ══════════════════════════════════════════════════════════
    # DRAG & DROP
    # ══════════════════════════════════════════════════════════
    def _drop_ziel(self, widget, handler) -> None:
        """Macht ein Bedienelement zum Ablageziel – falls tkinterdnd2 da ist."""
        if not DND_DA:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", handler)
        except Exception:
            pass                               # nicht schlimm, dann eben ohne

    def _pfade_aus_drop(self, event) -> list[str]:
        """
        Zerlegt die abgelegten Pfade.

        Tk liefert sie als eine Zeichenkette; Pfade mit Leerzeichen stehen
        dabei in geschweiften Klammern. splitlist() kennt diese Regel.
        """
        try:
            roh = self.tk.splitlist(event.data)
        except Exception:
            roh = str(getattr(event, "data", "")).split()
        pfade = []
        for eintrag in roh:
            pfad = str(eintrag).strip().strip("{}")
            if pfad and Path(pfad).exists():
                pfade.append(pfad)
        return pfade

    def _drop_auf_dateifeld(self, event):
        pfade = self._pfade_aus_drop(event)
        if not pfade:
            return
        self.file_var.set(pfade[0])
        self._log(f"🖱️ Übernommen: {Path(pfade[0]).name}")
        if len(pfade) > 1:
            self._in_warteschlange(pfade[1:])

    def _drop_in_warteschlange(self, event):
        self._in_warteschlange(self._pfade_aus_drop(event))

    def _drop_irgendwo(self, event):
        """Ablegen außerhalb der Felder: eine Datei ins Feld, mehrere in die Liste."""
        pfade = self._pfade_aus_drop(event)
        if not pfade:
            return
        if len(pfade) == 1:
            self.file_var.set(pfade[0])
            self.tabs.set("🎬 Datei")
            self._log(f"🖱️ Übernommen: {Path(pfade[0]).name}")
        else:
            self._in_warteschlange(pfade)

    def _in_warteschlange(self, pfade: list[str]) -> None:
        for pfad in pfade:
            self.schlange.hinzufuegen(self._job_bauen(pfad, "", "", ""))
        self._log(f"➕ {len(pfade)} Einträge in die Warteschlange gelegt.")
        self.tabs.set("📚 Warteschlange")

    # ══════════════════════════════════════════════════════════
    # AKTIONEN
    # ══════════════════════════════════════════════════════════
    def _choose_file(self):
        pfade = filedialog.askopenfilenames(title="Video oder Audio auswählen", filetypes=FILETYPES)
        if not pfade:
            return
        self.file_var.set(pfade[0])
        if len(pfade) > 1:
            self._in_warteschlange(list(pfade[1:]))

    def _choose_output_dir(self):
        path = filedialog.askdirectory(title="Ausgabeordner wählen")
        if path:
            self.output_var.set(path)

    def _on_model_change(self, value: str):
        self.model_hint.configure(text=MODELS.get(value, ""))

    def _current_settings(self) -> dict:
        return {
            "backend": self.backend_menu.get(),
            "model": self.model_menu.get(),
            "language": self.language_menu.get(),
            "output_dir": self.output_var.get(),
            "auto_save": bool(self.autosave_var.get()),
            "cookies_browser": self.cookies_var.get(),
            "sprecher": bool(self.sprecher_var.get()),
            "sprecherzahl": self.sprecherzahl_var.get(),
            "zf_art": self.zf_art_menu.get(),
        }

    def _save_settings_clicked(self):
        self.settings = self._current_settings()
        save_settings(self.settings)
        self._log("💾 Einstellungen gespeichert.")

    def _check_environment(self):
        lines = [ffmpeg_status(), backend_status(), tts_status(),
                 sprecher_status(), zusammenfassung_status()]
        try:
            import yt_dlp  # noqa: F401
            yt_dlp_da = True
            lines.append("✅ Online-Links: yt-dlp bereit")
        except ImportError:
            yt_dlp_da = False
            lines.append("⚠️ Online-Links brauchen yt-dlp (pip install yt-dlp)")
        lines.append("✅ Drag & Drop: aktiv" if DND_DA
                     else "⚠️ Drag & Drop braucht tkinterdnd2 (pip install tkinterdnd2)")

        datei = env_datei_finden()
        lines.append(f"📄 .env: {datei}" if datei else "📄 .env: keine gefunden (nur für Zusatzfunktionen nötig)")
        schluessel = gesetzte_schluessel()
        # Nur Namen anzeigen – ein Schlüssel gehört nicht auf den Bildschirm.
        lines.append("🔑 Schlüssel: " + (" · ".join(schluessel) if schluessel else "keine"))

        # Oben rechts ist wenig Platz – dort nur Häkchen, die Sätze stehen
        # ausführlich im Reiter "Einstellungen".
        def marke(name: str, da: bool) -> str:
            return f"{name} {'✅' if da else '❌'}"

        kurz = " · ".join((
            marke("ffmpeg", bool(find_ffmpeg())),
            marke("Whisper", bool(available_backends())),
            marke("Stimme", bool(available_engines())),
            marke("Links", yt_dlp_da),
            marke("Ziehen", DND_DA),
        ))
        self.env_label.configure(text=kurz)
        if hasattr(self, "status_text"):
            self.status_text.configure(text="\n".join(lines))
        for line in lines:
            if line.startswith(("❌", "⚠️")):
                self._log(line)

    # ── AUFTRÄGE ──────────────────────────────────────────────
    def _job_bauen(self, quelle: str, start: str, ende: str, dauer: str) -> Job:
        self.settings = self._current_settings()
        save_settings(self.settings)
        return Job(
            source=quelle,
            start=start or None,
            end=ende or None,
            duration=dauer or None,
            backend=self.backend_menu.get(),
            model=self.model_menu.get(),
            language=LANGUAGES.get(self.language_menu.get()),
            cookies_from_browser=self.cookies_var.get() or None,
            sprecher=bool(self.sprecher_var.get()),
            sprecherzahl=self._sprecherzahl(),
        )

    def _sprecherzahl(self) -> int | None:
        """Leeres oder unsinniges Feld heißt schlicht: Anzahl unbekannt."""
        try:
            zahl = int(str(self.sprecherzahl_var.get()).strip())
            return zahl if zahl > 0 else None
        except (TypeError, ValueError):
            return None

    def _start_file_job(self, sofort: bool = True):
        quelle = self.file_var.get().strip()
        if not quelle:
            messagebox.showinfo("Keine Datei", "Bitte zuerst eine Video- oder Audiodatei auswählen.")
            return
        self._auftrag_annehmen(quelle, self.file_start.get(), self.file_end.get(),
                               self.file_dur.get(), sofort)

    def _start_link_job(self, sofort: bool = True):
        quelle = self.url_var.get().strip()
        if not quelle:
            messagebox.showinfo("Kein Link", "Bitte zuerst einen Link einfügen.")
            return
        if not looks_like_url(quelle):
            messagebox.showwarning(
                "Link prüfen",
                "Das sieht nicht nach einem Link aus – er sollte mit http:// oder https:// beginnen.")
            return
        self._auftrag_annehmen(quelle, self.url_start.get(), self.url_end.get(),
                               self.url_dur.get(), sofort)

    def _auftrag_annehmen(self, quelle: str, start: str, ende: str, dauer: str, sofort: bool):
        try:
            job = self._job_bauen(quelle, start, ende, dauer)
        except ValueError as exc:
            messagebox.showwarning("Zeitangabe prüfen", str(exc))
            return

        auftrag = self.schlange.hinzufuegen(job)
        if not sofort:
            self._log(f"➕ [{auftrag.nummer}] in die Warteschlange gelegt.")
            self.tabs.set("📚 Warteschlange")
            return

        if self.schlange.laeuft:
            self._log(f"➕ [{auftrag.nummer}] angehängt – kommt nach dem laufenden Eintrag dran.")
            self.tabs.set("📚 Warteschlange")
            return

        self.progress.set(0)
        self._log("─" * 60)
        self.schlange.starten()

    def _queue_start(self):
        if self.schlange.laeuft:
            self._log("▶️ Läuft bereits.")
            return
        if not self.schlange.starten():
            messagebox.showinfo("Nichts zu tun", "In der Warteschlange wartet gerade kein Eintrag.")

    def _queue_abbrechen(self):
        if not self.schlange.laeuft:
            self._log("Es läuft gerade nichts.")
            return
        self.schlange.abbrechen()

    def _queue_aufraeumen(self):
        entfernt = self.schlange.erledigte_entfernen()
        self._log(f"🧹 {entfernt} erledigte Einträge entfernt." if entfernt
                  else "🧹 Nichts zu entfernen.")

    # ── BRÜCKE VOM HINTERGRUND IN DIE OBERFLÄCHE ──────────────
    def _schlangen_ereignis(self, art: str, wert) -> None:
        """Läuft im Arbeits-Thread – deshalb nur in die Queue legen, nichts zeichnen."""
        self.messages.put((art, wert))

    def _pump(self):
        """Holt Nachrichten aus dem Hintergrund in die Oberfläche."""
        neu_zeichnen = False
        try:
            while True:
                art, wert = self.messages.get_nowait()
                if art == "log":
                    self._log(str(wert))
                    self._set_status(str(wert)[:110])
                elif art == "fortschritt":
                    self._set_progress(wert)
                elif art == "aenderung":
                    neu_zeichnen = True
                elif art == "fertig":
                    self._auftrag_fertig(wert)
                    neu_zeichnen = True
                elif art == "fehler":
                    self._auftrag_gescheitert(wert)
                    neu_zeichnen = True
                elif art == "leer":
                    self._schlange_fertig()
                    neu_zeichnen = True
                elif art == "zusammenfassung":
                    self._zeige_zusammenfassung(str(wert))
                elif art == "zusammenfassung_fehler":
                    self.zf_laeuft = False
                    self._log(f"⚠️ Zusammenfassung nicht möglich: {str(wert).splitlines()[0]}")
                    messagebox.showinfo("Zusammenfassung nicht möglich", str(wert))
                elif art == "hinweis":
                    messagebox.showerror("Das hat nicht geklappt", str(wert))
        except queue.Empty:
            pass
        if neu_zeichnen:
            self._render_queue()
        self.after(120, self._pump)

    def _set_progress(self, anteil):
        if anteil is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(max(0.0, min(1.0, float(anteil))))

    def _auftrag_fertig(self, auftrag: Auftrag):
        self.transcript = auftrag.transcript
        self._render_transcript()
        if self.schlange.offen == 0:
            self.tabs.set("📝 Transkript")

        if self.autosave_var.get() and auftrag.transcript:
            try:
                geschrieben = save_all_formats(auftrag.transcript, self.output_var.get())
                self._log(f"💾 Gespeichert in {Path(geschrieben[0]).parent}")
            except Exception as exc:
                self._log(f"⚠️ Automatisches Speichern nicht möglich: {exc}")

    def _auftrag_gescheitert(self, auftrag: Auftrag):
        self._log(f"❌ [{auftrag.nummer}] {auftrag.name}: {auftrag.fehler}")
        # Bei einem einzelnen Eintrag darf ruhig ein Fenster aufgehen; bei
        # zwanzig Einträgen wäre das eine Klickorgie – dann reicht die Liste.
        if len(self.schlange.auftraege) == 1:
            messagebox.showerror("Das hat nicht geklappt", auftrag.fehler)

    def _schlange_fertig(self):
        self._set_progress(0.0 if self.schlange.offen else 1.0)
        self._set_status("✅ " + self.schlange.zusammenfassung())
        self._log("✅ " + self.schlange.zusammenfassung())

    # ── WARTESCHLANGE ANZEIGEN ────────────────────────────────
    def _render_queue(self):
        for kind in self.queue_list.winfo_children():
            kind.destroy()

        auftraege = self.schlange.auftraege
        self.queue_info.configure(text=self.schlange.zusammenfassung())
        if not auftraege:
            ctk.CTkLabel(
                self.queue_list,
                text="Noch nichts da.\n\nDateien hierher ziehen oder in den Reitern oben\n"
                     "auf „➕ In die Warteschlange“ klicken.",
                text_color=CLR_GREY, justify="left",
            ).pack(anchor="w", padx=16, pady=16)
            return

        for auftrag in auftraege:
            zeile = ctk.CTkFrame(self.queue_list, fg_color=CLR_CARD, corner_radius=8)
            zeile.pack(fill="x", padx=6, pady=4)

            ctk.CTkLabel(
                zeile, text=f"{STATUS_ZEICHEN.get(auftrag.status, '•')} {auftrag.nummer}",
                width=50, text_color=STATUS_FARBE.get(auftrag.status, CLR_GREY),
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(side="left", padx=(12, 6), pady=10)

            text = auftrag.name
            if auftrag.status == FEHLER and auftrag.fehler:
                text += f"   —   {auftrag.fehler.splitlines()[0][:70]}"
            elif auftrag.status == FERTIG and auftrag.transcript:
                text += f"   —   {len(auftrag.transcript.text.split())} Wörter"
            ctk.CTkLabel(
                zeile, text=text, anchor="w",
                text_color="#ffffff" if not auftrag.erledigt else CLR_GREY,
            ).pack(side="left", fill="x", expand=True)

            # Erst der Papierkorb, dann das Auge: was zuerst nach rechts
            # gepackt wird, sitzt außen – so stehen die Papierkörbe in allen
            # Zeilen untereinander, auch wenn das Auge mal fehlt.
            if auftrag.status != LAEUFT:
                ctk.CTkButton(zeile, text="🗑", width=40, fg_color=CLR_CARD,
                              hover_color=CLR_RED,
                              command=lambda a=auftrag: self._entferne_auftrag(a)).pack(side="right", padx=(0, 10))
            if auftrag.status == FERTIG:
                ctk.CTkButton(zeile, text="👁", width=40,
                              command=lambda a=auftrag: self._zeige_auftrag(a)).pack(side="right", padx=(0, 4))

    def _zeige_auftrag(self, auftrag: Auftrag):
        if auftrag.transcript:
            self.transcript = auftrag.transcript
            self._render_transcript()
            self.tabs.set("📝 Transkript")

    def _entferne_auftrag(self, auftrag: Auftrag):
        if self.schlange.entfernen(auftrag):
            self._render_queue()

    # ── TRANSKRIPT ────────────────────────────────────────────
    def _render_transcript(self):
        if not self.transcript:
            return
        text = self.transcript.to_text(with_timestamps=bool(self.timestamp_var.get()))
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.insert("1.0", text)

        transcript = self.transcript
        parts = [
            f"🗣️ {transcript.language or 'unbekannt'}",
            f"🧠 {transcript.backend} / {transcript.model}",
            f"✂️ {len(transcript.segments)} Abschnitte",
            f"📝 {len(transcript.text.split())} Wörter",
        ]
        if transcript.duration:
            parts.append(f"⏱️ {format_hms(transcript.duration)}")
        if transcript.offset:
            parts.append(f"↪️ ab {format_hms(transcript.offset)} im Original")
        self.transcript_info.configure(text="   ·   ".join(parts))

    def _require_transcript(self) -> bool:
        if self.transcript and self.transcript.segments:
            return True
        messagebox.showinfo("Noch nichts da", "Es gibt noch kein Transkript zum Weiterverarbeiten.")
        return False

    def _copy_transcript(self):
        if not self._require_transcript():
            return
        self.clipboard_clear()
        self.clipboard_append(self.transcript_box.get("1.0", "end").strip())
        self._log("📋 Transkript in die Zwischenablage kopiert.")

    def _save_transcript_as(self):
        if not self._require_transcript():
            return
        stem = safe_filename(self.transcript.title or "transkript")
        path = filedialog.asksaveasfilename(
            title="Transkript speichern",
            initialdir=self.output_var.get(),
            initialfile=f"{stem}.txt",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Untertitel SRT", "*.srt"),
                       ("Untertitel VTT", "*.vtt"), ("Markdown", "*.md")],
        )
        if not path:
            return
        try:
            self.transcript.export(path, with_timestamps=bool(self.timestamp_var.get()))
            self._log(f"💾 Gespeichert: {path}")
        except Exception as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))

    def _save_all_formats(self):
        if not self._require_transcript():
            return
        try:
            geschrieben = save_all_formats(self.transcript, self.output_var.get())
            self._log("💾 " + " · ".join(p.name for p in geschrieben))
            open_folder(self.output_var.get())
        except Exception as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))

    # ── VORLESEN ──────────────────────────────────────────────
    def _load_voices(self):
        try:
            self._voices = list_voices()
        except Exception:
            self._voices = []
        names = ["Standard"] + [v.name for v in self._voices]
        try:
            self.voice_menu.configure(values=names)
        except Exception:
            pass

    def _selected_voice_id(self) -> str | None:
        name = self.voice_menu.get()
        for voice in self._voices:
            if voice.name == name:
                return voice.id
        return None

    def _tts_take_transcript(self):
        if not self._require_transcript():
            return
        self.tts_box.delete("1.0", "end")
        self.tts_box.insert("1.0", self.transcript.text)
        self.tabs.set("🔊 Vorlesen")

    def _speak_transcript(self):
        if not self._require_transcript():
            return
        self._speak(self.transcript.text)

    def _speak_textbox(self):
        self._speak(self.tts_box.get("1.0", "end").strip())

    def _speak(self, text: str):
        if not text.strip():
            messagebox.showinfo("Kein Text", "Bitte zuerst etwas eintippen oder das Transkript übernehmen.")
            return

        stimme = self._selected_voice_id()
        tempo = int(self.rate_slider.get())

        def work():
            try:
                speak(text, voice=stimme, rate=tempo)
                self.messages.put(("log", "🔊 Vorlesen beendet."))
            except Exception as exc:
                self.messages.put(("hinweis", str(exc)))

        self._log("🔊 Vorlesen …")
        threading.Thread(target=work, daemon=True).start()

    def _save_speech(self):
        text = self.tts_box.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Kein Text", "Bitte zuerst etwas eintippen.")
            return
        path = filedialog.asksaveasfilename(
            title="Sprachausgabe speichern",
            initialdir=self.output_var.get(),
            initialfile="sprachausgabe.wav",
            defaultextension=".wav",
            filetypes=[("WAV (offline)", "*.wav"), ("MP3 (über gTTS)", "*.mp3")],
        )
        if not path:
            return

        stimme = self._selected_voice_id()
        tempo = int(self.rate_slider.get())

        def work():
            try:
                save_speech(text, path, voice=stimme, rate=tempo)
                self.messages.put(("log", f"💾 Audiodatei gespeichert: {path}"))
            except Exception as exc:
                self.messages.put(("hinweis", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    # ── KLEINKRAM ─────────────────────────────────────────────
    def _log(self, message: str):
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def _set_status(self, message: str):
        self.status_label.configure(text=message)

    def _on_close(self):
        try:
            save_settings(self._current_settings())
        except Exception:
            pass
        if self.schlange.laeuft:
            if not messagebox.askokcancel(
                "Noch am Arbeiten",
                "Es läuft noch eine Transkription. Wirklich beenden?\n"
                "Der laufende Eintrag geht dabei verloren.",
            ):
                return
            self.schlange.abbrechen()
        self.destroy()


def oberflaeche_starten() -> None:
    VoiceApp().mainloop()



# ══════════════════════════════════════════════════════════════════════
# aus cli.py
# ══════════════════════════════════════════════════════════════════════

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

    # gleich mehrere Videos hintereinander, alles in einen Ordner
    python -m voice2text *.mp4 --ordner ~/Transkripte

    # Gespräch mit Sprecher-Erkennung, dazu ein Protokoll
    python -m voice2text besprechung.mp4 --sprecher --zusammenfassung protokoll

    # Text vorlesen lassen
    python -m voice2text --sprich "Hallo Sven, das Transkript ist fertig."
"""


import argparse
import sys
from pathlib import Path



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice2text",
        description="🎙️ Video, Audio oder Online-Link in lesbaren Text verwandeln.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Die App spricht Deutsch, also darf auch die Hilfe deutsch heißen.
    # "-h" und "--help" bleiben daneben bestehen.
    parser.add_argument("--hilfe", action="help", help="Diese Hilfe anzeigen und beenden")

    parser.add_argument("quelle", nargs="*",
                        help="Dateipfad oder Online-Link – auch mehrere hintereinander")

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
    erkennung.add_argument("--sprecher", action="store_true",
                           help="Wer sagt was? (braucht pyannote.audio + Hugging-Face-Token)")
    erkennung.add_argument("--sprecherzahl", type=int,
                           help="Anzahl der Sprecher, falls bekannt – hilft der Erkennung")

    ausgabe = parser.add_argument_group("Ausgabe")
    ausgabe.add_argument("--ausgabe", "-o", help="Zieldatei (.txt · .srt · .vtt · .md)")
    ausgabe.add_argument("--ordner", help="Alle vier Formate in diesen Ordner schreiben")
    ausgabe.add_argument("--zeitstempel", action="store_true", help="Zeitstempel mit ausgeben")
    ausgabe.add_argument("--still", action="store_true", help="Keine Fortschrittsmeldungen")
    ausgabe.add_argument("--zusammenfassung", "-z", nargs="?", const="stichpunkte",
                         choices=list(ARTEN),
                         help="Transkript zusätzlich zusammenfassen (Standard: stichpunkte)")

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
    print("   " + tts_status())
    print("   " + sprecher_status())
    print("   " + zusammenfassung_status())
    try:
        import yt_dlp  # noqa: F401
        print("   ✅ Online-Links: yt-dlp bereit")
    except ImportError:
        print("   ⚠️ Online-Links brauchen yt-dlp (pip install yt-dlp)")


    datei = env_datei_finden()
    print(f"   📄 .env: {datei}" if datei else "   📄 .env: keine gefunden (nur nötig für Zusatzfunktionen)")
    schluessel = gesetzte_schluessel()
    # Nur die Namen – ein Schlüssel hat auf dem Bildschirm nichts verloren.
    print("   🔑 Schlüssel gefunden: " + (" · ".join(schluessel) if schluessel else "keine"))


def kommandozeile(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        gui_main = oberflaeche_starten
        gui_main()
        return 0

    if args.status:
        _print_status()
        return 0

    # ── Text → Sprache ────────────────────────────────────────
    if args.sprich:
        try:
            if args.sprachdatei:
                path = save_speech(args.sprich, args.sprachdatei)
                print(f"💾 Gespeichert: {path}")
            else:
                speak(args.sprich)
        except TtsError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        return 0

    if not args.quelle:
        parser.print_help()
        return 1

    if len(args.quelle) > 1 and args.ausgabe:
        print("❌ --ausgabe schreibt in genau eine Datei. Bei mehreren Quellen bitte --ordner nehmen.",
              file=sys.stderr)
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

    mehrere = len(args.quelle) > 1
    fehlgeschlagen = 0

    for nummer, quelle in enumerate(args.quelle, start=1):
        if mehrere and not args.still:
            print(f"\n── [{nummer}/{len(args.quelle)}] {quelle}", file=sys.stderr)

        job = Job(
            source=quelle,
            start=args.start,
            end=args.ende,
            duration=args.dauer,
            backend=args.backend,
            model=args.modell,
            language=sprache,
            cookies_from_browser=args.cookies,
            sprecher=args.sprecher,
            sprecherzahl=args.sprecherzahl,
        )

        try:
            transcript = run_job(job, progress=report)
        except Exception as exc:
            print(f"❌ {quelle}: {exc}", file=sys.stderr)
            fehlgeschlagen += 1
            # Bei mehreren Quellen bringt Aufgeben nichts – die übrigen
            # Videos können ja trotzdem in Ordnung sein.
            if not mehrere:
                return 1
            continue

        if args.zusammenfassung:
            try:
                transcript.summary = zusammenfassen(
                    transcript.text, art=args.zusammenfassung, progress=report
                )
            except ZusammenfassungError as exc:
                # Das Transkript ist fertig – daran soll eine fehlende
                # Zusammenfassung nichts ändern.
                print(f"⚠️ Zusammenfassung nicht möglich: {exc}", file=sys.stderr)

        if args.ausgabe:
            path = transcript.export(args.ausgabe, with_timestamps=args.zeitstempel)
            print(f"💾 Gespeichert: {path}")
        elif args.ordner:
            for path in save_all_formats(transcript, args.ordner):
                print(f"💾 {path}")
        else:
            if mehrere:
                print(f"\n=== {transcript.title or quelle} ===")
            if transcript.summary:
                print("--- Zusammenfassung ---")
                print(transcript.summary)
                print("--- Transkript ---")
            print(transcript.to_text(with_timestamps=args.zeitstempel))

        if not args.still:
            info = f"🗣️ {transcript.language or '?'} · {len(transcript.segments)} Abschnitte"
            if transcript.duration:
                info += f" · {format_hms(transcript.duration)}"
            print(info, file=sys.stderr)

    if mehrere and not args.still:
        geschafft = len(args.quelle) - fehlgeschlagen
        print(f"\n✅ {geschafft} von {len(args.quelle)} Quellen transkribiert.", file=sys.stderr)
    return 1 if fehlgeschlagen else 0



# ══════════════════════════════════════════════════════════════════════
# START
# ══════════════════════════════════════════════════════════════════════
def main() -> int:
    """
    Ohne Argumente öffnet sich das Fenster, mit Argumenten läuft die
    Kommandozeile. Ein Doppelklick übergibt keine Argumente – also
    landet man beim Fenster, und genau das ist gewollt.
    """
    if len(sys.argv) > 1:
        return kommandozeile()

    ersthilfe()
    try:
        oberflaeche_starten()
    except Exception as fehler:
        print()
        print("  ❌ Das Fenster ließ sich nicht öffnen:")
        print(f"     {fehler}")
        print()
        print("  Unter Linux fehlt meist tkinter:  sudo apt install python3-tk")
        print()
        try:
            input("  Enter zum Beenden ")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
