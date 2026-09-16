"""
╔══════════════════════════════════════════════════════════════╗
║  🎙️  VOICE2TEXT – Oberfläche                                 ║
╚══════════════════════════════════════════════════════════════╝

Video rein → Text raus. Sechs Reiter:

  🎬 Datei         Video oder Audio vom Rechner – auch per Drag & Drop
  🌐 Online-Link   Link einwerfen, optional Uhrzeit – nur die Stelle wird geholt
  📚 Warteschlange Mehrere Videos am Stück, einer nach dem anderen
  📝 Transkript    Ergebnis lesen, kopieren, als TXT/SRT/VTT/MD speichern
  🔊 Vorlesen      Text zu Sprache – auch das fertige Transkript
  ⚙️ Einstellungen Modell, Sprache, Backend, Ausgabeordner

Start:  python -m voice2text
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

try:
    import customtkinter as ctk
    from tkinter import StringVar, filedialog, messagebox
except ImportError as exc:  # pragma: no cover – nur ohne GUI-Pakete
    fehlt_tkinter = "tkinter" in str(exc)
    raise SystemExit(
        ("Für die Oberfläche fehlt tkinter – das gehört zu Python selbst:\n\n"
         "    Linux :  sudo apt install python3-tk\n"
         "    Mac   :  brew install python-tk\n"
         "    Windows: Python neu installieren und dabei 'tcl/tk' anhaken\n\n"
         if fehlt_tkinter else
         "Für die Oberfläche fehlt customtkinter:\n\n"
         "    pip install customtkinter\n\n")
        + "Ohne Oberfläche geht es auch:  python -m voice2text --hilfe\n"
        + f"(Ursprünglicher Fehler: {exc})"
    )

from . import media, tts
from .pipeline import Job, safe_filename, save_all_formats
from .timecode import format_hms
from .sprecher import sprecher_status
from .transcribe import LANGUAGES, MODELS, Transcript, available_backends, backend_status
from .zusammenfassung import ARTEN as ZF_ARTEN
from .zusammenfassung import ZusammenfassungError, zusammenfassen, zusammenfassung_status
from .warteschlange import FEHLER, FERTIG, LAEUFT, WARTET, Auftrag, Warteschlange

# ── DRAG & DROP (optional) ────────────────────────────────────
# Ohne tkinterdnd2 läuft alles wie gehabt, nur eben ohne Ziehen.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_DA = True
except Exception:
    DND_DA = False

if DND_DA:
    class _Fenster(ctk.CTk, TkinterDnD.DnDWrapper):
        """customtkinter-Fenster, das zusätzlich Dateien per Maus annimmt."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:                                       # pragma: no cover
    _Fenster = ctk.CTk

# ── FARBEN (gleiche Handschrift wie der Trading-Bot) ──────────
CLR_BG     = "#0a0a0b"
CLR_CARD   = "#141417"
CLR_ACCENT = "#f1c40f"
CLR_GREEN  = "#00ff88"
CLR_RED    = "#ff4655"
CLR_BLUE   = "#4fa3e0"
CLR_GREY   = "#8a8a92"

STATUS_FARBE = {WARTET: CLR_GREY, LAEUFT: CLR_ACCENT, FERTIG: CLR_GREEN, FEHLER: CLR_RED}
STATUS_ZEICHEN = {WARTET: "⏳", LAEUFT: "▶️", FERTIG: "✅", FEHLER: "❌"}

SETTINGS_FILE = Path.home() / ".voice2text.json"
DEFAULT_OUTPUT = Path.home() / "Transkripte"

