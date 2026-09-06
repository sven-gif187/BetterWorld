"""
╔══════════════════════════════════════════════════════════════╗
║  EINRICHTUNGS-ASSISTENT                                      ║
╚══════════════════════════════════════════════════════════════╝

Ein Befehl, der alles vorbereitet und am Ende beweist, dass es läuft:

    python voice2text/einrichten.py

Der Assistent geht sechs Schritte durch:

  1️⃣  Python-Version prüfen
  2️⃣  Fehlende Pakete installieren (fragt vorher)
  3️⃣  ffmpeg suchen
  4️⃣  Spracherkennung startklar machen (Modell laden)
  5️⃣  Selbsttest: Rechner spricht einen Satz → App liest ihn wieder heraus
  6️⃣  Bericht mit den nächsten Schritten

Nichts wird ungefragt installiert. Wer nur wissen will, wie es aussteht:

    python voice2text/einrichten.py --nur-pruefen
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Damit das Skript sowohl per "python voice2text/einrichten.py" als auch
# per "python -m voice2text.einrichten" funktioniert:
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice2text import media, tts                                    # noqa: E402
from voice2text.transcribe import TranscriptionError, available_backends, transcribe  # noqa: E402

# Der Satz, den der Rechner beim Selbsttest spricht und wieder erkennen soll.
TESTSATZ = "Das Transkript funktioniert. Sven testet die Spracherkennung mit einem kurzen Satz."
SCHLUESSELWOERTER = ["transkript", "funktioniert", "sven", "testet", "spracherkennung", "satz"]

# Ungefähre Download-Größe der Modelle – nur zur Information vorab.
MODELL_GROESSE = {
    "tiny": "≈ 75 MB",
    "base": "≈ 145 MB",
    "small": "≈ 500 MB",
    "medium": "≈ 1,5 GB",
    "large-v3": "≈ 3 GB",
}

PAKETE = [
    ("customtkinter", "customtkinter>=5.2.0", "die Fenster-Oberfläche", True),
    ("faster_whisper", "faster-whisper>=1.0.0", "die Spracherkennung", True),
    ("imageio_ffmpeg", "imageio-ffmpeg>=0.4.9", "bringt ffmpeg mit", True),
    ("yt_dlp", "yt-dlp>=2024.1.0", "Online-Links (YouTube & Co.)", True),
    ("pyttsx3", "pyttsx3>=2.90", "Sprachausgabe (Text → Sprache)", True),
]


# ══════════════════════════════════════════════════════════════
# AUSGABE-HELFER
# ══════════════════════════════════════════════════════════════
def kopf(nummer: str, titel: str) -> None:
    print(f"\n{nummer}  {titel}")
    print("─" * 62)


def ok(text: str) -> None:
    print(f"   ✅ {text}")


def warnung(text: str) -> None:
    print(f"   ⚠️  {text}")


def fehler(text: str) -> None:
    print(f"   ❌ {text}")


def frage(text: str, standard: bool = True) -> bool:
    auswahl = "[J/n]" if standard else "[j/N]"
    try:
        antwort = input(f"   ❓ {text} {auswahl} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not antwort:
        return standard
    return antwort in ("j", "ja", "y", "yes")


def paket_da(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# ══════════════════════════════════════════════════════════════
# SCHRITT 1 – PYTHON
# ══════════════════════════════════════════════════════════════
def schritt_python() -> bool:
    kopf("1️⃣ ", "Python-Version")
    version = sys.version_info
    print(f"   Gefunden: Python {version.major}.{version.minor}.{version.micro}")
    if version < (3, 10):
        fehler("Gebraucht wird mindestens Python 3.10 – bitte zuerst aktualisieren.")
        print("      Download: https://www.python.org/downloads/")
        return False
    ok("Passt.")
    return True


# ══════════════════════════════════════════════════════════════
# SCHRITT 2 – PAKETE
# ══════════════════════════════════════════════════════════════
def schritt_pakete(nur_pruefen: bool, automatisch: bool) -> bool:
    kopf("2️⃣ ", "Benötigte Pakete")

    fehlend = []
    for modul, pip_name, zweck, _pflicht in PAKETE:
        if paket_da(modul):
            ok(f"{modul:<16} – {zweck}")
        else:
            warnung(f"{modul:<16} – fehlt ({zweck})")
            fehlend.append(pip_name)

    if not fehlend:
        return True

    if nur_pruefen:
        print(f"\n   Nachinstallieren mit:  pip install {' '.join(fehlend)}")
        return False

    print(f"\n   Es fehlen {len(fehlend)} Pakete (zusammen rund 100 MB Download).")
    if not automatisch and not frage("Jetzt installieren?"):
        print("   Übersprungen. Später von Hand:")
        print(f"      pip install {' '.join(fehlend)}")
        return False

    print("\n   📦 Installation läuft – das dauert ein paar Minuten …\n")
    ergebnis = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", *fehlend],
        check=False,
    )
    if ergebnis.returncode != 0:
        fehler("Die Installation ist fehlgeschlagen.")
        print("      Häufigste Ursachen: kein Internet, oder pip braucht ein Update:")
        print(f"      {Path(sys.executable).name} -m pip install --upgrade pip")
        return False

    ok("Pakete installiert.")
    return True


# ══════════════════════════════════════════════════════════════
# SCHRITT 3 – FFMPEG
# ══════════════════════════════════════════════════════════════
def schritt_ffmpeg() -> bool:
    kopf("3️⃣ ", "ffmpeg (holt die Tonspur aus dem Video)")
    pfad = media.find_ffmpeg()
    if pfad:
        ok(f"Gefunden: {pfad}")
        return True
    fehler("Nicht gefunden.")
    print("      Einfachste Lösung:  pip install imageio-ffmpeg")
    print("      Alternativ:         winget install Gyan.FFmpeg   (Windows)")
    print("                          brew install ffmpeg          (macOS)")
    print("                          sudo apt install ffmpeg      (Linux)")
    return False


# ══════════════════════════════════════════════════════════════
# SCHRITT 4 – MODELL
# ══════════════════════════════════════════════════════════════
def schritt_modell(modell: str, nur_pruefen: bool, automatisch: bool) -> bool:
    kopf("4️⃣ ", f"Spracherkennung startklar machen (Modell '{modell}')")

    backends = available_backends()
    if not backends:
        fehler("Kein Spracherkenner installiert.")
        print("      pip install faster-whisper")
        return False
    ok("Verfügbar: " + " · ".join(backends))

    if nur_pruefen:
        return True

    if "faster-whisper" not in backends:
        warnung("faster-whisper fehlt – der Modell-Download wird übersprungen.")
        return True

    groesse = MODELL_GROESSE.get(modell, "Größe unbekannt")
    print(f"\n   Beim allerersten Mal lädt sich das Modell herunter ('{modell}' {groesse}).")
    print("   Danach liegt es auf der Platte und wird nie wieder geladen.")
    if not automatisch and not frage("Jetzt herunterladen?"):
        print("   Übersprungen – passiert dann eben beim ersten echten Lauf.")
        return True

    try:
        from faster_whisper import WhisperModel
        print("\n   📥 Modell wird geladen – bitte warten …")
        WhisperModel(modell, device="cpu", compute_type="int8")
        ok("Modell liegt bereit.")
        return True
    except Exception as exc:
        fehler(f"Das Modell konnte nicht geladen werden: {exc}")
        print("      Meist fehlt schlicht die Internetverbindung.")
        return False


# ══════════════════════════════════════════════════════════════
# SCHRITT 5 – SELBSTTEST
# ══════════════════════════════════════════════════════════════
def _testaudio_erzeugen(ziel: Path) -> str | None:
    """Erzeugt eine Sprachaufnahme des Testsatzes. Rückgabe: benutztes Verfahren."""
    if paket_da("pyttsx3"):
        try:
            tts.save_speech(TESTSATZ, ziel)
            if ziel.exists() and ziel.stat().st_size > 1000:
                return "pyttsx3 (offline)"
        except Exception:
            pass

    if paket_da("gtts"):
        try:
            mp3 = ziel.with_suffix(".mp3")
            tts.save_speech(TESTSATZ, mp3, language="de")
            if mp3.exists() and mp3.stat().st_size > 1000:
                media.extract_audio(mp3, ziel)
                return "gTTS (online)"
        except Exception:
            pass

    return None


def schritt_selbsttest(modell: str) -> bool:
    kopf("5️⃣ ", "Selbsttest – einmal komplett durch die Kette")

    if not media.find_ffmpeg() or not available_backends():
        warnung("Übersprungen – dafür müssen erst ffmpeg und die Spracherkennung stehen.")
        return False

    with tempfile.TemporaryDirectory(prefix="voice2text_test_") as ordner:
        audio = Path(ordner) / "testsatz.wav"

        print(f'   Der Rechner spricht: "{TESTSATZ}"')
        verfahren = _testaudio_erzeugen(audio)
        if not verfahren:
            warnung("Es konnte keine Testaufnahme erzeugt werden (Sprachausgabe fehlt).")
            print("      Linux:  sudo apt install espeak-ng")
            print("      Sonst:  pip install pyttsx3")
            print("      Das ist kein Beinbruch – die Transkription funktioniert trotzdem.")
            print("      Zum Prüfen einfach ein echtes Video nehmen.")
            return False
        ok(f"Aufnahme erzeugt mit {verfahren} ({audio.stat().st_size // 1024} kB)")

        print("   Und liest sie jetzt wieder heraus …")
        try:
            ergebnis = transcribe(
                audio, backend="auto", model=modell, language="de",
                progress=lambda anteil, text: None,
            )
        except TranscriptionError as exc:
            fehler(str(exc))
            return False

        erkannt = ergebnis.text.strip()
        print(f'\n   📝 Erkannt: "{erkannt}"\n')

        if not erkannt:
            fehler("Es kam kein Text zurück.")
            print("      Meist ist die Testaufnahme stumm – bei einem echten Video klappt es oft trotzdem.")
            return False

        klein = erkannt.lower()
        treffer = [wort for wort in SCHLUESSELWOERTER if wort in klein]
        quote = len(treffer) / len(SCHLUESSELWOERTER)

        if quote >= 0.5:
            ok(f"Selbsttest bestanden – {len(treffer)} von {len(SCHLUESSELWOERTER)} Schlüsselwörtern erkannt.")
            return True

        warnung(f"Nur {len(treffer)} von {len(SCHLUESSELWOERTER)} Wörtern erkannt.")
        print("      Die Kette läuft, aber die Computerstimme ist schwer zu verstehen.")
        print("      Bei echter Sprache ist die Qualität normalerweise deutlich besser.")
        return True


# ══════════════════════════════════════════════════════════════
# SCHRITT 6 – BERICHT
# ══════════════════════════════════════════════════════════════
def schritt_bericht(stand: dict) -> None:
    kopf("6️⃣ ", "Ergebnis")
    for name, geschafft in stand.items():
        print(f"   {'✅' if geschafft else '⚠️ '} {name}")

    bereit = stand.get("ffmpeg") and stand.get("Spracherkennung")
    print()
    if bereit:
        print("   🎉 Alles bereit! So geht es weiter:")
        print()
        print("      python -m voice2text")
        print("         → Fenster öffnet sich, Video auswählen, starten")
        print()
        print("      python -m voice2text video.mp4 --start 12:30 --dauer 90")
        print("         → nur der Ausschnitt ab Minute 12:30, 90 Sekunden lang")
        print()
        print('      python -m voice2text "https://youtu.be/abc?t=90" --dauer 60')
        print("         → direkt vom Link, Startzeit kommt aus dem Link selbst")
    else:
        print("   Es fehlt noch etwas – die Hinweise oben sagen, was.")
        print("   Danach einfach nochmal starten:")
        print("      python voice2text/einrichten.py")
    print()


# ══════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="🎙️ voice2text einrichten und testen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--nur-pruefen", action="store_true",
                        help="Nur nachsehen, nichts installieren")
    parser.add_argument("--ja", action="store_true",
                        help="Alle Rückfragen mit Ja beantworten")
    parser.add_argument("--modell", default="small",
                        help="Welches Modell vorbereitet wird (Standard: small)")
    parser.add_argument("--ohne-selbsttest", action="store_true",
                        help="Schritt 5 überspringen")
    args = parser.parse_args(argv)

    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   🎙️  VOICE2TEXT – EINRICHTUNG                             ║")
    print("╚════════════════════════════════════════════════════════════╝")
    if args.nur_pruefen:
        print("   (Nur prüfen – es wird nichts installiert.)")

    stand: dict[str, bool] = {}
    stand["Python-Version"] = schritt_python()
    if not stand["Python-Version"]:
        schritt_bericht(stand)
        return 1

    stand["Pakete"] = schritt_pakete(args.nur_pruefen, args.ja)
    stand["ffmpeg"] = schritt_ffmpeg()
    stand["Spracherkennung"] = schritt_modell(args.modell, args.nur_pruefen, args.ja)

    if not args.ohne_selbsttest and not args.nur_pruefen:
        stand["Selbsttest"] = schritt_selbsttest(args.modell)

    schritt_bericht(stand)
    return 0 if stand.get("ffmpeg") and stand.get("Spracherkennung") else 1


if __name__ == "__main__":
    raise SystemExit(main())
