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

from __future__ import annotations

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
