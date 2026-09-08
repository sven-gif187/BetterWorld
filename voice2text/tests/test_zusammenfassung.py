"""
Tests für die Zusammenfassung.

Echte Anfragen an ein Sprachmodell kosten Geld und brauchen Netz – beides
gehört nicht in eine Testsuite. Geprüft wird deshalb alles, was davor und
danach passiert: Häppchen bilden, Anweisungen bauen, Dienst wählen,
Teilergebnisse zusammenführen.
"""

import unittest
from unittest import mock

from voice2text import zusammenfassung as zf
from voice2text.zusammenfassung import (
    ARTEN,
    MAX_ZEICHEN,
    ZusammenfassungError,
    anweisung_bauen,
    haeppchen,
    verfuegbare_dienste,
    zusammenfassen,
    zusammenfassung_status,
)


class Verfuegbarkeit(unittest.TestCase):
    def test_ohne_schluessel_kein_dienst(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(verfuegbare_dienste(), [])

    def test_status_ist_immer_lesbar(self):
        self.assertTrue(zusammenfassung_status().startswith(("✅", "⚠️")))

    def test_ohne_dienst_kommt_eine_anleitung(self):
        with mock.patch.object(zf, "verfuegbare_dienste", return_value=[]):
            with self.assertRaises(ZusammenfassungError) as fall:
                zusammenfassen("Ein Text.")
        meldung = str(fall.exception)
        self.assertIn("pip install anthropic", meldung)
        self.assertIn("kostet", meldung)

    def test_unbekannter_dienst_wird_abgelehnt(self):
        with mock.patch.object(zf, "verfuegbare_dienste", return_value=["anthropic"]):
            with self.assertRaises(ZusammenfassungError):
                zusammenfassen("Text", dienst="hellseher")


class Haeppchen(unittest.TestCase):
    def test_kurzer_text_bleibt_am_stueck(self):
        self.assertEqual(haeppchen("Ein kurzer Satz."), ["Ein kurzer Satz."])

    def test_leerer_text(self):
        self.assertEqual(haeppchen(""), [])
        self.assertEqual(haeppchen("   "), [])

    def test_wird_an_satzenden_getrennt(self):
        text = "Erster Satz. " * 100
        teile = haeppchen(text, max_zeichen=200)
        self.assertGreater(len(teile), 1)
        for teil in teile:
            self.assertTrue(teil.endswith(".") or teil.endswith("Satz"),
                            f"mitten im Satz getrennt: …{teil[-20:]!r}")

    def test_grenze_wird_eingehalten(self):
        teile = haeppchen("Ein Satz mit ein paar Wörtern. " * 500, max_zeichen=300)
        for teil in teile:
            self.assertLessEqual(len(teil), 300)

    def test_bandwurmsatz_wird_notfalls_hart_geschnitten(self):
        """Transkripte ohne Satzzeichen sind keine Seltenheit."""
        text = "wort " * 400                      # 2000 Zeichen, kein einziger Punkt
        teile = haeppchen(text, max_zeichen=300)
        self.assertGreater(len(teile), 1)
        for teil in teile:
            self.assertLessEqual(len(teil), 300)

    def test_nichts_geht_verloren(self):
        text = "Satz eins. Satz zwei. Satz drei. Satz vier."
        zusammen = " ".join(haeppchen(text, max_zeichen=20))
        for wort in ("eins", "zwei", "drei", "vier"):
            self.assertIn(wort, zusammen)

    def test_standardgrenze_ist_gesetzt(self):
        self.assertEqual(len(haeppchen("x" * (MAX_ZEICHEN - 1))), 1)


class Anweisungen(unittest.TestCase):
    def test_jede_art_ergibt_eine_anweisung(self):
        for art in ARTEN:
            with self.subTest(art=art):
                text = anweisung_bauen(art)
                self.assertGreater(len(text), 50)
                self.assertIn("Deutsch", text)

    def test_unbekannte_art_fliegt_auf(self):
        with self.assertRaises(ZusammenfassungError):
            anweisung_bauen("gedicht")

    def test_sprache_wird_uebernommen(self):
        self.assertIn("Englisch", anweisung_bauen("kurz", sprache="Englisch"))

    def test_warnung_vor_erfundenem_inhalt_ist_immer_dabei(self):
        """
        Der wichtigste Satz der ganzen Anweisung: Spracherkennung macht
        Hörfehler, und ein Modell füllt Lücken bereitwillig mit Erfundenem.
        """
        for art in ARTEN:
            with self.subTest(art=art):
                text = anweisung_bauen(art)
                self.assertIn("ergänze nichts", text)
                self.assertIn("statt zu raten", text)


class Ablauf(unittest.TestCase):
    """Der Weg durchs Modul – mit einem erfundenen Dienst statt echter Anfragen."""

    def setUp(self):
        self.anfragen = []

        def erfundener_dienst(anweisung, text, max_tokens):
            self.anfragen.append((anweisung, text, max_tokens))
            return f"Zusammenfassung von {len(text)} Zeichen"

        self.patches = [
            mock.patch.object(zf, "verfuegbare_dienste", return_value=["anthropic"]),
            mock.patch.dict(zf._DIENSTE, {"anthropic": erfundener_dienst}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_kurzer_text_eine_anfrage(self):
        ergebnis = zusammenfassen("Ein kurzer Text.")
        self.assertEqual(len(self.anfragen), 1)
        self.assertIn("Zusammenfassung", ergebnis)

    def test_langer_text_wird_zusammengefuehrt(self):
        """Viele Teile plus ein abschließender Durchgang."""
        text = "Ein Satz mit Inhalt. " * 2000          # weit über der Grenze
        zusammenfassen(text)
        stuecke = len(zf.haeppchen(text))
        self.assertEqual(len(self.anfragen), stuecke + 1,
                         "erwartet: je Teil eine Anfrage plus eine zum Zusammenführen")
        letzte_anweisung = self.anfragen[-1][0]
        self.assertIn("Abschnitte", letzte_anweisung)

    def test_abschnittsnummern_landen_nicht_im_ergebnis(self):
        text = "Ein Satz mit Inhalt. " * 2000
        zusammenfassen(text)
        self.assertIn("ohne die Abschnittsnummern", self.anfragen[-1][0])

    def test_leerer_text_wird_abgelehnt(self):
        with self.assertRaises(ZusammenfassungError):
            zusammenfassen("   ")
        self.assertEqual(self.anfragen, [])

    def test_art_wird_durchgereicht(self):
        zusammenfassen("Kurzer Text.", art="aufgaben")
        self.assertIn("Aufgaben", self.anfragen[0][0])

    def test_meldungen_erreichen_die_oberflaeche(self):
        meldungen = []
        zusammenfassen("Ein Satz. " * 3000, progress=lambda a, m: meldungen.append(m))
        text = " ".join(m for m in meldungen if m)
        self.assertIn("Teilen bearbeitet", text)
        self.assertIn("zusammengeführt", text)


if __name__ == "__main__":
    unittest.main()