FILETYPES = [
    ("Video & Audio", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mp3 *.wav *.m4a *.aac *.ogg *.opus *.flac"),
    ("Alle Dateien", "*.*"),
]


# ══════════════════════════════════════════════════════════════
# EINSTELLUNGEN – überleben den Neustart
# ══════════════════════════════════════════════════════════════
def load_settings() -> dict:
    defaults = {
        "backend": "auto",
        "model": "small",
        "language": "Deutsch",
        "output_dir": str(DEFAULT_OUTPUT),
        "auto_save": True,
        "cookies_browser": "",
        "sprecher": False,
        "sprecherzahl": "",
        "zf_art": "stichpunkte",
    }
    try:
        if SETTINGS_FILE.exists():
            defaults.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass                                   # kaputte Datei? Dann eben Standardwerte.
    return defaults


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def open_folder(path: str | Path) -> None:
    """Ausgabeordner im Datei-Explorer zeigen."""
    path = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)                 # noqa: S606 – gewollt
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# DIE APP
# ══════════════════════════════════════════════════════════════
class VoiceApp(_Fenster):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.transcript: Transcript | None = None
        self.messages: queue.Queue = queue.Queue()
        self.zf_laeuft = False
        self.schlange = Warteschlange(ereignis=self._schlangen_ereignis)

        self.title("🎙️ Voice2Text – Video & Sprache zu Text")
        self.geometry("1060x820")
        self.minsize(900, 660)
        self.configure(fg_color=CLR_BG)
        ctk.set_appearance_mode("dark")

        self._build_header()
        self._build_tabs()
        self._build_footer()

        self.after(120, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._log("👋 Willkommen! Video oder Link auswählen und loslegen.")
        if DND_DA:
            self._log("🖱️ Tipp: Videos lassen sich direkt ins Fenster ziehen.")
            self._drop_ziel(self, self._drop_irgendwo)
        self._check_environment()

    # ── KOPFZEILE ─────────────────────────────────────────────
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=CLR_CARD, corner_radius=0, height=64)
        head.pack(fill="x")
        head.pack_propagate(False)

        ctk.CTkLabel(
            head, text="🎙️ VOICE2TEXT",
            font=ctk.CTkFont(size=22, weight="bold"), text_color=CLR_ACCENT,
        ).pack(side="left", padx=20)

        ctk.CTkLabel(
            head, text="Video · Audio · Online-Link  →  lesbarer Text",
            font=ctk.CTkFont(size=13), text_color=CLR_GREY,
        ).pack(side="left")

        self.env_label = ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=12), text_color=CLR_GREY, justify="right",
        )
        self.env_label.pack(side="right", padx=20)

    # ── REITER ────────────────────────────────────────────────
    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(
            self, fg_color=CLR_CARD, segmented_button_selected_color=CLR_ACCENT,
            segmented_button_selected_hover_color=CLR_ACCENT, text_color="#ffffff",
        )
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(12, 6))

        self.tab_file = self.tabs.add("🎬 Datei")
        self.tab_link = self.tabs.add("🌐 Online-Link")
        self.tab_queue = self.tabs.add("📚 Warteschlange")
        self.tab_text = self.tabs.add("📝 Transkript")
        self.tab_sum = self.tabs.add("🧾 Zusammenfassung")
        self.tab_tts = self.tabs.add("🔊 Vorlesen")
        self.tab_cfg = self.tabs.add("⚙️ Einstellungen")

        self._build_tab_file()
        self._build_tab_link()
        self._build_tab_queue()
        self._build_tab_text()
        self._build_tab_sum()
        self._build_tab_tts()
        self._build_tab_settings()

    # ---------- 🎬 DATEI ----------
    def _build_tab_file(self):
        frame = self.tab_file
        ctk.CTkLabel(
            frame, text="Video oder Audio vom Rechner transkribieren",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))

        hinweis = "Unterstützt mp4, mkv, mov, webm, mp3, m4a, wav … – alles, was ffmpeg lesen kann."
        if DND_DA:
            hinweis += "\n🖱️ Datei einfach ins Fenster ziehen – mehrere landen in der Warteschlange."
        ctk.CTkLabel(frame, text=hinweis, text_color=CLR_GREY, justify="left").pack(
            anchor="w", padx=18, pady=(0, 14))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=18)
        self.file_var = StringVar()
        self.file_entry = ctk.CTkEntry(
            row, textvariable=self.file_var, height=40,
            placeholder_text="Pfad zur Datei – oder rechts auf „Durchsuchen“ klicken",
        )
        self.file_entry.pack(side="left", fill="x", expand=True)
        self._drop_ziel(self.file_entry, self._drop_auf_dateifeld)

        ctk.CTkButton(
            row, text="📂 Durchsuchen", width=140, height=40, command=self._choose_file,
        ).pack(side="left", padx=(10, 0))

        self.file_start, self.file_end, self.file_dur = self._build_range_row(frame)

        knoepfe = ctk.CTkFrame(frame, fg_color="transparent")
        knoepfe.pack(fill="x", padx=18, pady=(22, 10))
        ctk.CTkButton(
            knoepfe, text="▶️  TRANSKRIPTION STARTEN", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=CLR_GREEN, hover_color="#00cc6d", text_color="#04120a",
            command=self._start_file_job,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            knoepfe, text="➕ In die Warteschlange", height=48, width=200,
            command=lambda: self._start_file_job(sofort=False),
        ).pack(side="left", padx=(10, 0))

    # ---------- 🌐 LINK ----------
    def _build_tab_link(self):
        frame = self.tab_link
        ctk.CTkLabel(
            frame, text="Direkt von einem Online-Video",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame,
            text=("Link einfügen – wahlweise mit Uhrzeit. Dann wird nur genau diese Stelle geladen\n"
                  "statt des ganzen Videos. Enthält der Link schon eine Sprungmarke (…?t=90),\n"
                  "wird sie automatisch übernommen."),
            text_color=CLR_GREY, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        self.url_var = StringVar()
        ctk.CTkEntry(
            frame, textvariable=self.url_var, height=40,
            placeholder_text="https://www.youtube.com/watch?v=…    oder jeder andere Video-Link",
        ).pack(fill="x", padx=18)

        self.url_start, self.url_end, self.url_dur = self._build_range_row(frame)

        ctk.CTkLabel(
            frame,
            text="ℹ️ Bitte nur Inhalte laden, die du auch laden darfst – die Nutzungsbedingungen der Plattform gelten weiterhin.",
            text_color=CLR_GREY, font=ctk.CTkFont(size=11), wraplength=900, justify="left",
        ).pack(anchor="w", padx=18, pady=(14, 0))

        knoepfe = ctk.CTkFrame(frame, fg_color="transparent")
        knoepfe.pack(fill="x", padx=18, pady=(16, 10))
        ctk.CTkButton(
            knoepfe, text="▶️  LINK TRANSKRIBIEREN", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=CLR_BLUE, hover_color="#3d87bd",
            command=self._start_link_job,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            knoepfe, text="➕ In die Warteschlange", height=48, width=200,
            command=lambda: self._start_link_job(sofort=False),
        ).pack(side="left", padx=(10, 0))

    def _build_range_row(self, parent):
        """Drei Felder für Start / Ende / Dauer – identisch in beiden Reitern."""
        box = ctk.CTkFrame(parent, fg_color=CLR_BG, corner_radius=10)
        box.pack(fill="x", padx=18, pady=(16, 0))

        ctk.CTkLabel(
            box, text="✂️  Ausschnitt (optional)   ·   Schreibweisen: 12:30 · 1:05:20 · 90 · 1h2m3s",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_ACCENT,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 8))

        start_var, end_var, dur_var = StringVar(), StringVar(), StringVar()
        for column, (label, var, hint) in enumerate((
            ("Start", start_var, "z. B. 12:30"),
            ("Ende", end_var, "z. B. 14:00"),
            ("oder Dauer", dur_var, "z. B. 90"),
        )):
            cell = ctk.CTkFrame(box, fg_color="transparent")
            cell.grid(row=1, column=column, sticky="ew", padx=14, pady=(0, 14))
            box.grid_columnconfigure(column, weight=1)
            ctk.CTkLabel(cell, text=label, text_color=CLR_GREY, font=ctk.CTkFont(size=12)).pack(anchor="w")
            ctk.CTkEntry(cell, textvariable=var, height=36, placeholder_text=hint).pack(fill="x")

        return start_var, end_var, dur_var

    # ---------- 📚 WARTESCHLANGE ----------
    def _build_tab_queue(self):
        frame = self.tab_queue
        ctk.CTkLabel(
            frame, text="Mehrere Videos am Stück",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))

        hinweis = ("Einträge werden nacheinander abgearbeitet – parallel wäre nicht schneller,\n"
                   "beide würden sich denselben Prozessor teilen.")
        if DND_DA:
            hinweis += "\n🖱️ Mehrere Dateien gleichzeitig ins Fenster ziehen füllt die Liste auf einmal."
        ctk.CTkLabel(frame, text=hinweis, text_color=CLR_GREY, justify="left").pack(
            anchor="w", padx=18, pady=(0, 12))

        leiste = ctk.CTkFrame(frame, fg_color="transparent")
        leiste.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkButton(
            leiste, text="▶️ Alle abarbeiten", fg_color=CLR_GREEN, text_color="#04120a",
            hover_color="#00cc6d", command=self._queue_start,
        ).pack(side="left")
        ctk.CTkButton(leiste, text="🛑 Abbrechen", fg_color=CLR_RED, hover_color="#cc3644",
                      command=self._queue_abbrechen).pack(side="left", padx=8)
        ctk.CTkButton(leiste, text="🧹 Erledigte entfernen",
                      command=self._queue_aufraeumen).pack(side="left")
        ctk.CTkButton(leiste, text="📁 Ausgabeordner",
                      command=lambda: open_folder(self.output_var.get())).pack(side="right")

        self.queue_info = ctk.CTkLabel(frame, text="Warteschlange ist leer.", text_color=CLR_GREY)
        self.queue_info.pack(anchor="w", padx=18)

        self.queue_list = ctk.CTkScrollableFrame(frame, fg_color=CLR_BG)
        self.queue_list.pack(fill="both", expand=True, padx=18, pady=(8, 14))
        self._drop_ziel(self.queue_list, self._drop_in_warteschlange)

    # ---------- 📝 TRANSKRIPT ----------
    def _build_tab_text(self):
        frame = self.tab_text

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(14, 8))

        self.timestamp_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            bar, text="Mit Zeitstempeln", variable=self.timestamp_var,
            command=self._render_transcript, fg_color=CLR_ACCENT, hover_color=CLR_ACCENT,
        ).pack(side="left")

        for text, command in (
            ("📋 Kopieren", self._copy_transcript),
            ("💾 Speichern …", self._save_transcript_as),
            ("📦 Alle Formate", self._save_all_formats),
            ("🔊 Vorlesen", self._speak_transcript),
        ):
            ctk.CTkButton(bar, text=text, width=130, command=command).pack(side="right", padx=(8, 0))

        self.transcript_info = ctk.CTkLabel(
            frame, text="Noch kein Transkript – starte oben mit einer Datei oder einem Link.",
            text_color=CLR_GREY,
        )
        self.transcript_info.pack(anchor="w", padx=18)

        self.transcript_box = ctk.CTkTextbox(
            frame, fg_color=CLR_BG, font=ctk.CTkFont(size=14), wrap="word",
        )
        self.transcript_box.pack(fill="both", expand=True, padx=18, pady=(8, 14))

    # ---------- 🧾 ZUSAMMENFASSUNG ----------
    def _build_tab_sum(self):
        frame = self.tab_sum
        ctk.CTkLabel(
            frame, text="Das Wichtigste in Kürze",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame,
            text=("Aus einer Stunde Transkript werden zehn Zeilen.\n"
                  "Dafür wird der Text an ein Sprachmodell geschickt – das kostet pro Anfrage\n"
                  "und verlässt den Rechner. Ohne API-Schlüssel bleibt dieser Reiter untätig,\n"
                  "alles andere funktioniert weiterhin."),
            text_color=CLR_GREY, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        leiste = ctk.CTkFrame(frame, fg_color="transparent")
        leiste.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(leiste, text="Art", text_color=CLR_GREY).pack(side="left")
        self.zf_art_menu = ctk.CTkOptionMenu(
            leiste, values=list(ZF_ARTEN), width=180, command=self._on_zf_art_change)
        self.zf_art_menu.set(self.settings.get("zf_art", "stichpunkte"))
        self.zf_art_menu.pack(side="left", padx=(8, 12))
        self.zf_hint = ctk.CTkLabel(
            leiste, text=ZF_ARTEN.get(self.settings.get("zf_art", "stichpunkte"), ""),
            text_color=CLR_GREY)
        self.zf_hint.pack(side="left")

        ctk.CTkButton(leiste, text="📋 Kopieren", width=120,
                      command=self._copy_summary).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            leiste, text="🧾 Zusammenfassen", width=180,
            fg_color=CLR_ACCENT, text_color="#101010", hover_color="#d4ac0d",
            command=self._zusammenfassen_klick,
        ).pack(side="right")

        self.summary_box = ctk.CTkTextbox(
            frame, fg_color=CLR_BG, font=ctk.CTkFont(size=14), wrap="word")
        self.summary_box.pack(fill="both", expand=True, padx=18, pady=(4, 14))

    def _on_zf_art_change(self, wert: str):
        self.zf_hint.configure(text=ZF_ARTEN.get(wert, ""))

    def _zusammenfassen_klick(self):
        if not self._require_transcript():
            return
        if self.zf_laeuft:
            self._log("🧾 Läuft bereits.")
            return

        text = self.transcript.text
        art = self.zf_art_menu.get()
        self.zf_laeuft = True
        self._log(f"🧾 Zusammenfassung wird erstellt ({art}) …")

        def arbeit():
            try:
                ergebnis = zusammenfassen(
                    text, art=art,
                    progress=lambda anteil, meldung: self.messages.put(("log", meldung)),
                )
                self.messages.put(("zusammenfassung", ergebnis))
            except ZusammenfassungError as exc:
                self.messages.put(("zusammenfassung_fehler", str(exc)))
            except Exception as exc:
                self.messages.put(("zusammenfassung_fehler", str(exc)))

        threading.Thread(target=arbeit, daemon=True).start()

    def _zeige_zusammenfassung(self, text: str):
        self.zf_laeuft = False
        if self.transcript:
            self.transcript.summary = text
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", text)
        self.tabs.set("🧾 Zusammenfassung")
        self._log("🧾 Zusammenfassung fertig.")

    def _copy_summary(self):
        text = self.summary_box.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Noch nichts da", "Es gibt noch keine Zusammenfassung.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log("📋 Zusammenfassung kopiert.")

    # ---------- 🔊 VORLESEN ----------
    def _build_tab_tts(self):
        frame = self.tab_tts
        ctk.CTkLabel(
            frame, text="Text vorlesen lassen", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame, text="Eigenen Text eintippen oder das fertige Transkript übernehmen.",
            text_color=CLR_GREY,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        self.tts_box = ctk.CTkTextbox(frame, fg_color=CLR_BG, height=260, font=ctk.CTkFont(size=14), wrap="word")
        self.tts_box.pack(fill="both", expand=True, padx=18)

        controls = ctk.CTkFrame(frame, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=12)

        ctk.CTkLabel(controls, text="Stimme", text_color=CLR_GREY).pack(side="left")
        self.voice_menu = ctk.CTkOptionMenu(controls, values=["Standard"], width=260)
        self.voice_menu.pack(side="left", padx=(8, 18))

        ctk.CTkLabel(controls, text="Tempo", text_color=CLR_GREY).pack(side="left")
        self.rate_slider = ctk.CTkSlider(controls, from_=100, to=260, number_of_steps=32, width=180)
        self.rate_slider.set(175)
        self.rate_slider.pack(side="left", padx=(8, 0))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(buttons, text="📝 Transkript übernehmen", command=self._tts_take_transcript).pack(side="left")
        ctk.CTkButton(
            buttons, text="🔊 Vorlesen", fg_color=CLR_GREEN, text_color="#04120a",
            hover_color="#00cc6d", command=self._speak_textbox,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(buttons, text="💾 Als Audiodatei", command=self._save_speech).pack(side="right")

        self._voices: list = []
        threading.Thread(target=self._load_voices, daemon=True).start()

    # ---------- ⚙️ EINSTELLUNGEN ----------
    def _build_tab_settings(self):
        frame = self.tab_cfg
        wrap = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)

        def section(title: str) -> ctk.CTkFrame:
            ctk.CTkLabel(wrap, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=CLR_ACCENT).pack(anchor="w", padx=10, pady=(16, 6))
            box = ctk.CTkFrame(wrap, fg_color=CLR_BG, corner_radius=10)
            box.pack(fill="x", padx=10)
            return box

        # Modell
        box = section("🧠 Erkennungs-Modell")
        self.model_menu = ctk.CTkOptionMenu(box, values=list(MODELS), width=200, command=self._on_model_change)
        self.model_menu.set(self.settings.get("model", "small"))
        self.model_menu.pack(side="left", padx=14, pady=14)
        self.model_hint = ctk.CTkLabel(box, text=MODELS.get(self.settings.get("model", "small"), ""),
                                       text_color=CLR_GREY)
        self.model_hint.pack(side="left", padx=(4, 14))

        # Sprache
        box = section("🗣️ Gesprochene Sprache")
        self.language_menu = ctk.CTkOptionMenu(box, values=list(LANGUAGES), width=240)
        self.language_menu.set(self.settings.get("language", "Deutsch"))
        self.language_menu.pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="Fest eingestellt ist meist genauer als „automatisch“.",
                     text_color=CLR_GREY).pack(side="left")

        # Backend
        box = section("⚙️ Backend")
        options = ["auto"] + (available_backends() or [])
        self.backend_menu = ctk.CTkOptionMenu(box, values=options, width=200)
        self.backend_menu.set(self.settings.get("backend", "auto") if self.settings.get("backend") in options else "auto")
        self.backend_menu.pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="„auto“ nimmt das schnellste installierte Verfahren.",
                     text_color=CLR_GREY).pack(side="left")

        # Ausgabeordner
        box = section("📁 Ausgabeordner")
        self.output_var = StringVar(value=self.settings.get("output_dir", str(DEFAULT_OUTPUT)))
        ctk.CTkEntry(box, textvariable=self.output_var, height=36).pack(
            side="left", fill="x", expand=True, padx=(14, 8), pady=14)
        ctk.CTkButton(box, text="Wählen", width=90, command=self._choose_output_dir).pack(side="left")
        ctk.CTkButton(box, text="Öffnen", width=90,
                      command=lambda: open_folder(self.output_var.get())).pack(side="left", padx=(8, 14))

        self.autosave_var = ctk.BooleanVar(value=bool(self.settings.get("auto_save", True)))
        ctk.CTkCheckBox(wrap, text="Fertige Transkripte automatisch dort speichern (txt · srt · vtt · md)",
                        variable=self.autosave_var, fg_color=CLR_ACCENT,
                        hover_color=CLR_ACCENT).pack(anchor="w", padx=10, pady=(10, 0))

        # Sprecher
        box = section("👥 Sprecher-Erkennung (optional)")
        self.sprecher_var = ctk.BooleanVar(value=bool(self.settings.get("sprecher", False)))
        ctk.CTkCheckBox(box, text="Wer sagt was?", variable=self.sprecher_var,
                        fg_color=CLR_ACCENT, hover_color=CLR_ACCENT).pack(
            side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="Anzahl (falls bekannt)", text_color=CLR_GREY).pack(side="left")
        self.sprecherzahl_var = StringVar(value=str(self.settings.get("sprecherzahl", "")))
        ctk.CTkEntry(box, textvariable=self.sprecherzahl_var, width=60,
                     placeholder_text="z. B. 2").pack(side="left", padx=(8, 14))
        ctk.CTkLabel(box, text="Braucht pyannote.audio und ein Hugging-Face-Token.",
                     text_color=CLR_GREY).pack(side="left")

        # Cookies
        box = section("🍪 Browser-Cookies für Online-Links (optional)")
        self.cookies_var = StringVar(value=self.settings.get("cookies_browser", ""))
        ctk.CTkOptionMenu(box, values=["", "chrome", "firefox", "edge", "brave", "safari"],
                          variable=self.cookies_var, width=200).pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(box, text="Nur nötig bei Videos, die eine Anmeldung verlangen.",
                     text_color=CLR_GREY).pack(side="left")

        # Systemstatus
        box = section("🩺 Systemstatus")
        self.status_text = ctk.CTkLabel(box, text="", justify="left", text_color=CLR_GREY)
        self.status_text.pack(anchor="w", padx=14, pady=14)
        ctk.CTkButton(wrap, text="🔄 Status neu prüfen", command=self._check_environment).pack(
            anchor="w", padx=10, pady=(10, 4))
        ctk.CTkButton(wrap, text="💾 Einstellungen speichern", fg_color=CLR_ACCENT, text_color="#101010",
                      hover_color="#d4ac0d", command=self._save_settings_clicked).pack(
            anchor="w", padx=10, pady=(4, 16))

    # ── FUSSZEILE: Fortschritt & Protokoll ────────────────────
    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color=CLR_CARD, corner_radius=10)
        foot.pack(fill="both", padx=14, pady=(0, 12))

        line = ctk.CTkFrame(foot, fg_color="transparent")
        line.pack(fill="x", padx=14, pady=(12, 4))
        self.status_label = ctk.CTkLabel(line, text="Bereit.", text_color=CLR_GREY, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress = ctk.CTkProgressBar(foot, height=10, progress_color=CLR_ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=14, pady=(0, 8))

        self.log_box = ctk.CTkTextbox(foot, height=120, fg_color=CLR_BG,
                                      font=ctk.CTkFont(size=12, family="monospace"))
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    # ══════════════════════════════════════════════════════════
    # DRAG & DROP
    # ══════════════════════════════════════════════════════════
    def _drop_ziel(self, widget, handler) -> None:
        """Macht ein Bedienelement zum Ablageziel – falls tkinterdnd2 da ist."""
        if not DND_DA:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", handler)
        except Exception:
            pass                               # nicht schlimm, dann eben ohne

    def _pfade_aus_drop(self, event) -> list[str]:
        """
        Zerlegt die abgelegten Pfade.

        Tk liefert sie als eine Zeichenkette; Pfade mit Leerzeichen stehen
        dabei in geschweiften Klammern. splitlist() kennt diese Regel.
        """
        try:
            roh = self.tk.splitlist(event.data)
        except Exception:
            roh = str(getattr(event, "data", "")).split()
        pfade = []
        for eintrag in roh:
            pfad = str(eintrag).strip().strip("{}")
            if pfad and Path(pfad).exists():
                pfade.append(pfad)
        return pfade

    def _drop_auf_dateifeld(self, event):
        pfade = self._pfade_aus_drop(event)
        if not pfade:
            return
        self.file_var.set(pfade[0])
        self._log(f"🖱️ Übernommen: {Path(pfade[0]).name}")
        if len(pfade) > 1:
            self._in_warteschlange(pfade[1:])

    def _drop_in_warteschlange(self, event):
        self._in_warteschlange(self._pfade_aus_drop(event))

    def _drop_irgendwo(self, event):
        """Ablegen außerhalb der Felder: eine Datei ins Feld, mehrere in die Liste."""
        pfade = self._pfade_aus_drop(event)
        if not pfade:
            return
        if len(pfade) == 1:
            self.file_var.set(pfade[0])
            self.tabs.set("🎬 Datei")
            self._log(f"🖱️ Übernommen: {Path(pfade[0]).name}")
        else:
            self._in_warteschlange(pfade)

    def _in_warteschlange(self, pfade: list[str]) -> None:
        for pfad in pfade:
            self.schlange.hinzufuegen(self._job_bauen(pfad, "", "", ""))
        self._log(f"➕ {len(pfade)} Einträge in die Warteschlange gelegt.")
        self.tabs.set("📚 Warteschlange")

    # ══════════════════════════════════════════════════════════
    # AKTIONEN
    # ══════════════════════════════════════════════════════════
    def _choose_file(self):
        pfade = filedialog.askopenfilenames(title="Video oder Audio auswählen", filetypes=FILETYPES)
        if not pfade:
            return
        self.file_var.set(pfade[0])
        if len(pfade) > 1:
            self._in_warteschlange(list(pfade[1:]))

    def _choose_output_dir(self):
        path = filedialog.askdirectory(title="Ausgabeordner wählen")
        if path:
            self.output_var.set(path)

    def _on_model_change(self, value: str):
        self.model_hint.configure(text=MODELS.get(value, ""))

    def _current_settings(self) -> dict:
        return {
            "backend": self.backend_menu.get(),
            "model": self.model_menu.get(),
            "language": self.language_menu.get(),
            "output_dir": self.output_var.get(),
            "auto_save": bool(self.autosave_var.get()),
            "cookies_browser": self.cookies_var.get(),
            "sprecher": bool(self.sprecher_var.get()),
            "sprecherzahl": self.sprecherzahl_var.get(),
            "zf_art": self.zf_art_menu.get(),
        }

    def _save_settings_clicked(self):
        self.settings = self._current_settings()
        save_settings(self.settings)
        self._log("💾 Einstellungen gespeichert.")

    def _check_environment(self):
        lines = [media.ffmpeg_status(), backend_status(), tts.tts_status(),
                 sprecher_status(), zusammenfassung_status()]
        try:
            import yt_dlp  # noqa: F401
            yt_dlp_da = True
            lines.append("✅ Online-Links: yt-dlp bereit")
        except ImportError:
            yt_dlp_da = False
            lines.append("⚠️ Online-Links brauchen yt-dlp (pip install yt-dlp)")
        lines.append("✅ Drag & Drop: aktiv" if DND_DA
                     else "⚠️ Drag & Drop braucht tkinterdnd2 (pip install tkinterdnd2)")

        from .konfig import env_datei_finden, gesetzte_schluessel
        datei = env_datei_finden()
        lines.append(f"📄 .env: {datei}" if datei else "📄 .env: keine gefunden (nur für Zusatzfunktionen nötig)")
        schluessel = gesetzte_schluessel()
        # Nur Namen anzeigen – ein Schlüssel gehört nicht auf den Bildschirm.
        lines.append("🔑 Schlüssel: " + (" · ".join(schluessel) if schluessel else "keine"))

        # Oben rechts ist wenig Platz – dort nur Häkchen, die Sätze stehen
        # ausführlich im Reiter "Einstellungen".
        def marke(name: str, da: bool) -> str:
            return f"{name} {'✅' if da else '❌'}"

        kurz = " · ".join((
            marke("ffmpeg", bool(media.find_ffmpeg())),
            marke("Whisper", bool(available_backends())),
            marke("Stimme", bool(tts.available_engines())),
            marke("Links", yt_dlp_da),
            marke("Ziehen", DND_DA),
        ))
        self.env_label.configure(text=kurz)
        if hasattr(self, "status_text"):
            self.status_text.configure(text="\n".join(lines))
        for line in lines:
            if line.startswith(("❌", "⚠️")):
                self._log(line)

    # ── AUFTRÄGE ──────────────────────────────────────────────
    def _job_bauen(self, quelle: str, start: str, ende: str, dauer: str) -> Job:
        self.settings = self._current_settings()
        save_settings(self.settings)
        return Job(
            source=quelle,
            start=start or None,
            end=ende or None,
            duration=dauer or None,
            backend=self.backend_menu.get(),
            model=self.model_menu.get(),
            language=LANGUAGES.get(self.language_menu.get()),
            cookies_from_browser=self.cookies_var.get() or None,
            sprecher=bool(self.sprecher_var.get()),
            sprecherzahl=self._sprecherzahl(),
        )

    def _sprecherzahl(self) -> int | None:
        """Leeres oder unsinniges Feld heißt schlicht: Anzahl unbekannt."""
        try:
            zahl = int(str(self.sprecherzahl_var.get()).strip())
            return zahl if zahl > 0 else None
        except (TypeError, ValueError):
            return None

    def _start_file_job(self, sofort: bool = True):
        quelle = self.file_var.get().strip()
        if not quelle:
            messagebox.showinfo("Keine Datei", "Bitte zuerst eine Video- oder Audiodatei auswählen.")
            return
        self._auftrag_annehmen(quelle, self.file_start.get(), self.file_end.get(),
                               self.file_dur.get(), sofort)

    def _start_link_job(self, sofort: bool = True):
        quelle = self.url_var.get().strip()
        if not quelle:
            messagebox.showinfo("Kein Link", "Bitte zuerst einen Link einfügen.")
            return
        if not media.looks_like_url(quelle):
            messagebox.showwarning(
                "Link prüfen",
                "Das sieht nicht nach einem Link aus – er sollte mit http:// oder https:// beginnen.")
            return
        self._auftrag_annehmen(quelle, self.url_start.get(), self.url_end.get(),
                               self.url_dur.get(), sofort)

    def _auftrag_annehmen(self, quelle: str, start: str, ende: str, dauer: str, sofort: bool):
        try:
            job = self._job_bauen(quelle, start, ende, dauer)
        except ValueError as exc:
            messagebox.showwarning("Zeitangabe prüfen", str(exc))
            return

        auftrag = self.schlange.hinzufuegen(job)
        if not sofort:
            self._log(f"➕ [{auftrag.nummer}] in die Warteschlange gelegt.")
            self.tabs.set("📚 Warteschlange")
            return

        if self.schlange.laeuft:
            self._log(f"➕ [{auftrag.nummer}] angehängt – kommt nach dem laufenden Eintrag dran.")
            self.tabs.set("📚 Warteschlange")
            return

        self.progress.set(0)
        self._log("─" * 60)
        self.schlange.starten()

    def _queue_start(self):
        if self.schlange.laeuft:
            self._log("▶️ Läuft bereits.")
            return
        if not self.schlange.starten():
            messagebox.showinfo("Nichts zu tun", "In der Warteschlange wartet gerade kein Eintrag.")

    def _queue_abbrechen(self):
        if not self.schlange.laeuft:
            self._log("Es läuft gerade nichts.")
            return
        self.schlange.abbrechen()

    def _queue_aufraeumen(self):
        entfernt = self.schlange.erledigte_entfernen()
        self._log(f"🧹 {entfernt} erledigte Einträge entfernt." if entfernt
                  else "🧹 Nichts zu entfernen.")

    # ── BRÜCKE VOM HINTERGRUND IN DIE OBERFLÄCHE ──────────────
    def _schlangen_ereignis(self, art: str, wert) -> None:
        """Läuft im Arbeits-Thread – deshalb nur in die Queue legen, nichts zeichnen."""
        self.messages.put((art, wert))

    def _pump(self):
        """Holt Nachrichten aus dem Hintergrund in die Oberfläche."""
        neu_zeichnen = False
        try:
            while True:
                art, wert = self.messages.get_nowait()
                if art == "log":
                    self._log(str(wert))
                    self._set_status(str(wert)[:110])
                elif art == "fortschritt":
                    self._set_progress(wert)
                elif art == "aenderung":
                    neu_zeichnen = True
                elif art == "fertig":
                    self._auftrag_fertig(wert)
                    neu_zeichnen = True
                elif art == "fehler":
                    self._auftrag_gescheitert(wert)
                    neu_zeichnen = True
                elif art == "leer":
                    self._schlange_fertig()
                    neu_zeichnen = True
                elif art == "zusammenfassung":
                    self._zeige_zusammenfassung(str(wert))
                elif art == "zusammenfassung_fehler":
                    self.zf_laeuft = False
                    self._log(f"⚠️ Zusammenfassung nicht möglich: {str(wert).splitlines()[0]}")
                    messagebox.showinfo("Zusammenfassung nicht möglich", str(wert))
                elif art == "hinweis":
                    messagebox.showerror("Das hat nicht geklappt", str(wert))
        except queue.Empty:
            pass
        if neu_zeichnen:
            self._render_queue()
        self.after(120, self._pump)

    def _set_progress(self, anteil):
        if anteil is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(max(0.0, min(1.0, float(anteil))))

    def _auftrag_fertig(self, auftrag: Auftrag):
        self.transcript = auftrag.transcript
        self._render_transcript()
        if self.schlange.offen == 0:
            self.tabs.set("📝 Transkript")

        if self.autosave_var.get() and auftrag.transcript:
            try:
                geschrieben = save_all_formats(auftrag.transcript, self.output_var.get())
                self._log(f"💾 Gespeichert in {Path(geschrieben[0]).parent}")
            except Exception as exc:
                self._log(f"⚠️ Automatisches Speichern nicht möglich: {exc}")

    def _auftrag_gescheitert(self, auftrag: Auftrag):
        self._log(f"❌ [{auftrag.nummer}] {auftrag.name}: {auftrag.fehler}")
        # Bei einem einzelnen Eintrag darf ruhig ein Fenster aufgehen; bei
        # zwanzig Einträgen wäre das eine Klickorgie – dann reicht die Liste.
        if len(self.schlange.auftraege) == 1:
            messagebox.showerror("Das hat nicht geklappt", auftrag.fehler)

    def _schlange_fertig(self):
        self._set_progress(0.0 if self.schlange.offen else 1.0)
        self._set_status("✅ " + self.schlange.zusammenfassung())
        self._log("✅ " + self.schlange.zusammenfassung())

    # ── WARTESCHLANGE ANZEIGEN ────────────────────────────────
    def _render_queue(self):
        for kind in self.queue_list.winfo_children():
            kind.destroy()

        auftraege = self.schlange.auftraege
        self.queue_info.configure(text=self.schlange.zusammenfassung())
        if not auftraege:
            ctk.CTkLabel(
                self.queue_list,
                text="Noch nichts da.\n\nDateien hierher ziehen oder in den Reitern oben\n"
                     "auf „➕ In die Warteschlange“ klicken.",
                text_color=CLR_GREY, justify="left",
            ).pack(anchor="w", padx=16, pady=16)
            return

        for auftrag in auftraege:
            zeile = ctk.CTkFrame(self.queue_list, fg_color=CLR_CARD, corner_radius=8)
            zeile.pack(fill="x", padx=6, pady=4)

            ctk.CTkLabel(
                zeile, text=f"{STATUS_ZEICHEN.get(auftrag.status, '•')} {auftrag.nummer}",
                width=50, text_color=STATUS_FARBE.get(auftrag.status, CLR_GREY),
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(side="left", padx=(12, 6), pady=10)

            text = auftrag.name
            if auftrag.status == FEHLER and auftrag.fehler:
                text += f"   —   {auftrag.fehler.splitlines()[0][:70]}"
            elif auftrag.status == FERTIG and auftrag.transcript:
                text += f"   —   {len(auftrag.transcript.text.split())} Wörter"
            ctk.CTkLabel(
                zeile, text=text, anchor="w",
                text_color="#ffffff" if not auftrag.erledigt else CLR_GREY,
            ).pack(side="left", fill="x", expand=True)

            # Erst der Papierkorb, dann das Auge: was zuerst nach rechts
            # gepackt wird, sitzt außen – so stehen die Papierkörbe in allen
            # Zeilen untereinander, auch wenn das Auge mal fehlt.
            if auftrag.status != LAEUFT:
                ctk.CTkButton(zeile, text="🗑", width=40, fg_color=CLR_CARD,
                              hover_color=CLR_RED,
                              command=lambda a=auftrag: self._entferne_auftrag(a)).pack(side="right", padx=(0, 10))
            if auftrag.status == FERTIG:
                ctk.CTkButton(zeile, text="👁", width=40,
                              command=lambda a=auftrag: self._zeige_auftrag(a)).pack(side="right", padx=(0, 4))

    def _zeige_auftrag(self, auftrag: Auftrag):
        if auftrag.transcript:
            self.transcript = auftrag.transcript
            self._render_transcript()
            self.tabs.set("📝 Transkript")

    def _entferne_auftrag(self, auftrag: Auftrag):
        if self.schlange.entfernen(auftrag):
            self._render_queue()

    # ── TRANSKRIPT ────────────────────────────────────────────
    def _render_transcript(self):
        if not self.transcript:
            return
        text = self.transcript.to_text(with_timestamps=bool(self.timestamp_var.get()))
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.insert("1.0", text)

        transcript = self.transcript
        parts = [
            f"🗣️ {transcript.language or 'unbekannt'}",
            f"🧠 {transcript.backend} / {transcript.model}",
            f"✂️ {len(transcript.segments)} Abschnitte",
            f"📝 {len(transcript.text.split())} Wörter",
        ]
        if transcript.duration:
            parts.append(f"⏱️ {format_hms(transcript.duration)}")
        if transcript.offset:
            parts.append(f"↪️ ab {format_hms(transcript.offset)} im Original")
        self.transcript_info.configure(text="   ·   ".join(parts))

    def _require_transcript(self) -> bool:
        if self.transcript and self.transcript.segments:
            return True
        messagebox.showinfo("Noch nichts da", "Es gibt noch kein Transkript zum Weiterverarbeiten.")
        return False

    def _copy_transcript(self):
        if not self._require_transcript():
            return
        self.clipboard_clear()
        self.clipboard_append(self.transcript_box.get("1.0", "end").strip())
        self._log("📋 Transkript in die Zwischenablage kopiert.")

    def _save_transcript_as(self):
        if not self._require_transcript():
            return
        stem = safe_filename(self.transcript.title or "transkript")
        path = filedialog.asksaveasfilename(
            title="Transkript speichern",
            initialdir=self.output_var.get(),
            initialfile=f"{stem}.txt",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Untertitel SRT", "*.srt"),
                       ("Untertitel VTT", "*.vtt"), ("Markdown", "*.md")],
        )
        if not path:
            return
        try:
            self.transcript.export(path, with_timestamps=bool(self.timestamp_var.get()))
            self._log(f"💾 Gespeichert: {path}")
        except Exception as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))

    def _save_all_formats(self):
        if not self._require_transcript():
            return
        try:
            geschrieben = save_all_formats(self.transcript, self.output_var.get())
            self._log("💾 " + " · ".join(p.name for p in geschrieben))
            open_folder(self.output_var.get())
        except Exception as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))

    # ── VORLESEN ──────────────────────────────────────────────
    def _load_voices(self):
        try:
            self._voices = tts.list_voices()
        except Exception:
            self._voices = []
        names = ["Standard"] + [v.name for v in self._voices]
        try:
            self.voice_menu.configure(values=names)
        except Exception:
            pass

    def _selected_voice_id(self) -> str | None:
        name = self.voice_menu.get()
        for voice in self._voices:
            if voice.name == name:
                return voice.id
        return None

    def _tts_take_transcript(self):
        if not self._require_transcript():
            return
        self.tts_box.delete("1.0", "end")
        self.tts_box.insert("1.0", self.transcript.text)
        self.tabs.set("🔊 Vorlesen")

    def _speak_transcript(self):
        if not self._require_transcript():
            return
        self._speak(self.transcript.text)

    def _speak_textbox(self):
        self._speak(self.tts_box.get("1.0", "end").strip())

    def _speak(self, text: str):
        if not text.strip():
            messagebox.showinfo("Kein Text", "Bitte zuerst etwas eintippen oder das Transkript übernehmen.")
            return

        stimme = self._selected_voice_id()
        tempo = int(self.rate_slider.get())

        def work():
            try:
                tts.speak(text, voice=stimme, rate=tempo)
                self.messages.put(("log", "🔊 Vorlesen beendet."))
            except Exception as exc:
                self.messages.put(("hinweis", str(exc)))

        self._log("🔊 Vorlesen …")
        threading.Thread(target=work, daemon=True).start()

    def _save_speech(self):
        text = self.tts_box.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Kein Text", "Bitte zuerst etwas eintippen.")
            return
        path = filedialog.asksaveasfilename(
            title="Sprachausgabe speichern",
            initialdir=self.output_var.get(),
            initialfile="sprachausgabe.wav",
            defaultextension=".wav",
            filetypes=[("WAV (offline)", "*.wav"), ("MP3 (über gTTS)", "*.mp3")],
        )
        if not path:
            return

        stimme = self._selected_voice_id()
        tempo = int(self.rate_slider.get())

        def work():
            try:
                tts.save_speech(text, path, voice=stimme, rate=tempo)
                self.messages.put(("log", f"💾 Audiodatei gespeichert: {path}"))
            except Exception as exc:
                self.messages.put(("hinweis", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    # ── KLEINKRAM ─────────────────────────────────────────────
    def _log(self, message: str):
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def _set_status(self, message: str):
        self.status_label.configure(text=message)

    def _on_close(self):
        try:
            save_settings(self._current_settings())
        except Exception:
            pass
        if self.schlange.laeuft:
            if not messagebox.askokcancel(
                "Noch am Arbeiten",
                "Es läuft noch eine Transkription. Wirklich beenden?\n"
                "Der laufende Eintrag geht dabei verloren.",
            ):
                return
            self.schlange.abbrechen()
        self.destroy()


def main() -> None:
    VoiceApp().mainloop()


if __name__ == "__main__":
    main()
