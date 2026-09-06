"""Tests für die Warteschlange – ohne echte Transkription, dafür mit echten Threads."""

import threading
import time
import unittest

from voice2text.pipeline import Job
from voice2text.transcribe import Segment, Transcript
from voice2text.warteschlange import (
    ABGEBROCHEN,
    FEHLER,
    FERTIG,
    WARTET,
    Warteschlange,
)


def fertiges_transkript(titel="Testvideo") -> Transcript:
    return Transcript(segments=[Segment(0, 1, "Text")], title=titel)


def warte_bis(bedingung, sekunden=5.0) -> bool:
    """Wartet, bis die Bedingung zutrifft – statt blind zu schlafen."""
    ende = time.time() + sekunden
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


class Bestuecken(unittest.TestCase):
    def test_leere_schlange(self):
        schlange = Warteschlange(ausfuehren=lambda job, progress=None: fertiges_transkript())
        self.assertEqual(schlange.auftraege, [])
        self.assertEqual(schlange.offen, 0)
        self.assertFalse(schlange.laeuft)
        self.assertIn("leer", schlange.zusammenfassung())

    def test_hinzufuegen_und_zaehlen(self):
        schlange = Warteschlange(ausfuehren=lambda job, progress=None: fertiges_transkript())
        schlange.hinzufuegen(Job(source="a.mp4"))
        schlange.hinzufuegen(Job(source="b.mp4"))
        self.assertEqual(len(schlange.auftraege), 2)
        self.assertEqual(schlange.offen, 2)

    def test_nummern_sind_eindeutig(self):
        schlange = Warteschlange(ausfuehren=lambda job, progress=None: fertiges_transkript())
        nummern = [schlange.hinzufuegen(Job(source=f"{i}.mp4")).nummer for i in range(3)]
        self.assertEqual(len(set(nummern)), 3)

    def test_wartender_eintrag_laesst_sich_entfernen(self):
        schlange = Warteschlange(ausfuehren=lambda job, progress=None: fertiges_transkript())
        auftrag = schlange.hinzufuegen(Job(source="a.mp4"))
        self.assertTrue(schlange.entfernen(auftrag))
        self.assertEqual(schlange.auftraege, [])
        self.assertFalse(schlange.entfernen(auftrag), "Zweimal entfernen darf nicht gehen.")


class Namen(unittest.TestCase):
    def test_dateiname_statt_ganzem_pfad(self):
        schlange = Warteschlange()
        self.assertEqual(schlange.hinzufuegen(Job(source="C:/Videos/urlaub.mp4")).name, "urlaub.mp4")
        self.assertEqual(schlange.hinzufuegen(Job(source="/home/sven/rede.mkv")).name, "rede.mkv")

    def test_link_bleibt_erkennbar(self):
        """Ein Link darf nicht wie ein Pfad am letzten / abgeschnitten werden."""
        schlange = Warteschlange()
        auftrag = schlange.hinzufuegen(Job(source="https://youtu.be/abc"))
        self.assertIn("youtu.be", auftrag.name)

    def test_sehr_langer_link_wird_gekuerzt(self):
        schlange = Warteschlange()
        auftrag = schlange.hinzufuegen(Job(source="https://example.com/" + "x" * 200))
        self.assertLessEqual(len(auftrag.name), 60)
        self.assertTrue(auftrag.name.startswith("example.com/"))

    def test_videotitel_gewinnt_sobald_bekannt(self):
        schlange = Warteschlange()
        auftrag = schlange.hinzufuegen(Job(source="/pfad/x.mp4"))
        auftrag.transcript = fertiges_transkript("Der echte Titel")
        self.assertEqual(auftrag.name, "Der echte Titel")


