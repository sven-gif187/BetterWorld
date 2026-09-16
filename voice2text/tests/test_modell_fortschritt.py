"""
Tests für die Anzeige des Modell-Downloads.

Anlass: Beim allerersten Start schwieg die App fünf bis zehn Minuten am
Stück. Der Fortschritt lief nur im Konsolenfenster, wo niemand hinschaut –
für den Benutzer sah das aus, als wäre das Programm abgestürzt.
"""

import os
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from voice2text.transcribe import (
    MODELL_MB,
    _download_beobachten,
    modell_ordner,
    modell_schon_da,
    ordner_groesse,
)


class Ordner(unittest.TestCase):
    def test_standardort(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            pfad = modell_ordner("small")
        self.assertEqual(pfad.name, "models--Systran--faster-whisper-small")
        self.assertEqual(pfad.parent.name, "hub")

    def test_hf_home_wird_beachtet(self):
        with mock.patch.dict(os.environ, {"HF_HOME": "/eigener/ort"}, clear=True):
            self.assertEqual(modell_ordner("base"),
                             Path("/eigener/ort/hub/models--Systran--faster-whisper-base"))

    def test_hf_hub_cache_schlaegt_hf_home(self):
        umgebung = {"HF_HOME": "/a", "HF_HUB_CACHE": "/b"}
        with mock.patch.dict(os.environ, umgebung, clear=True):
            self.assertEqual(modell_ordner("tiny").parent, Path("/b"))

    def test_jedes_modell_hat_eine_groesse(self):
        from voice2text.transcribe import MODELS
        for name in MODELS:
            self.assertIn(name, MODELL_MB, f"Größe für '{name}' fehlt")


class Groesse(unittest.TestCase):
    def test_leerer_ordner(self):
        with TemporaryDirectory() as t:
            self.assertEqual(ordner_groesse(Path(t)), 0)

    def test_ordner_gibt_es_nicht(self):
        self.assertEqual(ordner_groesse(Path("/gibt/es/nicht")), 0)

    def test_dateien_werden_addiert(self):
        with TemporaryDirectory() as t:
            (Path(t) / "a.bin").write_bytes(b"x" * 1000)
            unterordner = Path(t) / "tief"
            unterordner.mkdir()
            (unterordner / "b.bin").write_bytes(b"x" * 500)
            self.assertEqual(ordner_groesse(Path(t)), 1500)


class SchonDa(unittest.TestCase):
    def test_bruchstueck_gilt_nicht_als_fertig(self):
        """Ein abgebrochener Download darf nicht als vorhanden durchgehen."""
        with TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": t}, clear=True):
                ordner = modell_ordner("small")
                ordner.mkdir(parents=True)
                (ordner / "teil.bin").write_bytes(b"x" * 1_000_000)   # 1 MB von 484
                self.assertFalse(modell_schon_da("small"))

    def test_vollstaendig_gilt_als_da(self):
        with TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": t}, clear=True):
                ordner = modell_ordner("tiny")
                ordner.mkdir(parents=True)
                (ordner / "modell.bin").write_bytes(b"x" * 70_000_000)  # 70 von 75 MB
                self.assertTrue(modell_schon_da("tiny"))

    def test_gar_nichts_da(self):
        with TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": t}, clear=True):
                self.assertFalse(modell_schon_da("small"))


class Beobachter(unittest.TestCase):
    def test_meldet_wachsende_groesse(self):
        meldungen = []
        with TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": t}, clear=True):
                ordner = modell_ordner("tiny")
                ordner.mkdir(parents=True)
                (ordner / "teil.bin").write_bytes(b"x" * 30_000_000)   # 30 von 75 MB

                fertig = threading.Event()
                with mock.patch("voice2text.transcribe.threading.Event.wait",
                                side_effect=[False, True]):
                    _download_beobachten(
                        "tiny",
                        lambda anteil, text: meldungen.append((anteil, text)),
                        fertig,
                    )

        self.assertEqual(len(meldungen), 1)
        anteil, text = meldungen[0]
        self.assertAlmostEqual(anteil, 30 / 75, places=2)
        self.assertIn("30 von rund 75 MB", text)

    def test_ohne_dateien_kommt_eine_wartemeldung(self):
        meldungen = []
        with TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": t}, clear=True):
                fertig = threading.Event()
                with mock.patch("voice2text.transcribe.threading.Event.wait",
                                side_effect=[False, True]):
                    _download_beobachten(
                        "small",
                        lambda anteil, text: meldungen.append((anteil, text)),
                        fertig,
                    )
        self.assertEqual(meldungen[0][0], None)
        self.assertIn("Verbindung", meldungen[0][1])

    def test_hoert_auf_wenn_fertig_gesetzt_wird(self):
        """Der Beobachter darf nicht als Geisterfaden weiterlaufen."""
        meldungen = []
        fertig = threading.Event()
        faden = threading.Thread(
            target=_download_beobachten,
            args=("tiny", lambda a, t: meldungen.append(t), fertig),
            daemon=True,
        )
        faden.start()
        fertig.set()
        faden.join(timeout=5)
        self.assertFalse(faden.is_alive(), "Der Beobachter läuft noch")


if __name__ == "__main__":
    unittest.main()
