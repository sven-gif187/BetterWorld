"""
Echte ffmpeg-Tests – kein Mock, sondern ein wirklich erzeugtes Testvideo.

Ohne ffmpeg werden die Tests übersprungen statt rot; wer nur die Logik
prüfen will, braucht also nichts zu installieren.
"""

import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from voice2text import media

FFMPEG = media.find_ffmpeg()
VIDEO_SEKUNDEN = 20


@unittest.skipUnless(FFMPEG, "ffmpeg nicht installiert – Integrationstests übersprungen")
class FfmpegEchtlauf(unittest.TestCase):
    """Testvideo bauen, Tonspur herausschneiden, Längen nachmessen."""

    @classmethod
    def setUpClass(cls):
        cls._ordner = TemporaryDirectory(prefix="voice2text_it_")
        cls.video = Path(cls._ordner.name) / "testvideo.mp4"
        befehl = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={VIDEO_SEKUNDEN}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={VIDEO_SEKUNDEN}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(cls.video),
        ]
        ergebnis = media._run(befehl, "Testvideo bauen")
        if ergebnis.returncode != 0 or not cls.video.exists():
            cls._ordner.cleanup()
            raise unittest.SkipTest("Testvideo ließ sich nicht erzeugen")

    @classmethod
    def tearDownClass(cls):
        cls._ordner.cleanup()

    def test_laenge_wird_richtig_gemessen(self):
        self.assertAlmostEqual(media.probe_duration(self.video), VIDEO_SEKUNDEN, delta=0.5)

    def test_ganze_tonspur(self):
        ziel = Path(self._ordner.name) / "ganz.wav"
        media.extract_audio(self.video, ziel)
        self.assertAlmostEqual(media.probe_duration(ziel), VIDEO_SEKUNDEN, delta=0.5)

    def test_ausschnitt_hat_die_bestellte_laenge(self):
        """Der Kern der ganzen App: ab Sekunde 8, acht Sekunden lang."""
        ziel = Path(self._ordner.name) / "ausschnitt.wav"
        media.extract_audio(self.video, ziel, start=8, duration=8)
        self.assertAlmostEqual(media.probe_duration(ziel), 8.0, delta=0.3)

    def test_ausschnitt_bis_zum_ende(self):
        ziel = Path(self._ordner.name) / "rest.wav"
        media.extract_audio(self.video, ziel, start=15)
        self.assertAlmostEqual(media.probe_duration(ziel), VIDEO_SEKUNDEN - 15, delta=0.5)

    def test_format_passt_zu_whisper(self):
        ziel = Path(self._ordner.name) / "format.wav"
        media.extract_audio(self.video, ziel, duration=3)
        with wave.open(str(ziel)) as datei:
            self.assertEqual(datei.getframerate(), media.SAMPLE_RATE)   # 16 kHz
            self.assertEqual(datei.getnchannels(), 1)                   # Mono
            self.assertEqual(datei.getsampwidth(), 2)                   # 16 bit

    def test_prepare_source_merkt_sich_den_startpunkt(self):
        quelle = media.prepare_source(self.video, start=12.5, duration=5)
        try:
            self.assertEqual(quelle.offset, 12.5)
            self.assertEqual(quelle.title, "testvideo")
            self.assertAlmostEqual(quelle.duration, 5.0, delta=0.3)
            self.assertTrue(quelle.audio_path.exists())
        finally:
            ordner = quelle.audio_path.parent
            quelle.cleanup()
        self.assertFalse(ordner.exists(), "Der Temp-Ordner muss danach verschwunden sein.")

    def test_zerlegen_fuer_die_cloud(self):
        ziel = Path(self._ordner.name) / "lang.wav"
        media.extract_audio(self.video, ziel)
        teile = media.split_audio(ziel, chunk_seconds=8)
        self.assertEqual([versatz for _, versatz in teile], [0.0, 8.0, 16.0])
        for pfad, _ in teile:
            self.assertTrue(pfad.exists())

    def test_fehlende_datei_meldet_sich_klar(self):
        with self.assertRaises(media.MediaError) as fall:
            media.prepare_source(Path(self._ordner.name) / "gibtsnicht.mp4")
        self.assertIn("nicht gefunden", str(fall.exception))


if __name__ == "__main__":
    unittest.main()