class Abarbeiten(unittest.TestCase):
    def test_alle_werden_der_reihe_nach_erledigt(self):
        reihenfolge = []

        def ausfuehren(job, progress=None):
            reihenfolge.append(job.source)
            return fertiges_transkript()

        schlange = Warteschlange(ausfuehren=ausfuehren)
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            schlange.hinzufuegen(Job(source=name))

        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))
        self.assertEqual(reihenfolge, ["a.mp4", "b.mp4", "c.mp4"])
        self.assertTrue(all(a.status == FERTIG for a in schlange.auftraege))
        self.assertEqual(schlange.offen, 0)

    def test_immer_nur_einer_gleichzeitig(self):
        gleichzeitig = []
        aktiv = threading.Semaphore(1)

        def ausfuehren(job, progress=None):
            gleichzeitig.append(aktiv.acquire(blocking=False))
            time.sleep(0.02)
            aktiv.release()
            return fertiges_transkript()

        schlange = Warteschlange(ausfuehren=ausfuehren)
        for i in range(4):
            schlange.hinzufuegen(Job(source=f"{i}.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))
        self.assertTrue(all(gleichzeitig), "Es liefen zwei Aufträge parallel.")

    def test_ein_fehler_stoppt_die_anderen_nicht(self):
        def ausfuehren(job, progress=None):
            if job.source == "kaputt.mp4":
                raise RuntimeError("Datei ist Müll")
            return fertiges_transkript()

        schlange = Warteschlange(ausfuehren=ausfuehren)
        schlange.hinzufuegen(Job(source="gut1.mp4"))
        schlange.hinzufuegen(Job(source="kaputt.mp4"))
        schlange.hinzufuegen(Job(source="gut2.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))

        status = [a.status for a in schlange.auftraege]
        self.assertEqual(status, [FERTIG, FEHLER, FERTIG])
        self.assertIn("Müll", schlange.auftraege[1].fehler)

    def test_zweimal_starten_startet_nicht_doppelt(self):
        schlange = Warteschlange(ausfuehren=lambda job, progress=None: (time.sleep(0.05), fertiges_transkript())[1])
        schlange.hinzufuegen(Job(source="a.mp4"))
        self.assertTrue(schlange.starten())
        self.assertFalse(schlange.starten(), "Ein zweiter Start darf nicht durchgehen.")
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))

    def test_start_ohne_offene_eintraege(self):
        self.assertFalse(Warteschlange().starten())

    def test_abbruch_laesst_den_rest_liegen(self):
        gestartet = threading.Event()

        def ausfuehren(job, progress=None):
            gestartet.set()
            time.sleep(0.05)
            return fertiges_transkript()

        schlange = Warteschlange(ausfuehren=ausfuehren)
        for i in range(5):
            schlange.hinzufuegen(Job(source=f"{i}.mp4"))
        schlange.starten()
        self.assertTrue(gestartet.wait(2))
        schlange.abbrechen()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))

        status = [a.status for a in schlange.auftraege]
        self.assertEqual(status[0], FERTIG, "Der laufende Eintrag wird noch fertig gerechnet.")
        self.assertIn(ABGEBROCHEN, status)
        self.assertNotIn(WARTET, status)


class Ereignisse(unittest.TestCase):
    def test_zuhoerer_bekommt_alles_mit(self):
        ereignisse = []
        schlange = Warteschlange(
            ereignis=lambda art, wert: ereignisse.append(art),
            ausfuehren=lambda job, progress=None: fertiges_transkript(),
        )
        schlange.hinzufuegen(Job(source="a.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))
        for erwartet in ("aenderung", "log", "fertig", "leer"):
            self.assertIn(erwartet, ereignisse)

    def test_fortschritt_wird_durchgereicht(self):
        anteile = []

        def ausfuehren(job, progress=None):
            progress(0.5, "halb")
            progress(1.0, "ganz")
            return fertiges_transkript()

        schlange = Warteschlange(
            ereignis=lambda art, wert: anteile.append(wert) if art == "fortschritt" else None,
            ausfuehren=ausfuehren,
        )
        schlange.hinzufuegen(Job(source="a.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))
        self.assertIn(0.5, anteile)
        self.assertIn(1.0, anteile)

    def test_kaputter_zuhoerer_haelt_die_schlange_nicht_auf(self):
        def boeser_zuhoerer(art, wert):
            raise RuntimeError("Anzeige abgestürzt")

        schlange = Warteschlange(
            ereignis=boeser_zuhoerer,
            ausfuehren=lambda job, progress=None: fertiges_transkript(),
        )
        schlange.hinzufuegen(Job(source="a.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))
        self.assertEqual(schlange.auftraege[0].status, FERTIG)


class Aufraeumen(unittest.TestCase):
    def test_erledigte_entfernen(self):
        schlange = Warteschlange(ausfuehren=lambda job, progress=None: fertiges_transkript())
        schlange.hinzufuegen(Job(source="a.mp4"))
        schlange.hinzufuegen(Job(source="b.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))

        schlange.hinzufuegen(Job(source="c.mp4"))
        self.assertEqual(schlange.erledigte_entfernen(), 2)
        self.assertEqual([a.job.source for a in schlange.auftraege], ["c.mp4"])

    def test_zusammenfassung_zaehlt_richtig(self):
        def ausfuehren(job, progress=None):
            if job.source == "kaputt.mp4":
                raise RuntimeError("nein")
            return fertiges_transkript()

        schlange = Warteschlange(ausfuehren=ausfuehren)
        schlange.hinzufuegen(Job(source="a.mp4"))
        schlange.hinzufuegen(Job(source="kaputt.mp4"))
        schlange.starten()
        self.assertTrue(warte_bis(lambda: not schlange.laeuft))

        text = schlange.zusammenfassung()
        self.assertIn("2 Einträge", text)
        self.assertIn("1 fertig", text)
        self.assertIn("1 mit Fehler", text)


if __name__ == "__main__":
    unittest.main()
