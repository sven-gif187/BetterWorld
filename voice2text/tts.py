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
