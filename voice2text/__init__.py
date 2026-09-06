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

__version__ = "1.0.0"
__all__ = ["timecode", "media", "transcribe", "tts", "pipeline"]
