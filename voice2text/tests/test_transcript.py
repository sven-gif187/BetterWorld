"""Tests für die Ergebnis-Aufbereitung: Fließtext, SRT, VTT, Markdown, Export."""

import tempfile
import unittest
from pathlib import Path

from voice2text.transcribe import Segment, Transcript


def beispiel() -> Transcript:
    return Transcript(
        segments=[
            Segment(0.0, 2.5, " Guten Morgen zusammen. "),
            Segment(2.5, 6.0, "Heute geht es um Paper Trading."),
            Segment(6.0, 6.4, "   "),          # Leerlauf – darf nirgends auftauchen
        ],
        language="de",
        backend="faster-whisper",
        model="small",
        title="Testvideo",
        origin="test.mp4",
        duration=6.4,
    )


class TextAusgabe(unittest.TestCase):
    def test_fliesstext_ohne_leerstellen(self):
        self.assertEqual(beispiel().text, "Guten Morgen zusammen. Heute geht es um Paper Trading.")

    def test_text_mit_zeitstempeln(self):
        zeilen = beispiel().to_text(with_timestamps=True).splitlines()
        self.assertEqual(len(zeilen), 2)
        self.assertTrue(zeilen[0].startswith("[0:00 – 0:02]"))

    def test_leerer_transkript_bleibt_leer(self):
        self.assertEqual(Transcript().text, "")
        self.assertEqual(Transcript().to_srt(), "")


class UntertitelFormate(unittest.TestCase):
    def test_srt_nummeriert_und_zeitet_korrekt(self):
        srt = beispiel().to_srt()
        self.assertIn("1\n00:00:00,000 --> 00:00:02,500\nGuten Morgen zusammen.", srt)
        self.assertIn("2\n00:00:02,500 --> 00:00:06,000\n", srt)
        self.assertNotIn("3\n", srt)          # leeres Segment wird übersprungen

    def test_vtt_beginnt_mit_kopfzeile(self):
        vtt = beispiel().to_vtt()
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:02.500", vtt)

    def test_markdown_enthaelt_kopfdaten(self):
        markdown = beispiel().to_markdown()
        self.assertIn("# Testvideo", markdown)
        self.assertIn("**Quelle:** test.mp4", markdown)
        self.assertIn("faster-whisper", markdown)


class Verschiebung(unittest.TestCase):
    def test_offset_verschiebt_alle_zeiten(self):
        verschoben = Segment(10.0, 12.0, "Text").shifted(750.0)
        self.assertEqual((verschoben.start, verschoben.end), (760.0, 762.0))

    def test_ausschnitt_behaelt_originalzeiten(self):
        """Ab Minute 12:30 transkribiert → Zeitstempel passen trotzdem zum Original."""
        transcript = Transcript(
            segments=[Segment(0.0, 3.0, "Erster Satz").shifted(750.0)],
            offset=750.0,
        )
        self.assertIn("00:12:30,000 --> 00:12:33,000", transcript.to_srt())


class Export(unittest.TestCase):
    def test_endung_bestimmt_das_format(self):
        transcript = beispiel()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertIn("-->", transcript.export(folder / "a.srt").read_text(encoding="utf-8"))
            self.assertTrue(transcript.export(folder / "a.vtt").read_text(encoding="utf-8").startswith("WEBVTT"))
            self.assertIn("# Testvideo", transcript.export(folder / "a.md").read_text(encoding="utf-8"))
            txt = transcript.export(folder / "a.txt", with_timestamps=False).read_text(encoding="utf-8")
            self.assertEqual(txt, transcript.text)

    def test_ordner_wird_angelegt(self):
        with tempfile.TemporaryDirectory() as tmp:
            ziel = Path(tmp) / "neu" / "tiefer" / "t.txt"
            self.assertTrue(beispiel().export(ziel).exists())


if __name__ == "__main__":
    unittest.main()
