"""
Tests für die Kommandozeile.

Anlass: Die Anleitung nannte "python -m voice2text --hilfe", den Schalter
gab es aber gar nicht – argparse kennt von Haus aus nur -h/--help. Beim
Prüfen war das durchgerutscht, weil die Ausgabe durch "head" lief und die
Fehlermeldung wie die Hilfe aussah. Deshalb steht hier ab jetzt ein Test.

Es wird nur der Weg bis zum Aufruf geprüft, nie eine echte Transkription –
die braucht ein Modell und dauert Minuten.
"""

import contextlib
import io
import unittest

from voice2text.cli import build_parser, main
from voice2text.transcribe import MODELS
from voice2text.zusammenfassung import ARTEN


def ruf_auf(*argumente) -> tuple[int, str, str]:
    """Ruft die Kommandozeile auf und fängt alles ab. Rückgabe: (code, out, err)."""
    aus, fehler = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
        try:
            code = main(list(argumente))
        except SystemExit as ende:             # argparse beendet sich selbst
            code = ende.code if ende.code is not None else 0
    return code, aus.getvalue(), fehler.getvalue()


class Hilfe(unittest.TestCase):
    def test_alle_drei_schreibweisen(self):
        """--hilfe, --help und -h müssen alle sauber mit 0 enden."""
        for schalter in ("--hilfe", "--help", "-h"):
            with self.subTest(schalter=schalter):
                code, ausgabe, _ = ruf_auf(schalter)
                self.assertEqual(code, 0, f"{schalter} endete mit {code}")
                self.assertIn("voice2text", ausgabe)

    def test_hilfe_nennt_die_wichtigen_schalter(self):
        _, ausgabe, _ = ruf_auf("--hilfe")
        for schalter in ("--start", "--dauer", "--ordner", "--sprecher", "--zusammenfassung"):
            with self.subTest(schalter=schalter):
                self.assertIn(schalter, ausgabe)

    def test_ohne_argumente_gibt_es_die_hilfe(self):
        code, ausgabe, _ = ruf_auf()
        self.assertEqual(code, 1)
        self.assertIn("usage", ausgabe.lower())


class Status(unittest.TestCase):
    def test_status_laeuft_durch(self):
        code, ausgabe, _ = ruf_auf("--status")
        self.assertEqual(code, 0)
        self.assertIn("Systemstatus", ausgabe)

    def test_status_zeigt_keine_schluesselwerte(self):
        """Auf dem Bildschirm stehen Namen, niemals Werte."""
        _, ausgabe, _ = ruf_auf("--status")
        self.assertIn("Schlüssel", ausgabe)
        self.assertNotIn("sk-", ausgabe)
        self.assertNotIn("hf_", ausgabe)


class Schalter(unittest.TestCase):
    def test_parser_kennt_die_dokumentierten_schalter(self):
        parser = build_parser()
        args = parser.parse_args([
            "video.mp4", "--start", "12:30", "--dauer", "90",
            "--modell", "small", "--sprache", "de", "--backend", "auto",
            "--sprecher", "--sprecherzahl", "2", "--zusammenfassung", "protokoll",
            "--ordner", "/tmp/aus", "--zeitstempel", "--still",
        ])
        self.assertEqual(args.quelle, ["video.mp4"])
        self.assertEqual(args.start, "12:30")
        self.assertTrue(args.sprecher)
        self.assertEqual(args.sprecherzahl, 2)
        self.assertEqual(args.zusammenfassung, "protokoll")

    def test_zusammenfassung_ohne_angabe_nimmt_stichpunkte(self):
        args = build_parser().parse_args(["video.mp4", "-z"])
        self.assertEqual(args.zusammenfassung, "stichpunkte")

    def test_mehrere_quellen_erlaubt(self):
        args = build_parser().parse_args(["a.mp4", "b.mp4", "c.mp4"])
        self.assertEqual(len(args.quelle), 3)

    def test_alle_modelle_und_arten_sind_waehlbar(self):
        for modell in MODELS:
            build_parser().parse_args(["v.mp4", "--modell", modell])
        for art in ARTEN:
            build_parser().parse_args(["v.mp4", "--zusammenfassung", art])

    def test_unbekanntes_modell_wird_abgelehnt(self):
        code, _, fehler = ruf_auf("v.mp4", "--modell", "riesig")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", fehler)


class Widersprueche(unittest.TestCase):
    def test_mehrere_quellen_und_eine_zieldatei(self):
        """--ausgabe schreibt in genau eine Datei, das geht bei zweien nicht."""
        code, _, fehler = ruf_auf("a.mp4", "b.mp4", "--ausgabe", "x.srt")
        self.assertEqual(code, 1)
        self.assertIn("--ordner", fehler)

    def test_fehlende_datei_meldet_sich_verstaendlich(self):
        code, _, fehler = ruf_auf("gibt_es_nicht.mp4", "--still")
        self.assertEqual(code, 1)
        self.assertIn("nicht gefunden", fehler)


if __name__ == "__main__":
    unittest.main()
