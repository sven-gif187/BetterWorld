"""
Tests für die Sprecher-Erkennung.

Die eigentliche Erkennung braucht pyannote.audio und ein Hugging-Face-Konto –
das lässt sich hier nicht prüfen. Die Zuordnung von Stimmen zu Sätzen dagegen
schon, und genau dort steckt die Logik, die schiefgehen kann.
"""

import unittest

from voice2text.sprecher import (
    Sprecherabschnitt,
    SprecherError,
    diarisieren,
    nach_sprecher_buendeln,
    namen_vergeben,
    sprecher_status,
    verfuegbar,
    zuordnen,
)
from voice2text.transcribe import Segment, Transcript


class Verfuegbarkeit(unittest.TestCase):
    def test_status_ist_immer_lesbar(self):
        text = sprecher_status()
        self.assertTrue(text.startswith(("✅", "⚠️")))

    def test_ohne_einrichtung_kommt_eine_anleitung(self):
        if verfuegbar():
            self.skipTest("pyannote ist eingerichtet – Fehlerpfad nicht prüfbar")
        with self.assertRaises(SprecherError) as fall:
            diarisieren("egal.wav")
        self.assertIn("pip install", str(fall.exception))


class Namensgebung(unittest.TestCase):
    def test_nummerierung_nach_erstem_auftreten(self):
        """Wer zuerst spricht, ist Sprecher 1 – auch wenn das Modell anders zählt."""
        abschnitte = [
            Sprecherabschnitt(0, 5, "SPEAKER_07"),
            Sprecherabschnitt(5, 10, "SPEAKER_02"),
            Sprecherabschnitt(10, 15, "SPEAKER_07"),
        ]
        benannt = namen_vergeben(abschnitte)
        self.assertEqual([a.sprecher for a in benannt],
                         ["Sprecher 1", "Sprecher 2", "Sprecher 1"])

    def test_unsortierte_eingabe_wird_sortiert(self):
        abschnitte = [
            Sprecherabschnitt(10, 15, "B"),
            Sprecherabschnitt(0, 5, "A"),
        ]
        benannt = namen_vergeben(abschnitte)
        self.assertEqual([a.start for a in benannt], [0, 10])
        self.assertEqual(benannt[0].sprecher, "Sprecher 1")

    def test_leere_liste(self):
        self.assertEqual(namen_vergeben([]), [])


class Zuordnung(unittest.TestCase):
    def test_saubere_zuordnung(self):
        segmente = [Segment(0, 3, "Frage"), Segment(3, 6, "Antwort")]
        abschnitte = [Sprecherabschnitt(0, 3, "Sprecher 1"), Sprecherabschnitt(3, 6, "Sprecher 2")]
        zuordnen(segmente, abschnitte)
        self.assertEqual([s.speaker for s in segmente], ["Sprecher 1", "Sprecher 2"])

    def test_die_laengste_ueberlappung_gewinnt(self):
        """
        Whisper schneidet nach Sätzen, die Stimmerkennung nach Sprechern –
        die Grenzen liegen fast nie übereinander.
        """
        segment = Segment(0, 10, "Ein langer Satz")
        abschnitte = [
            Sprecherabschnitt(0, 3, "Sprecher 1"),     # 3 Sekunden
            Sprecherabschnitt(3, 10, "Sprecher 2"),    # 7 Sekunden → gewinnt
        ]
        zuordnen([segment], abschnitte)
        self.assertEqual(segment.speaker, "Sprecher 2")

    def test_knappe_mehrheit(self):
        segment = Segment(0, 10, "Text")
        abschnitte = [
            Sprecherabschnitt(0, 5.1, "Sprecher 1"),
            Sprecherabschnitt(5.1, 10, "Sprecher 2"),
        ]
        zuordnen([segment], abschnitte)
        self.assertEqual(segment.speaker, "Sprecher 1")

    def test_ohne_ueberlappung_bleibt_der_sprecher_leer(self):
        """Musik, Stille, Hintergrundrauschen – lieber nichts als geraten."""
        segment = Segment(20, 25, "Text ohne Stimme davor")
        zuordnen([segment], [Sprecherabschnitt(0, 10, "Sprecher 1")])
        self.assertIsNone(segment.speaker)

    def test_ohne_abschnitte_passiert_nichts(self):
        segmente = [Segment(0, 3, "Text")]
        zuordnen(segmente, [])
        self.assertIsNone(segmente[0].speaker)

    def test_luecke_zwischen_den_stimmen(self):
        segmente = [Segment(0, 2, "A"), Segment(4, 6, "B"), Segment(8, 10, "C")]
        abschnitte = [Sprecherabschnitt(0, 3, "Sprecher 1"), Sprecherabschnitt(7, 11, "Sprecher 2")]
        zuordnen(segmente, abschnitte)
        self.assertEqual([s.speaker for s in segmente], ["Sprecher 1", None, "Sprecher 2"])

    def test_zuordnung_ueberschreibt_alte_werte(self):
        segment = Segment(0, 5, "Text", speaker="Sprecher 9")
        zuordnen([segment], [Sprecherabschnitt(0, 5, "Sprecher 1")])
        self.assertEqual(segment.speaker, "Sprecher 1")


