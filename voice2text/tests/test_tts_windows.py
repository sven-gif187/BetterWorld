"""
Tests für die Sprachausgabe, besonders die Windows-Rückfallebene.

Anlass: Auf Svens Rechner scheiterte das Vorlesen mit
"No module named 'pywintypes'" – pyttsx3 braucht unter Windows das Paket
pywin32, dessen Nachbereitungsschritt bei der Installation oft nicht
läuft. Windows bringt aber selbst eine Sprachausgabe mit, die kein
einziges Zusatzpaket braucht. Genau darauf weicht die App jetzt aus.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

from voice2text import tts
from voice2text.tts import TtsError, _tempo_umrechnen, speak, windows_sprachausgabe_da


class Tempo(unittest.TestCase):
    """pyttsx3 zählt Wörter pro Minute, Windows eine Stufe von -10 bis +10."""

    def test_normaltempo_ist_die_mitte(self):
        self.assertEqual(_tempo_umrechnen(175), 0)

    def test_langsamer_wird_negativ(self):
        self.assertLess(_tempo_umrechnen(100), 0)

    def test_schneller_wird_positiv(self):
        self.assertGreater(_tempo_umrechnen(260), 0)

    def test_bleibt_in_den_grenzen(self):
        for wert in (1, 10_000, -500):
            with self.subTest(wert=wert):
                self.assertGreaterEqual(_tempo_umrechnen(wert), -10)
                self.assertLessEqual(_tempo_umrechnen(wert), 10)

    def test_ohne_angabe_normaltempo(self):
        self.assertEqual(_tempo_umrechnen(None), 0)
        self.assertEqual(_tempo_umrechnen(0), 0)


class Verfuegbarkeit(unittest.TestCase):
    def test_auf_nicht_windows_gibt_es_sie_nicht(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(windows_sprachausgabe_da())

    def test_auf_windows_mit_powershell(self):
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch("shutil.which", return_value=r"C:\powershell.exe"):
            self.assertTrue(windows_sprachausgabe_da())

    def test_auf_windows_ohne_powershell(self):
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch("shutil.which", return_value=None):
            self.assertFalse(windows_sprachausgabe_da())

    def test_status_nennt_die_windows_ausgabe(self):
        with mock.patch.object(tts, "windows_sprachausgabe_da", return_value=True):
            self.assertIn("Windows-Sprachausgabe", tts.tts_status())


class Rueckfallebene(unittest.TestCase):
    """Der eigentliche Punkt: Wenn pyttsx3 streikt, muss Windows einspringen."""

    def test_pywintypes_fehler_weicht_auf_windows_aus(self):
        gesprochen = []
        with mock.patch.object(tts, "_new_engine",
                               side_effect=TtsError("No module named 'pywintypes'")), \
             mock.patch.object(tts, "windows_sprachausgabe_da", return_value=True), \
             mock.patch.object(tts, "_windows_sprechen",
                               side_effect=lambda t, r=None, ziel=None: gesprochen.append(t)):
            speak("Guten Morgen.")
        self.assertEqual(gesprochen, ["Guten Morgen."])

    def test_ohne_windows_bleibt_es_beim_fehler(self):
        with mock.patch.object(tts, "_new_engine", side_effect=TtsError("kaputt")), \
             mock.patch.object(tts, "windows_sprachausgabe_da", return_value=False):
            with self.assertRaises(TtsError):
                speak("Text")

    def test_fehler_beim_sprechen_weicht_ebenfalls_aus(self):
        """Nicht nur der Start, auch das Sprechen selbst kann scheitern."""
        gesprochen = []
        engine = mock.MagicMock()
        engine.say.side_effect = RuntimeError("COM-Fehler")
        with mock.patch.object(tts, "_new_engine", return_value=engine), \
             mock.patch.object(tts, "windows_sprachausgabe_da", return_value=True), \
             mock.patch.object(tts, "_windows_sprechen",
                               side_effect=lambda t, r=None, ziel=None: gesprochen.append(t)):
            speak("Text")
        self.assertEqual(gesprochen, ["Text"])

    def test_windows_stimme_geht_direkt_den_kurzen_weg(self):
        """Eine ausdrücklich gewählte Windows-Stimme umgeht pyttsx3 ganz."""
        gesprochen = []
        with mock.patch.object(tts, "_new_engine",
                               side_effect=AssertionError("darf nicht aufgerufen werden")), \
             mock.patch.object(tts, "_windows_sprechen",
                               side_effect=lambda t, r=None, ziel=None: gesprochen.append(t)):
            speak("Text", voice="windows:Microsoft Hedda")
        self.assertEqual(gesprochen, ["Text"])

    def test_speichern_weicht_auch_aus(self):
        geschrieben = []
        with mock.patch.object(tts, "_new_engine", side_effect=TtsError("pywintypes")), \
             mock.patch.object(tts, "windows_sprachausgabe_da", return_value=True), \
             mock.patch.object(tts, "_windows_sprechen",
                               side_effect=lambda t, r=None, ziel=None: geschrieben.append(ziel)):
            tts.save_speech("Text", "/tmp/ausgabe.wav")
        self.assertEqual(geschrieben, [Path("/tmp/ausgabe.wav")])


class Fehlermeldung(unittest.TestCase):
    def test_pywintypes_bekommt_eine_erklaerung(self):
        kaputt = mock.MagicMock()
        kaputt.init.side_effect = ImportError("No module named 'pywintypes'")
        with mock.patch.dict(sys.modules, {"pyttsx3": kaputt}):
            with self.assertRaises(TtsError) as fall:
                tts._new_engine()
        meldung = str(fall.exception)
        self.assertIn("pywin32", meldung)
        self.assertIn("Nötig ist das aber nicht", meldung)


class TextUebergabe(unittest.TestCase):
    def test_text_geht_ueber_eine_datei_nicht_ueber_den_befehl(self):
        """
        Ein Transkript enthält Anführungszeichen, Umlaute und Zeilenumbrüche.
        Würde es in den PowerShell-Befehl geschrieben, zerlegte das den Aufruf.
        """
        aufrufe = []

        def falscher_lauf(befehl, **kwargs):
            aufrufe.append(befehl)
            return mock.MagicMock(returncode=0, stderr="")

        with mock.patch.object(tts, "_powershell", return_value="powershell"), \
             mock.patch("subprocess.run", side_effect=falscher_lauf):
            tts._windows_sprechen('Er sagte: "Hallo" – und ging.\nDann Stille.')

        befehl = " ".join(aufrufe[0])
        self.assertNotIn("Hallo", befehl, "Der Text steht im Befehl statt in einer Datei")
        self.assertIn("Get-Content", befehl)


if __name__ == "__main__":
    unittest.main()
