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

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .timecode import format_hms, format_timestamp

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
        from .sprecher import nach_sprecher_buendeln

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

    from .media import split_audio

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