class Buendelung(unittest.TestCase):
    def test_gleiche_stimme_wird_zusammengefasst(self):
        segmente = [
            Segment(0, 2, "Ganz gut.", speaker="Sprecher 2"),
            Segment(2, 5, "Wir waren wandern.", speaker="Sprecher 2"),
        ]
        gebuendelt = nach_sprecher_buendeln(segmente)
        self.assertEqual(len(gebuendelt), 1)
        self.assertEqual(gebuendelt[0][3], "Ganz gut. Wir waren wandern.")
        self.assertEqual(gebuendelt[0][2], 5)

    def test_sprecherwechsel_trennt(self):
        segmente = [
            Segment(0, 2, "Frage?", speaker="Sprecher 1"),
            Segment(2, 4, "Antwort.", speaker="Sprecher 2"),
        ]
        self.assertEqual(len(nach_sprecher_buendeln(segmente)), 2)

    def test_lange_pause_trennt_auch_bei_gleicher_stimme(self):
        segmente = [
            Segment(0, 2, "Erster Beitrag.", speaker="Sprecher 1"),
            Segment(30, 32, "Viel später nochmal.", speaker="Sprecher 1"),
        ]
        self.assertEqual(len(nach_sprecher_buendeln(segmente, luecke=1.5)), 2)

    def test_leere_abschnitte_verschwinden(self):
        segmente = [
            Segment(0, 2, "Text", speaker="Sprecher 1"),
            Segment(2, 3, "   ", speaker="Sprecher 1"),
        ]
        gebuendelt = nach_sprecher_buendeln(segmente)
        self.assertEqual(gebuendelt[0][3], "Text")

    def test_ohne_sprecher_funktioniert_es_trotzdem(self):
        segmente = [Segment(0, 2, "Eins"), Segment(2, 4, "Zwei")]
        gebuendelt = nach_sprecher_buendeln(segmente)
        self.assertEqual(len(gebuendelt), 1)
        self.assertIsNone(gebuendelt[0][0])


class AusgabeMitSprechern(unittest.TestCase):
    def gespraech(self) -> Transcript:
        segmente = [
            Segment(0, 3, "Und wie war dein Wochenende?", speaker="Sprecher 1"),
            Segment(3, 4, "Ganz gut.", speaker="Sprecher 2"),
            Segment(4, 7, "Wir waren wandern.", speaker="Sprecher 2"),
        ]
        return Transcript(segments=segmente, language="de", backend="faster-whisper",
                          model="small", title="Gespräch", duration=7)

    def test_erkennt_dass_sprecher_vorhanden_sind(self):
        self.assertTrue(self.gespraech().hat_sprecher)
        self.assertFalse(Transcript(segments=[Segment(0, 1, "Text")]).hat_sprecher)

    def test_dialogform(self):
        zeilen = self.gespraech().to_dialog().split("\n\n")
        self.assertEqual(len(zeilen), 2)
        self.assertTrue(zeilen[0].startswith("Sprecher 1: "))
        self.assertEqual(zeilen[1], "Sprecher 2: Ganz gut. Wir waren wandern.")

    def test_zeitstempel_zeigen_den_sprecher(self):
        self.assertIn("] Sprecher 1: Und wie", self.gespraech().to_text(with_timestamps=True))

    def test_untertitel_bekommen_den_namen_davor(self):
        self.assertIn("Sprecher 1: Und wie war dein Wochenende?", self.gespraech().to_srt())
        self.assertIn("Sprecher 2: Ganz gut.", self.gespraech().to_vtt())

    def test_markdown_nennt_die_anzahl(self):
        self.assertIn("**Sprecher:** 2", self.gespraech().to_markdown())

    def test_ohne_sprecher_bleibt_alles_wie_vorher(self):
        schlicht = Transcript(segments=[Segment(0, 1, "Nur Text")])
        self.assertEqual(schlicht.to_text(), "Nur Text")
        self.assertNotIn("Sprecher", schlicht.to_srt())

    def test_verschieben_behaelt_den_sprecher(self):
        verschoben = Segment(0, 2, "Text", speaker="Sprecher 1").shifted(750)
        self.assertEqual(verschoben.speaker, "Sprecher 1")
        self.assertEqual(verschoben.start, 750)


if __name__ == "__main__":
    unittest.main()
