"""
🎙️ voice2text – Video & Sprache zu Text (und wieder zurück)

Ein kleines Paket mit vier Bausteinen:

    timecode   – Zeitangaben lesen und formatieren
    media      – Ton aus Video holen, Online-Links anzapfen (ffmpeg/yt-dlp)
    transcribe – Spracherkennung mit Whisper (offline oder Cloud)
    tts        – Text wieder vorlesen lassen

Start der Oberfläche:   python -m voice2text
Kommandozeile:          python -m voice2text video.mp4 --start 12:30
"""

__version__ = "1.1.0"
__all__ = [
    "timecode", "media", "transcribe", "tts",
    "pipeline", "warteschlange", "sprecher", "zusammenfassung", "konfig",
]

# Schlüssel aus der .env in die Umgebung holen, sobald das Paket geladen
# wird. Ohne diesen Schritt stünde in der Anleitung "Schlüssel in die .env
# eintragen" – und er käme nie an. Echte Umgebungsvariablen bleiben unangetastet.
from .konfig import env_laden as _env_laden  # noqa: E402

try:
    _env_laden()
except Exception:                              # eine kaputte .env darf nichts blockieren
    pass
