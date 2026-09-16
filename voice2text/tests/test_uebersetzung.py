"""
Tests für die Übersetzung.

Echte Übersetzungen brauchen ein Sprachpaket oder einen API-Schlüssel –
beides gehört nicht in eine Testsuite. Geprüft wird alles davor und
danach: Sprachnamen, Zerlegung, Dienstwahl, Anweisungsbau und die
Verdrahtung in der Pipeline.
"""

import unittest
from pathlib import Path
from unittest import mock

from voice2text import media, pipeline
from voice2text import uebersetzung as ue
from voice2text.pipeline import Job, run_job
from voice2text.transcribe import Segment, Transcript
from voice2text.uebersetzung import (
    SPRACHEN,
    UebersetzungError,
    absatz_haeppchen,
    sprachkuerzel,
    sprachname,
    uebersetzen,
    uebersetzung_status,
)


class Sprachen(unittest.TestCase):
    def test_name_wird_zu_kuerzel(self):
        self.assertEqual(sprachkuerzel("Englisch"), "en")
        self.assertEqual(sprachkuerzel("Deutsch"), "de")

    def test_kuerzel_bleibt_kuerzel(self):
        self.assertEqual(sprachkuerzel("en"), "en")
        self.assertEqual(sprachkuerzel("DE"), "de")

    def test_kleinschreibung_geht_auch(self):
        self.assertEqual(sprachkuerzel("englisch"), "en")

    def test_leer_bedeutet_keine_angabe(self):
        self.assertIsNone(sprachkuerzel(None))
        self.assertIsNone(sprachkuerzel(""))

    def test_unbekanntes_fliegt_auf(self):
        with self.assertRaises(UebersetzungError) as fall:
            sprachkuerzel("Klingonisch")
        self.assertIn("Möglich:", str(fall.exception))

    def test_rueckweg(self):
        self.assertEqual(sprachname("en"), "Englisch")
        self.assertEqual(sprachname("xx"), "xx")   # unbekannt bleibt stehen

    def test_jede_sprache_ist_beidseitig_uebersetzbar(self):
        for name, kuerzel in SPRACHEN.items():
            with self.subTest(name=name):
                self.assertEqual(sprachkuerzel(name), kuerzel)
                self.assertEqual(sprachname(kuerzel), name)


class Zerlegung(unittest.TestCase):
    def test_kurzer_text_bleibt_am_stueck(self):
        self.assertEqual(absatz_haeppchen("Ein Satz."), ["Ein Satz."])

    def test_leerer_text(self):
        self.assertEqual(absatz_haeppchen(""), [])

    def test_absaetze_bleiben_zusammen(self):
        text = "Sprecher 1: Hallo.\n\nSprecher 2: Guten Tag."
        self.assertEqual(absatz_haeppchen(text, 200), [text])

    def test_grenze_wird_eingehalten(self):
        for teil in absatz_haeppchen("Ein Satz mit Wörtern. " * 500, 300):
            self.assertLessEqual(len(teil), 300)

    def test_bandwurm_ohne_satzzeichen(self):
        teile = absatz_haeppchen("wort " * 400, 300)
        self.assertGreater(len(teile), 1)
        for teil in teile:
            self.assertLessEqual(len(teil), 300)

    def test_nichts_geht_verloren(self):
        text = "Eins. Zwei. Drei. Vier. Fünf."
        zusammen = " ".join(absatz_haeppchen(text, 12))
        for wort in ("Eins", "Zwei", "Drei", "Vier", "Fünf"):
            self.assertIn(wort, zusammen)


