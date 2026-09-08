"""Tests für den Ablauf – ohne ffmpeg, ohne Netz: die Bausteine werden ersetzt."""

import unittest
from pathlib import Path
from unittest import mock

from voice2text import media, pipeline
from voice2text.pipeline import Job, run_job, safe_filename
from voice2text.transcribe import Segment, Transcript


class Dateinamen(unittest.TestCase):
    def test_sonderzeichen_verschwinden(self):
        self.assertEqual(safe_filename("Mein Video: Teil 1/2 ⚡"), "Mein_Video_Teil_12")

    def test_leerer_name_bekommt_ersatz(self):
        self.assertEqual(safe_filename("///"), "transkript")

    def test_laenge_wird_begrenzt(self):
        self.assertLessEqual(len(safe_filename("a" * 200)), 80)


class Quellenerkennung(unittest.TestCase):
    def test_links_werden_erkannt(self):
        self.assertTrue(media.looks_like_url("https://youtu.be/abc"))
        self.assertTrue(media.looks_like_url("  http://example.com/v.mp4 "))

    def test_dateipfade_sind_keine_links(self):
        for pfad in ("C:/Videos/test.mp4", "/home/sven/test.mp4", "test.mp4", "~/video.mkv"):
            with self.subTest(pfad=pfad):
                self.assertFalse(media.looks_like_url(pfad))


class Ablauf(unittest.TestCase):
    """run_job verdrahtet Ausschnitt, Tonspur und Erkennung – genau das wird geprüft."""

    def setUp(self):
        self.prepared = media.MediaSource(
            audio_path=Path("/tmp/audio_16k.wav"),
            title="Testvideo",
            origin="test.mp4",
            offset=0.0,
            duration=60.0,
        )

    def _run(self, job: Job, meldungen: list | None = None):
        gesammelt = meldungen if meldungen is not None else []
        with mock.patch.object(media, "prepare_source", return_value=self.prepared) as vorbereiten, \
             mock.patch.object(pipeline, "transcribe") as erkennen:
            erkennen.return_value = Transcript(segments=[Segment(0, 1, "Text")])
            ergebnis = run_job(job, progress=lambda anteil, text: gesammelt.append(text))
        return ergebnis, vorbereiten, erkennen

    def test_ohne_ausschnitt(self):
        _, vorbereiten, _ = self._run(Job(source="test.mp4"))
        self.assertEqual(vorbereiten.call_args.kwargs["start"], None)
        self.assertEqual(vorbereiten.call_args.kwargs["duration"], None)

    def test_start_und_ende_werden_umgerechnet(self):
        _, vorbereiten, _ = self._run(Job(source="test.mp4", start="12:30", end="14:00"))
        self.assertEqual(vorbereiten.call_args.kwargs["start"], 750.0)
        self.assertEqual(vorbereiten.call_args.kwargs["duration"], 90.0)

    def test_sprungmarke_aus_dem_link_wird_uebernommen(self):
        """Genau der Fall: Link mit Uhrzeit reinwerfen, App findet die Stelle."""
        _, vorbereiten, _ = self._run(Job(source="https://youtu.be/abc?t=90", duration="30"))
        self.assertEqual(vorbereiten.call_args.kwargs["start"], 90.0)
        self.assertEqual(vorbereiten.call_args.kwargs["duration"], 30.0)

    def test_ausdrueckliche_zeit_schlaegt_die_aus_dem_link(self):
        _, vorbereiten, _ = self._run(Job(source="https://youtu.be/abc?t=90", start="5:00"))
        self.assertEqual(vorbereiten.call_args.kwargs["start"], 300.0)

    def test_einstellungen_kommen_bei_der_erkennung_an(self):
        job = Job(source="test.mp4", model="medium", language="de", backend="faster-whisper")
        _, _, erkennen = self._run(job)
        self.assertEqual(erkennen.call_args.kwargs["model"], "medium")
        self.assertEqual(erkennen.call_args.kwargs["language"], "de")
        self.assertEqual(erkennen.call_args.kwargs["backend"], "faster-whisper")

    def test_offset_wird_weitergereicht(self):
        self.prepared.offset = 750.0
        _, _, erkennen = self._run(Job(source="test.mp4", start="12:30"))
        self.assertEqual(erkennen.call_args.kwargs["offset"], 750.0)

    def test_meldungen_erreichen_die_oberflaeche(self):
        meldungen: list = []
        self._run(Job(source="test.mp4", start="1:00", duration="30"), meldungen)
        text = " ".join(m for m in meldungen if m)
        self.assertIn("Ausschnitt", text)
        self.assertIn("Fertig", text)

    def test_leere_quelle_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            run_job(Job(source="   "))

    def test_temporaere_dateien_werden_aufgeraeumt(self):
        aufgeraeumt = []
        self.prepared.cleanup = lambda: aufgeraeumt.append(True)
        with mock.patch.object(media, "prepare_source", return_value=self.prepared), \
             mock.patch.object(pipeline, "transcribe", side_effect=RuntimeError("kaputt")):
            with self.assertRaises(RuntimeError):
                run_job(Job(source="test.mp4"))
        self.assertTrue(aufgeraeumt, "Der Temp-Ordner muss auch nach einem Fehler verschwinden.")


if __name__ == "__main__":
    unittest.main()
