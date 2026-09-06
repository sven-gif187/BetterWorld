# 🎙️ voice2text – Video & Sprache zu Text

> **Video rein → lesbarer Text raus.**
> Lokale Dateien oder Online-Links, wahlweise nur ein bestimmter Ausschnitt ab einer Uhrzeit.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Offline](https://img.shields.io/badge/Modus-offline%20möglich-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square)

---

## 🚀 Was kann das?

| Feature | Beschreibung |
|---|---|
| 🎬 **Video → Text** | mp4, mkv, mov, webm, mp3, m4a, wav … alles, was ffmpeg lesen kann |
| 🌐 **Online-Links** | YouTube & Co. direkt transkribieren – ohne vorher herunterzuladen |
| ⏱️ **Nur die Stelle** | Link + Uhrzeit → es wird **nur dieser Ausschnitt** geladen, nicht das ganze Video |
| 🔗 **Sprungmarke** | Enthält der Link schon `?t=90`, wird der Startpunkt automatisch übernommen |
| 📍 **Echte Zeitstempel** | Ab Minute 12:30 transkribiert? Die Zeiten passen trotzdem zum Original |
| 💾 **4 Formate** | `.txt` · `.srt` (Untertitel) · `.vtt` (Web) · `.md` (Archiv) |
| 🖱️ **Drag & Drop** | Videos einfach ins Fenster ziehen – mehrere landen in der Warteschlange |
| 📚 **Warteschlange** | Mehrere Videos am Stück, einer nach dem anderen, Fehler stoppen den Rest nicht |
| 👥 **Sprecher-Erkennung** | Wer sagt was – aus Wortsalat wird ein lesbarer Dialog *(optional)* |
| 🧾 **Zusammenfassung** | Stichpunkte, Protokoll oder Aufgabenliste statt einer Stunde Text *(optional)* |
| 🔊 **Text → Sprache** | Transkript oder eigenen Text vorlesen lassen und als Audio speichern |
| 🔐 **Offline möglich** | Mit `faster-whisper` verlässt kein Ton den Rechner – kein Konto, keine Gebühr |
| 💻 **Zwei Wege** | Fenster-Oberfläche **oder** Kommandozeile |

---

## ⚙️ Installation

### Der bequeme Weg: der Einrichtungs-Assistent

```bash
python voice2text/einrichten.py
```

**Windows:** einfach `voice2text\EINRICHTEN_WINDOWS.bat` doppelklicken.

Der Assistent geht sechs Schritte durch, fragt vor jeder Installation nach und macht
am Ende einen **Selbsttest**: Der Rechner spricht einen Satz, die App liest ihn wieder
heraus. Kommt der Satz zurück, funktioniert die ganze Kette.

```
1️⃣  Python-Version      ✅ 3.11.15
2️⃣  Pakete              ✅ installiert
3️⃣  ffmpeg              ✅ gefunden
4️⃣  Spracherkennung     ✅ Modell bereit
5️⃣  Selbsttest          ✅ bestanden
```

Nur nachsehen, ohne etwas zu installieren:

```bash
python voice2text/einrichten.py --nur-pruefen
```

### Der kurze Weg

```bash
pip install -r voice2text/requirements.txt
```

Das war's – `imageio-ffmpeg` bringt ffmpeg gleich mit, es muss nichts von Hand installiert werden.

<details>
<summary>ffmpeg lieber systemweit? (optional, etwas schneller)</summary>

```bash
# Windows
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Linux
sudo apt install ffmpeg
```
</details>

**Prüfen, ob alles bereitsteht:**

```bash
python -m voice2text --status
```

```
🩺 Systemstatus
   ✅ ffmpeg: C:\...\ffmpeg.exe
   ✅ Spracherkennung: faster-whisper
   ✅ Sprachausgabe: pyttsx3
   ✅ Online-Links: yt-dlp bereit
```

---

## 🖥️ Oberfläche starten

```bash
python -m voice2text
```

**Windows:** `voice2text\START_WINDOWS.bat` doppelklicken.

Sieben Reiter:

| Reiter | Wofür |
|---|---|
| 🎬 **Datei** | Video/Audio auswählen oder hineinziehen, optional Ausschnitt setzen, starten |
| 🌐 **Online-Link** | Link einfügen, optional Start/Ende, starten |
| 📚 **Warteschlange** | Mehrere Videos am Stück – Fortschritt, Fehler, fertige Transkripte auf einen Blick |
| 📝 **Transkript** | Ergebnis lesen, kopieren, speichern, vorlesen lassen |
| 🧾 **Zusammenfassung** | Stichpunkte, Protokoll, Aufgabenliste *(braucht API-Schlüssel)* |
| 🔊 **Vorlesen** | Beliebigen Text zu Sprache – Stimme und Tempo einstellbar |
| ⚙️ **Einstellungen** | Modell, Sprache, Backend, Sprecher, Ausgabeordner, Systemstatus |

### Mehrere Videos auf einmal

Dateien ins Fenster ziehen (mehrere gleichzeitig), oder in den Reitern
„🎬 Datei" / „🌐 Online-Link" auf **➕ In die Warteschlange** klicken statt auf Start.
Dann einmal **▶️ Alle abarbeiten** – der Rest läuft von allein.

Ein Eintrag mit Fehler hält die anderen nicht auf; er wird rot markiert und die Liste
läuft weiter. **🛑 Abbrechen** stoppt nach dem gerade laufenden Eintrag, damit keine
halben Dateien zurückbleiben.

Fertige Transkripte landen automatisch in `~/Transkripte` (im Reiter *Einstellungen* änderbar).

---

## ⌨️ Kommandozeile

```bash
# ganzes Video
python -m voice2text video.mp4

# nur von 12:30 bis 14:00
python -m voice2text video.mp4 --start 12:30 --ende 14:00

# Online-Link, ab 1:05:20, 90 Sekunden lang
python -m voice2text "https://www.youtube.com/watch?v=..." --start 1:05:20 --dauer 90

# Link mit eingebauter Sprungmarke – Start kommt automatisch aus dem Link
python -m voice2text "https://youtu.be/abc123?t=90" --dauer 60

# als Untertitel-Datei
python -m voice2text video.mp4 --ausgabe untertitel.srt

# alle vier Formate in einen Ordner
python -m voice2text video.mp4 --ordner ~/Transkripte

# gleich mehrere Videos hintereinander
python -m voice2text video1.mp4 video2.mp4 video3.mp4 --ordner ~/Transkripte

# Gespräch mit Sprechern, dazu ein Protokoll
python -m voice2text besprechung.mp4 --sprecher --zusammenfassung protokoll

# nur die Aufgabenliste aus einer Besprechung
python -m voice2text besprechung.mp4 -z aufgaben

# Text vorlesen lassen
python -m voice2text --sprich "Hallo Sven, das Transkript ist fertig."
```

### Zeitangaben – alle Schreibweisen erlaubt

| Eingabe | Bedeutung |
|---|---|
| `12:30` | Minute 12, Sekunde 30 |
| `1:05:20` | Stunde 1, Minute 5, Sekunde 20 |
| `90` oder `90s` | 90 Sekunden |
| `1h2m3s` | wie YouTube es schreibt |
| `90,5` | mit Nachkommastelle |

---

## 🧠 Welches Modell?

| Modell | Tempo | Qualität | Speicher |
|---|---|---|---|
| `tiny` | blitzschnell | grob | ~1 GB |
| `base` | schnell | brauchbar | ~1 GB |
| **`small`** | **ausgewogen** | **gut – empfohlen für Deutsch** | **~2 GB** |
| `medium` | langsam | sehr gut | ~5 GB |
| `large-v3` | sehr langsam (ohne GPU) | beste | ~10 GB |

Beim ersten Start lädt sich das Modell einmalig herunter (`small` ≈ 500 MB), danach liegt es auf der Platte.

**Faustregel:** Auf einem normalen Laptop braucht `small` etwa so lange wie das Video selbst dauert – bei 10 Minuten Video also rund 10 Minuten. Mit `--start`/`--dauer` nur den interessanten Ausschnitt zu nehmen, spart entsprechend Zeit.

---

## ☁️ Alternative: Erkennung in der Cloud

Wenn der Rechner zu schwach ist, kann OpenAI die Arbeit übernehmen:

```bash
pip install openai
```

Dann in die `.env` im Projektordner:

```
OPENAI_API_KEY=sk-...
```

Danach steht in den Einstellungen das Backend `openai-api` zur Auswahl. Lange Aufnahmen werden automatisch in 10-Minuten-Häppchen geschickt und wieder zusammengesetzt. Achtung: Dabei verlässt der Ton den Rechner und es entstehen Kosten je Minute.

---

## 👥 Sprecher-Erkennung *(optional)*

Statt einer Textwurst wird daraus ein Gespräch:

```
Sprecher 1: Und wie war dein Wochenende?

Sprecher 2: Ganz gut, wir waren wandern.
```

Wer zuerst spricht, ist Sprecher 1. Die Namen stehen auch in den Untertiteln
und im Markdown-Export.

Einrichtung – drei Schritte, alles kostenlos:

1. `pip install pyannote.audio`
2. Konto auf [huggingface.co](https://huggingface.co) anlegen und auf der Seite
   `pyannote/speaker-diarization-3.1` die Nutzungsbedingungen bestätigen
3. Zugriffs-Token unter *Settings → Tokens* erzeugen und in die `.env` eintragen:
   `HUGGINGFACE_TOKEN=hf_...`

Danach in den Einstellungen den Haken bei *Wer sagt was?* setzen, oder auf der
Kommandozeile `--sprecher` mitgeben. Ist die Zahl der Sprecher bekannt, hilft
`--sprecherzahl 2` der Erkennung spürbar.

Klappt etwas davon nicht, läuft die Transkription trotzdem durch – es fehlen
dann nur die Namen.

---

## 🧾 Zusammenfassung *(optional, kostet Geld)*

Aus einer Stunde Transkript werden zehn Zeilen. Fünf Arten stehen zur Wahl:

| Art | Ergebnis |
|---|---|
| `stichpunkte` | Die wichtigsten Punkte als Liste *(Standard)* |
| `fliesstext` | Ein zusammenhängender Absatz |
| `protokoll` | Themen · Beschlüsse · Offene Fragen |
| `aufgaben` | Nur: wer macht was bis wann |
| `kurz` | Drei Sätze, mehr nicht |

Dafür wird ein Sprachmodell gebraucht – entweder

```bash
pip install anthropic     # dann ANTHROPIC_API_KEY in die .env
pip install openai        # oder OPENAI_API_KEY (hat, wer die Cloud-Erkennung nutzt)
```

**Zwei Dinge, die man wissen sollte:** Der Text verlässt dabei den Rechner, und
jede Anfrage kostet ein paar Cent. Lange Transkripte werden automatisch in
Häppchen zerlegt und die Teilergebnisse anschließend verdichtet.

Das Modell wird ausdrücklich angewiesen, nichts zu ergänzen, was nicht im Text
steht – Spracherkennung macht Hörfehler, und ein Sprachmodell füllt Lücken
sonst bereitwillig mit Erfundenem.

---

## 🩺 Wenn etwas klemmt

| Meldung | Lösung |
|---|---|
| `ffmpeg wurde nicht gefunden` | `pip install imageio-ffmpeg` |
| `Kein Spracherkenner installiert` | `pip install faster-whisper` |
| `Online-Links brauchen yt-dlp` | `pip install yt-dlp` |
| `Sign in to confirm` bei einem Link | In den Einstellungen den Browser für Cookies hinterlegen (Video verlangt Anmeldung) |
| Sprachausgabe bleibt stumm (Linux) | `sudo apt install espeak-ng` |
| Ziehen ins Fenster tut nichts | `pip install tkinterdnd2`, danach App neu starten |
| Sprecher-Erkennung wird übersprungen | Token fehlt oder Nutzungsbedingungen auf huggingface.co nicht bestätigt |
| Zusammenfassung nicht möglich | Kein `ANTHROPIC_API_KEY` bzw. `OPENAI_API_KEY` in der `.env` |
| Erkennung ist ungenau | Sprache fest auf *Deutsch* stellen statt „automatisch“, oder Modell `medium` nehmen |
| Alles ist zu langsam | Kleineres Modell (`base`) oder mit `--start`/`--dauer` nur den nötigen Ausschnitt |

---

## 🧩 Aufbau

```
voice2text/
├── __main__.py     Einstieg:  ohne Argumente → Fenster, mit Argumenten → Kommandozeile
├── app.py          Oberfläche (customtkinter, 7 Reiter, Drag & Drop)
├── cli.py          Kommandozeile
├── pipeline.py     Der Ablauf: Quelle → Ausschnitt → Ton → Text
├── media.py        ffmpeg & yt-dlp: Tonspur holen, Online-Links anzapfen
├── transcribe.py   Spracherkennung (faster-whisper / whisper / OpenAI-API)
├── timecode.py     Zeitangaben lesen und formatieren
├── tts.py          Text → Sprache
├── warteschlange.py Mehrere Aufträge nacheinander (ohne GUI, deshalb testbar)
├── sprecher.py     Sprecher-Erkennung und Zuordnung zu den Sätzen
├── zusammenfassung.py Transkript → Stichpunkte, Protokoll, Aufgabenliste
├── einrichten.py   Einrichtungs-Assistent mit Selbsttest
└── tests/          119 Tests (8 davon mit echtem ffmpeg, sonst übersprungen)
```

Tests ausführen:

```bash
python -m unittest discover -s voice2text/tests -t .
```

---

## ⚠️ Bitte beachten

Beim Laden von Online-Videos gelten die Nutzungsbedingungen der jeweiligen Plattform. Bitte nur Inhalte verarbeiten, für die du die Erlaubnis hast. Und wenn Aufnahmen andere Menschen zeigen oder zu hören sind: Vor dem Weitergeben eines Transkripts kurz überlegen, ob die damit einverstanden wären.

---

<div align="center">
  Made with ❤️ · Teil von <a href="../README.md">BetterWorld</a>
</div>
