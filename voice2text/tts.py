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

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Voice", "TtsError", "available_engines", "tts_status",
    "list_voices", "speak", "save_speech", "windows_sprachausgabe_da",
]


class TtsError(RuntimeError):
    """Vorlesen oder Speichern hat nicht geklappt."""


@dataclass
class Voice:
    """Eine Stimme des Systems."""

    id: str
    name: str

    def __str__(self) -> str:
        return self.name


# ══════════════════════════════════════════════════════════════
# WINDOWS-EIGENE SPRACHAUSGABE
# ══════════════════════════════════════════════════════════════
# Windows bringt seit jeher eine Sprachausgabe mit (System.Speech).
# Die braucht kein einziges Zusatzpaket und ist damit die verlässlichste
# Variante überhaupt – gerade weil pyttsx3 auf Windows gern an einer
# halb installierten pywin32-Komponente scheitert ("No module named
# 'pywintypes'"). Genau dann springt diese Rückfallebene ein.

def _powershell() -> str | None:
    """Pfad zur PowerShell – nur unter Windows vorhanden."""
    if sys.platform != "win32":
        return None
    from shutil import which
    return which("powershell") or which("pwsh")


def windows_sprachausgabe_da() -> bool:
    return _powershell() is not None


def _tempo_umrechnen(rate: int | None) -> int:
    """
    pyttsx3 zählt Wörter pro Minute (175 ist normal), Windows dagegen
    eine Stufe von -10 bis +10. Diese Umrechnung bringt beide zusammen.
    """
    if not rate:
        return 0
    return max(-10, min(10, round((int(rate) - 175) / 15)))


def _windows_sprechen(text: str, rate: int | None = None, ziel: Path | None = None) -> None:
    """
    Lässt Windows den Text sprechen oder in eine WAV-Datei schreiben.

    Der Text wird über eine Datei übergeben, nicht in den Befehl
    hineingeschrieben – sonst könnten Anführungszeichen oder Umlaute im
    Transkript den Aufruf zerlegen.
    """
    powershell = _powershell()
    if not powershell:
        raise TtsError("Diese Sprachausgabe gibt es nur unter Windows.")

    with tempfile.TemporaryDirectory(prefix="voice2text_tts_") as ordner:
        textdatei = Path(ordner) / "text.txt"
        textdatei.write_text(text, encoding="utf-8")

        ausgabe = (f'$s.SetOutputToWaveFile("{ziel}"); ' if ziel else "")
        skript = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {_tempo_umrechnen(rate)}; "
            + ausgabe +
            f'$t = Get-Content -Raw -Encoding UTF8 "{textdatei}"; '
            "$s.Speak($t); $s.Dispose()"
        )

        ergebnis = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", skript],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    if ergebnis.returncode != 0:
        meldung = (ergebnis.stderr or "").strip().splitlines()
        raise TtsError("Windows konnte den Text nicht vorlesen: "
                       + (meldung[-1] if meldung else "unbekannter Fehler"))


def _windows_stimmen() -> list["Voice"]:
    """Fragt Windows, welche Stimmen installiert sind."""
    powershell = _powershell()
    if not powershell:
        return []
    skript = (
        "Add-Type -AssemblyName System.Speech; "
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
        ".GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
    )
    try:
        ergebnis = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", skript],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return []
    if ergebnis.returncode != 0:
        return []
    return [Voice(id=f"windows:{name.strip()}", name=name.strip())
            for name in (ergebnis.stdout or "").splitlines() if name.strip()]


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
    if windows_sprachausgabe_da():
        engines.append("Windows-Sprachausgabe")
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
        hinweis = ""
        if "pywintypes" in str(exc) or "win32" in str(exc):
            # Klassiker unter Windows: pywin32 ist da, aber der
            # Nachbereitungsschritt der Installation lief nie.
            hinweis = (
                "\n\nUnter Windows liegt das fast immer an pywin32. Reparieren mit:\n"
                "    pip install --upgrade --force-reinstall pywin32\n\n"
                "Nötig ist das aber nicht – die App nimmt stattdessen die\n"
                "Sprachausgabe, die Windows selbst mitbringt."
            )
        raise TtsError(f"Die Sprachausgabe konnte nicht gestartet werden: {exc}{hinweis}") from exc

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
        return _windows_stimmen()
    try:
        stimmen = [
            Voice(id=str(v.id), name=str(getattr(v, "name", v.id)))
            for v in engine.getProperty("voices")
        ]
        return stimmen or _windows_stimmen()
    except Exception:
        return _windows_stimmen()
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

    if str(voice or "").startswith("windows:"):
        _windows_sprechen(text, rate)
        return

    try:
        engine = _new_engine(voice, rate)
    except TtsError:
        # pyttsx3 will nicht – unter Windows geht es auch ohne.
        if windows_sprachausgabe_da():
            _windows_sprechen(text, rate)
            return
        raise

    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        if windows_sprachausgabe_da():
            _windows_sprechen(text, rate)
            return
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

    if str(voice or "").startswith("windows:"):
        _windows_sprechen(text, rate, ziel=path)
        return path

    try:
        engine = _new_engine(voice, rate)
    except TtsError:
        if windows_sprachausgabe_da():
            _windows_sprechen(text, rate, ziel=path)
            return path
        raise

    try:
        # Der espeak-Treiber schreibt ungefragt "Audio saved to …" auf die
        # Konsole – das gehört nicht in unsere Ausgabe.
        with contextlib.redirect_stdout(io.StringIO()):
            engine.save_to_file(text, str(path))
            engine.runAndWait()
    except Exception as exc:
        if windows_sprachausgabe_da():
            _windows_sprechen(text, rate, ziel=path)
            return path
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