class Dienstwahl(unittest.TestCase):
    def test_ohne_dienst_kommt_eine_anleitung(self):
        with mock.patch.object(ue, "verfuegbare_uebersetzer", return_value=[]):
            with self.assertRaises(UebersetzungError) as fall:
                uebersetzen("Hello", nach="Deutsch")
        meldung = str(fall.exception)
        self.assertIn("pip install argostranslate", meldung)
        self.assertIn("Englisch", meldung, "der kostenlose Whisper-Weg muss erwähnt werden")

    def test_status_ist_immer_lesbar(self):
        self.assertTrue(uebersetzung_status().startswith(("✅", "⚠️")))

    def test_gleiche_sprache_bleibt_unangetastet(self):
        """Deutsch nach Deutsch ist keine Arbeit – und kostet auch nichts."""
        with mock.patch.object(ue, "verfuegbare_uebersetzer",
                               side_effect=AssertionError("darf nicht gefragt werden")):
            self.assertEqual(uebersetzen("Hallo", nach="de", von="de"), "Hallo")

    def test_leerer_text_wird_abgelehnt(self):
        with self.assertRaises(UebersetzungError):
            uebersetzen("   ", nach="en")

    def test_unbekannter_dienst(self):
        with mock.patch.object(ue, "verfuegbare_uebersetzer", return_value=["argos"]):
            with self.assertRaises(UebersetzungError):
                uebersetzen("Hello", nach="de", dienst="babelfisch")


class Ablauf(unittest.TestCase):
    def setUp(self):
        self.anfragen = []

        def erfundener_dienst(text, von, nach, melden):
            self.anfragen.append((text, von, nach))
            return f"[{nach}] {text}"

        self.patches = [
            mock.patch.object(ue, "verfuegbare_uebersetzer", return_value=["argos"]),
            mock.patch.dict(ue._UEBERSETZER, {"argos": erfundener_dienst}),
        ]
        for pp in self.patches:
            pp.start()

    def tearDown(self):
        for pp in self.patches:
            pp.stop()

    def test_kurzer_text_eine_anfrage(self):
        self.assertEqual(uebersetzen("Hello", nach="de", von="en"), "[de] Hello")
        self.assertEqual(len(self.anfragen), 1)

    def test_langer_text_wird_stueckweise_uebersetzt(self):
        text = "Ein Satz mit Inhalt. " * 2000
        uebersetzen(text, nach="de", von="en")
        self.assertEqual(len(self.anfragen), len(absatz_haeppchen(text)))

    def test_ohne_quellsprache_wird_englisch_angenommen(self):
        """Argos muss wissen, woher – Englisch ist der häufigste Fall."""
        meldungen = []
        uebersetzen("Hello", nach="de", progress=lambda a, m: meldungen.append(m))
        self.assertEqual(self.anfragen[0][1], "en")
        self.assertTrue(any("Englisch an" in str(m) for m in meldungen))

    def test_ziel_englisch_ohne_quelle_nimmt_deutsch_an(self):
        uebersetzen("Hallo", nach="en")
        self.assertEqual(self.anfragen[0][1], "de")


