"""
Tests für das Einlesen der .env.

Wichtigster Punkt: Schlüssel dürfen ankommen, aber nirgends auftauchen.
"""

import os
import tempfile
import unittest
from pathlib import Path

from voice2text.konfig import env_datei_finden, env_laden, env_lesen, gesetzte_schluessel


def schreibe(ordner: Path, inhalt: str) -> Path:
    datei = ordner / ".env"
    datei.write_text(inhalt, encoding="utf-8")
    return datei


class Lesen(unittest.TestCase):
    def test_einfache_paare(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "A=1\nB=zwei\n")
            self.assertEqual(env_lesen(datei), {"A": "1", "B": "zwei"})

    def test_kommentare_und_leerzeilen(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "# oben\n\nA=1\n   # eingerückt\nB=2\n")
            self.assertEqual(env_lesen(datei), {"A": "1", "B": "2"})

    def test_export_praefix(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "export TOKEN=abc\n")
            self.assertEqual(env_lesen(datei), {"TOKEN": "abc"})

    def test_anfuehrungszeichen_werden_entfernt(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), 'A="mit leerzeichen"\nB=\'einfach\'\n')
            self.assertEqual(env_lesen(datei), {"A": "mit leerzeichen", "B": "einfach"})

    def test_kommentar_hinter_dem_wert(self):
        """Ein häufiger Tippfehler – der Kommentar darf nicht Teil des Schlüssels werden."""
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "KEY=sk-abc123  # mein Schluessel\n")
            self.assertEqual(env_lesen(datei)["KEY"], "sk-abc123")

    def test_raute_im_wert_bleibt_erhalten(self):
        """Ohne Leerzeichen davor ist die Raute Teil des Werts, nicht ein Kommentar."""
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "PASS=abc#def\n")
            self.assertEqual(env_lesen(datei)["PASS"], "abc#def")

    def test_gleichheitszeichen_im_wert(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "TOKEN=abc=def==\n")
            self.assertEqual(env_lesen(datei)["TOKEN"], "abc=def==")

    def test_kaputte_zeilen_werden_uebersprungen(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "KAPUTT\n=ohne_namen\nGUT=1\nau ch kaputt=2\n")
            self.assertEqual(env_lesen(datei), {"GUT": "1"})

    def test_datei_gibt_es_nicht(self):
        self.assertEqual(env_lesen("/gibt/es/nicht/.env"), {})

    def test_binaermuell_stuerzt_nicht_ab(self):
        with tempfile.TemporaryDirectory() as t:
            datei = Path(t) / ".env"
            datei.write_bytes(b"\xff\xfe\x00\x01binaer")
            self.assertEqual(env_lesen(datei), {})


class Laden(unittest.TestCase):
    def setUp(self):
        self.sicherung = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.sicherung)

    def test_werte_landen_in_der_umgebung(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "VOICE2TEXT_TEST_A=hallo\n")
            env_laden(datei)
            self.assertEqual(os.environ["VOICE2TEXT_TEST_A"], "hallo")

    def test_echte_umgebungsvariablen_haben_vorrang(self):
        """
        Wer einen Schlüssel in der Konsole setzt, will ihn benutzen –
        eine Datei darf ihn nicht heimlich überschreiben.
        """
        os.environ["VOICE2TEXT_TEST_B"] = "aus der konsole"
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "VOICE2TEXT_TEST_B=aus der datei\n")
            env_laden(datei)
            self.assertEqual(os.environ["VOICE2TEXT_TEST_B"], "aus der konsole")

    def test_ueberschreiben_auf_wunsch(self):
        os.environ["VOICE2TEXT_TEST_C"] = "alt"
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "VOICE2TEXT_TEST_C=neu\n")
            env_laden(datei, ueberschreiben=True)
            self.assertEqual(os.environ["VOICE2TEXT_TEST_C"], "neu")

    def test_rueckgabe_enthaelt_nur_namen_keine_werte(self):
        """Der eine Test, der wirklich zählt: Geheimnisse dürfen nicht durchsickern."""
        geheim = "sk-streng-geheim-12345"
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), f"VOICE2TEXT_TEST_D={geheim}\n")
            ergebnis = env_laden(datei)
        self.assertEqual(ergebnis, ["VOICE2TEXT_TEST_D"])
        self.assertNotIn(geheim, str(ergebnis))

    def test_fehlende_datei_ist_kein_fehler(self):
        self.assertEqual(env_laden("/gibt/es/nicht/.env"), [])


class Suche(unittest.TestCase):
    def test_findet_datei_im_startverzeichnis(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "A=1\n")
            self.assertEqual(env_datei_finden(t), datei)

    def test_findet_datei_im_uebergeordneten_ordner(self):
        with tempfile.TemporaryDirectory() as t:
            datei = schreibe(Path(t), "A=1\n")
            tief = Path(t) / "eins" / "zwei"
            tief.mkdir(parents=True)
            self.assertEqual(env_datei_finden(tief), datei)


class SchluesselAnzeige(unittest.TestCase):
    def setUp(self):
        self.sicherung = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.sicherung)

    def test_zeigt_nur_namen(self):
        os.environ["OPENAI_API_KEY"] = "sk-geheim"
        namen = gesetzte_schluessel()
        self.assertIn("OPENAI_API_KEY", namen)
        self.assertNotIn("sk-geheim", " ".join(namen))


if __name__ == "__main__":
    unittest.main()
