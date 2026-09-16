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

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Callable

from .media import looks_like_url
from .pipeline import Job, run_job
from .transcribe import Transcript

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
