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
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["env_datei_finden", "env_lesen", "env_laden", "gesetzte_schluessel"]

# Die Namen, auf die es ankommt – nur zur Anzeige, nie mit Wert.
BEKANNTE_SCHLUESSEL = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HUGGINGFACE_TOKEN",
    "HF_TOKEN",
)


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
        if ueberschreiben or not os.getenv(name):
            os.environ[name] = wert
            gesetzt.append(name)
    return gesetzt


def gesetzte_schluessel() -> list[str]:
    """Welche der bekannten Schlüssel vorhanden sind – nur die Namen."""
    return [name for name in BEKANNTE_SCHLUESSEL if os.getenv(name)]
