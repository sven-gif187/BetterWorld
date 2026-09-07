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

from __future__ import annotations

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