class InDerPipeline(unittest.TestCase):
    """Der wichtigste Teil: Englisch muss den kostenlosen Weg nehmen."""

    def setUp(self):
        self.quelle = media.MediaSource(
            audio_path=Path("/tmp/a.wav"), title="T", origin="t.mp4", duration=60.0)

    def _lauf(self, job, transkript=None):
        transkript = transkript or Transcript(segments=[Segment(0, 1, "Hello")], language="en")
        with mock.patch.object(media, "prepare_source", return_value=self.quelle), \
             mock.patch.object(pipeline, "transcribe", return_value=transkript) as erkennen:
            ergebnis = run_job(job, progress=lambda a, m: None)
        return ergebnis, erkennen

    def test_englisch_laesst_whisper_uebersetzen(self):
        _, erkennen = self._lauf(Job(source="x.mp4", uebersetzen_nach="Englisch"))
        self.assertEqual(erkennen.call_args.kwargs["task"], "translate")

    def test_kuerzel_geht_auch(self):
        _, erkennen = self._lauf(Job(source="x.mp4", uebersetzen_nach="en"))
        self.assertEqual(erkennen.call_args.kwargs["task"], "translate")

    def test_andere_sprache_erkennt_normal_und_uebersetzt_danach(self):
        with mock.patch.object(ue, "verfuegbare_uebersetzer", return_value=["argos"]), \
             mock.patch.dict(ue._UEBERSETZER,
                             {"argos": lambda t, v, n, m: f"[{n}] {t}"}):
            ergebnis, erkennen = self._lauf(Job(source="x.mp4", uebersetzen_nach="Deutsch"))
        self.assertEqual(erkennen.call_args.kwargs["task"], "transcribe")
        self.assertEqual(ergebnis.translation, "[de] Hello")
        self.assertEqual(ergebnis.translation_language, "Deutsch")

    def test_ohne_zielsprache_passiert_nichts(self):
        ergebnis, erkennen = self._lauf(Job(source="x.mp4"))
        self.assertEqual(erkennen.call_args.kwargs["task"], "transcribe")
        self.assertEqual(ergebnis.translation, "")

    def test_gescheiterte_uebersetzung_kostet_nicht_das_transkript(self):
        """Die Spracherkennung ist zu teuer, um sie daran wegzuwerfen."""
        meldungen = []
        with mock.patch.object(ue, "verfuegbare_uebersetzer", return_value=[]):
            with mock.patch.object(media, "prepare_source", return_value=self.quelle), \
                 mock.patch.object(pipeline, "transcribe",
                                   return_value=Transcript(segments=[Segment(0, 1, "Hello")])):
                ergebnis = run_job(Job(source="x.mp4", uebersetzen_nach="Deutsch"),
                                   progress=lambda a, m: meldungen.append(m))
        self.assertEqual(ergebnis.text, "Hello")
        self.assertEqual(ergebnis.translation, "")
        self.assertTrue(any("übersprungen" in str(m) for m in meldungen))

    def test_uebersetzung_landet_im_markdown(self):
        transkript = Transcript(
            segments=[Segment(0, 1, "Hello")],
            translation="Hallo", translation_language="Deutsch", title="T")
        markdown = transkript.to_markdown()
        self.assertIn("## Übersetzung (Deutsch)", markdown)
        self.assertIn("Hallo", markdown)


class YoutubeFehler(unittest.TestCase):
    """
    yt-dlp-Meldungen sind englisch, technisch und nennen die Lösung nicht.
    Die App soll sie in eine Anweisung übersetzen.
    """

    def test_anmeldung_verlangt(self):
        rat = media._yt_fehler_deuten("ERROR: Sign in to confirm you're not a bot")
        self.assertIn("Cookies", rat)
        self.assertIn("geschlossen", rat, "der Hinweis auf den geschlossenen Browser fehlt")

    def test_veraltetes_ytdlp(self):
        rat = media._yt_fehler_deuten("ERROR: Unable to extract player response")
        self.assertIn("pip install --upgrade yt-dlp", rat)

    def test_video_weg(self):
        self.assertIn("nicht abrufbar", media._yt_fehler_deuten("ERROR: Video unavailable"))

    def test_403(self):
        self.assertIn("403", media._yt_fehler_deuten("HTTP Error 403: Forbidden"))

    def test_falscher_link(self):
        rat = media._yt_fehler_deuten("ERROR: Unsupported URL: https://example.com")
        self.assertIn("watch?v=", rat)

    def test_unbekannter_fehler_bleibt_ohne_deutung(self):
        self.assertEqual(media._yt_fehler_deuten("Etwas völlig Neues"), "")

    def test_unbekannter_fehler_bekommt_trotzdem_allgemeine_hilfe(self):
        with mock.patch.object(media, "_download_with_module",
                               side_effect=RuntimeError("Etwas völlig Neues")):
            with self.assertRaises(media.MediaError) as fall:
                media.download_online_audio("https://youtu.be/x", Path("/tmp"))
        meldung = str(fall.exception)
        self.assertIn("upgrade yt-dlp", meldung)
        self.assertIn("Cookies", meldung)


if __name__ == "__main__":
    unittest.main()
