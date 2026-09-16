"""Tests für die Zeitlogik – hier steckt der meiste Ärger, also am gründlichsten geprüft."""

import unittest

from voice2text.timecode import (
    format_hms,
    format_timestamp,
    parse_timecode,
    parse_url_time,
    resolve_range,
)


class ParseTimecode(unittest.TestCase):
    def test_doppelpunkt_schreibweisen(self):
        self.assertEqual(parse_timecode("1:23:45"), 5025.0)
        self.assertEqual(parse_timecode("12:30"), 750.0)
        self.assertEqual(parse_timecode("00:00:07"), 7.0)
        self.assertEqual(parse_timecode("0:01.5"), 1.5)

    def test_nackte_sekunden(self):
        self.assertEqual(parse_timecode("90"), 90.0)
        self.assertEqual(parse_timecode("90s"), 90.0)
        self.assertEqual(parse_timecode(90), 90.0)
        self.assertEqual(parse_timecode(90.5), 90.5)

    def test_youtube_schreibweise(self):
        self.assertEqual(parse_timecode("1h2m3s"), 3723.0)
        self.assertEqual(parse_timecode("2m"), 120.0)
        self.assertEqual(parse_timecode("1m30s"), 90.0)
        self.assertEqual(parse_timecode("1H30M"), 5400.0)

    def test_komma_als_dezimaltrenner(self):
        self.assertEqual(parse_timecode("90,5"), 90.5)

    def test_leer_bedeutet_nicht_angegeben(self):
        self.assertIsNone(parse_timecode(None))
        self.assertIsNone(parse_timecode(""))
        self.assertIsNone(parse_timecode("   "))

    def test_unsinn_fliegt_auf(self):
        for wert in ("abc", "1:2:3:4", "12:", ":30", "-5", "-1:00", "12x30"):
            with self.subTest(wert=wert):
                with self.assertRaises(ValueError):
                    parse_timecode(wert)


class FormatTimecode(unittest.TestCase):
    def test_srt_format(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")
        self.assertEqual(format_timestamp(90.5), "00:01:30,500")
        self.assertEqual(format_timestamp(3723.456), "01:02:03,456")

    def test_vtt_format_nutzt_punkt(self):
        self.assertEqual(format_timestamp(90.5, "."), "00:01:30.500")

    def test_negative_zeiten_werden_abgefangen(self):
        self.assertEqual(format_timestamp(-3), "00:00:00,000")

    def test_kompakte_anzeige(self):
        self.assertEqual(format_hms(0), "0:00")
        self.assertEqual(format_hms(65), "1:05")
        self.assertEqual(format_hms(3723), "1:02:03")

    def test_hin_und_zurueck(self):
        for sekunden in (0.0, 7.25, 90.5, 3723.456, 36000.0):
            with self.subTest(sekunden=sekunden):
                text = format_timestamp(sekunden)
                self.assertAlmostEqual(parse_timecode(text.replace(",", ".")), sekunden, places=2)


class UrlZeit(unittest.TestCase):
    def test_youtube_kurzlink(self):
        self.assertEqual(parse_url_time("https://youtu.be/abc123?t=90"), 90.0)

    def test_youtube_langlink_mit_hms(self):
        self.assertEqual(parse_url_time("https://www.youtube.com/watch?v=abc&t=1h2m3s"), 3723.0)

    def test_start_parameter(self):
        self.assertEqual(parse_url_time("https://example.com/v?start=42"), 42.0)

    def test_fragment(self):
        self.assertEqual(parse_url_time("https://example.com/video#t=42"), 42.0)

    def test_ohne_zeit(self):
        self.assertIsNone(parse_url_time("https://www.youtube.com/watch?v=abc"))
        self.assertIsNone(parse_url_time(""))

    def test_kaputter_wert_stuerzt_nicht_ab(self):
        self.assertIsNone(parse_url_time("https://example.com/v?t=morgen"))


class Bereich(unittest.TestCase):
    def test_start_und_ende_werden_zu_dauer(self):
        self.assertEqual(resolve_range("1:00", end="2:30"), (60.0, 90.0))

    def test_start_und_dauer_bleiben(self):
        self.assertEqual(resolve_range("1:00", duration="90"), (60.0, 90.0))

    def test_ende_schlaegt_dauer(self):
        self.assertEqual(resolve_range("1:00", end="2:00", duration="600"), (60.0, 60.0))

    def test_nur_ende_ohne_start(self):
        self.assertEqual(resolve_range(None, end="0:30"), (None, 30.0))

    def test_nichts_angegeben(self):
        self.assertEqual(resolve_range(), (None, None))

    def test_ende_vor_start_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            resolve_range("2:00", end="1:00")


if __name__ == "__main__":
    unittest.main()
