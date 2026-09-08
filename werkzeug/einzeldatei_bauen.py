"""
╔══════════════════════════════════════════════════════════════╗
║  EINZELDATEI BAUEN – aus 13 Modulen wird eine .py            ║
╚══════════════════════════════════════════════════════════════╝

Das Paket voice2text/ ist sauber in Module aufgeteilt – gut zum
Entwickeln und Testen, unpraktisch zum Verschicken. Wer die App nur
benutzen will, möchte eine Datei: speichern, doppelklicken, fertig.

Dieses Skript klebt die Module in der richtigen Reihenfolge zusammen:

    python werkzeug/einzeldatei_bauen.py

Ergebnis: voice2text_komplett.py

Dabei wird geprüft, ob sich zwei Module denselben Namen teilen – in einer
gemeinsamen Datei würde der spätere den früheren stillschweigend
überschreiben, und der Fehler zeigte sich erst beim Benutzen.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
PAKET = WURZEL / "voice2text"
ZIEL = WURZEL / "voice2text_komplett.py"

# Reihenfolge nach Abhängigkeiten: was zuerst gebraucht wird, steht oben.
REIHENFOLGE = [
    "konfig.py",
    "timecode.py",
    "media.py",
    "sprecher.py",
    "transcribe.py",
    "zusammenfassung.py",
    "tts.py",
    "pipeline.py",
    "warteschlange.py",
    "app.py",
    "cli.py",
]

# Zwei Module haben je eine Funktion "main". In einer Datei müssen die
# unterschiedlich heißen, sonst gewinnt die letzte.
UMBENENNEN = {
    "app.py": {"main": "oberflaeche_starten"},
    "cli.py": {"main": "kommandozeile"},
}

# In einer einzigen Datei gibt es keine Module mehr. Wer "tts.speak()"
# schreibt, meint dann schlicht "speak()". Diese Präfixe werden entfernt.
MODULNAMEN = ["media", "tts", "konfig", "timecode", "transcribe",
              "sprecher", "zusammenfassung", "pipeline", "warteschlange"]
# "media.prepare_source" muss aufgelöst werden, "media.py" in einem
# Kommentar dagegen nicht – deshalb sind Dateiendungen ausgenommen.
ENDUNGEN = ("py", "md", "txt", "json", "yml", "yaml", "bat", "srt", "vtt")
PRAEFIX = re.compile(
    r"(?<![\w.])(" + "|".join(MODULNAMEN) + r")\."
    r"(?!(?:" + "|".join(ENDUNGEN) + r")\b)"
    r"(?=[A-Za-z_])"
)

# Zeilen, die beim Zusammenkleben verschwinden müssen
WEG = re.compile(
    r"^\s*(from\s+\.\S*\s+import|from\s+\.\s+import|from\s+voice2text|import\s+voice2text|from\s+__future__\s+import)"
)


def oberste_namen(quelltext: str, datei: str) -> set[str]:
    """Alle Namen, die ein Modul auf oberster Ebene definiert."""
    namen = set()
    for knoten in ast.parse(quelltext, filename=datei).body:
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            namen.add(knoten.name)
        elif isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name):
                    namen.add(ziel.id)
        elif isinstance(knoten, ast.AnnAssign) and isinstance(knoten.target, ast.Name):
            namen.add(knoten.target.id)
    return namen


def hauptblock_entfernen(quelltext: str) -> str:
    """
    Schneidet 'if __name__ == "__main__":' samt Rumpf heraus.

    Jedes Modul hat so einen Block, damit es einzeln startbar ist. In der
    zusammengeklebten Datei ist __name__ aber für alle "__main__" – dann
    feuern sie beim Einlesen alle gleichzeitig. Genau so öffnete sich beim
    Aufruf "--status" plötzlich das Fenster.
    """
    zeilen = quelltext.splitlines()
    ergebnis = []
    ueberspringen = False
    for zeile in zeilen:
        if re.match(r'^if __name__ == ["\']__main__["\']:', zeile):
            ueberspringen = True
            continue
        if ueberspringen:
            # Der Rumpf ist eingerückt; die erste Zeile ohne Einrückung
            # gehört wieder zum Modul.
            if zeile.strip() == "" or zeile[:1] in (" ", "\t"):
                continue
            ueberspringen = False
        ergebnis.append(zeile)
    return "\n".join(ergebnis)


ALIAS = re.compile(r"^(\s*)from\s+\.(\w+)\s+import\s+(.+)$")


def umbenennungen_retten(zeile: str) -> list[str]:
    """
    Macht aus "from .zusammenfassung import ARTEN as ZF_ARTEN"
    die Zuweisung "ZF_ARTEN = ARTEN".

    Ohne diesen Schritt wäre der neue Name in der Einzeldatei unbekannt –
    ein Fehler, der sich erst beim Benutzen zeigt, nicht beim Bauen.
    """
    treffer = ALIAS.match(zeile)
    if not treffer:
        return []
    einrueckung, herkunft, teile = treffer.groups()
    zuweisungen = []
    for stueck in teile.split("#")[0].split(","):
        stueck = stueck.strip()
        if " as " not in stueck:
            continue
        name, _, neuer_name = stueck.partition(" as ")
        name, neuer_name = name.strip(), neuer_name.strip()
        # Falls das Ziel beim Zusammenkleben selbst umbenannt wurde
        name = UMBENENNEN.get(f"{herkunft}.py", {}).get(name, name)
        zuweisungen.append(f"{einrueckung}{neuer_name} = {name}")
    return zuweisungen


def modul_lesen(datei: str) -> str:
    quelltext = hauptblock_entfernen((PAKET / datei).read_text(encoding="utf-8"))
    quelltext = PRAEFIX.sub("", quelltext)
    for alt, neu in UMBENENNEN.get(datei, {}).items():
        quelltext = re.sub(rf"^def {alt}\(", f"def {neu}(", quelltext, flags=re.MULTILINE)
        quelltext = quelltext.replace(f"    {alt}()\n", f"    {neu}()\n")
        quelltext = quelltext.replace(f"return {alt}()", f"return {neu}()")
    return quelltext


def bauen() -> Path:
    # ── Namenskonflikte aufspüren, bevor etwas zusammengeklebt wird ──
    gesehen: dict[str, str] = {}
    konflikte: list[str] = []
    for datei in REIHENFOLGE:
        quelltext = modul_lesen(datei)
        for name in oberste_namen(quelltext, datei):
            if name.startswith("__"):
                continue
            if name in gesehen and gesehen[name] != datei:
                konflikte.append(f"  {name}  ({gesehen[name]} ↔ {datei})")
            gesehen[name] = datei

    # Harmlos: identische Hilfsfunktionen und Typkürzel, die mehrfach
    # gleich definiert sind. Alles andere muss umbenannt werden.
    unbedenklich = {"_module_available", "ProgressFn", "__all__"}
    echte = [k for k in konflikte if k.strip().split()[0] not in unbedenklich]
    if echte:
        print("❌ Namenskonflikte – bitte erst umbenennen:")
        print("\n".join(echte))
        return None

    teile = [KOPF]
    for datei in REIHENFOLGE:
        quelltext = modul_lesen(datei)
        zeilen = []
        for zeile in quelltext.splitlines():
            if not WEG.match(zeile):
                zeilen.append(zeile)
                continue
            # Ein Import mit Umbenennung ("ARTEN as ZF_ARTEN") darf nicht
            # einfach verschwinden – sonst fehlt der neue Name. Aus dem
            # Import wird deshalb eine schlichte Zuweisung.
            zeilen.extend(umbenennungen_retten(zeile))
        teile.append(
            f"\n\n# {'═' * 70}\n"
            f"# aus {datei}\n"
            f"# {'═' * 70}\n"
        )
        teile.append("\n".join(zeilen).strip() + "\n")
    teile.append(FUSS)

    ergebnis = "\n".join(teile)

    # Selbstprüfung: nichts darf übrig bleiben, was es in einer Datei
    # nicht mehr gibt – weder Modulnamen noch fremde Hauptblöcke.
    uebrig = sorted(set(PRAEFIX.findall(ergebnis)))
    if uebrig:
        print(f"❌ Nicht aufgelöste Modulnamen: {', '.join(uebrig)}")
        return None
    if ergebnis.count('__name__ == "__main__"') != 1:
        print("❌ Es ist mehr als ein Hauptblock übrig geblieben.")
        return None

    ZIEL.write_text(ergebnis, encoding="utf-8")
    return ZIEL


KOPF = '''#!/usr/bin/env python3
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
'''

FUSS = '''

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
'''


if __name__ == "__main__":
    pfad = bauen()
    if pfad is None:
        sys.exit(1)
    zeilen = pfad.read_text(encoding="utf-8").count("\n")
    print(f"✅ {pfad.name} gebaut · {zeilen} Zeilen · {pfad.stat().st_size // 1024} kB")
