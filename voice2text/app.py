"""
╔══════════════════════════════════════════════════════════════╗
║  🎙️  VOICE2TEXT – Oberfläche                                 ║
╚══════════════════════════════════════════════════════════════╝

Video rein → Text raus. Fünf Reiter:

  🎬 Datei        Video oder Audio vom Rechner transkribieren
  🌐 Online-Link  Link einwerfen, optional Uhrzeit – nur die Stelle wird geholt
  📝 Transkript   Ergebnis lesen, kopieren, als TXT/SRT/VTT/MD speichern
  🔊 Vorlesen     Text zu Sprache – auch das fertige Transkript
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
import traceback
from pathlib import Path

try:
    import customtkinter as ctk
    from tkinter import StringVar, filedialog, messagebox
except ImportError as exc:  # pragma: no cover – nur ohne GUI-Pakete
    raise SystemExit(
        "Für die Oberfläche fehlt customtkinter:\n\n"
        "    pip install customtkinter\n\n"
        "Ohne Oberfläche geht es auch:  python -m voice2text --hilfe\n"
        f"(Ursprünglicher Fehler: {exc})"
    )

from . import media, tts
from .pipeline import Job, run_job, safe_filename, save_all_formats
from .timecode import format_hms
from .transcribe import LANGUAGES, MODELS, Transcript, available_backends, backend_status

# ── FARBEN (gleiche Handschrift wie der Trading-Bot) ──────────
CLR_BG     = "#0a0a0b"
CLR_CARD   = "#141417"
CLR_ACCENT = "#f1c40f"
CLR_GREEN  = "#00ff88"
CLR_RED    = "#ff4655"
CLR_BLUE   = "#4fa3e0"
CLR_GREY   = "#8a8a92"

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
class VoiceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.transcript: Transcript | None = None
        self.busy = False
        self.messages: queue.Queue = queue.Queue()

        self.title("🎙️ Voice2Text – Video & Sprache zu Text")
        self.geometry("1060x780")
        self.minsize(900, 640)
        self.configure(fg_color=CLR_BG)
        ctk.set_appearance_mode("dark")

        self._build_header()
        self._build_tabs()
        self._build_footer()

        self.after(120, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log("👋 Willkommen! Video oder Link auswählen und loslegen.")
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
        self.tab_text = self.tabs.add("📝 Transkript")
        self.tab_tts = self.tabs.add("🔊 Vorlesen")
        self.tab_cfg = self.tabs.add("⚙️ Einstellungen")

        self._build_tab_file()
        self._build_tab_link()
        self._build_tab_text()
        self._build_tab_tts()
        self._build_tab_settings()

    # ---------- 🎬 DATEI ----------
    def _build_tab_file(self):
        frame = self.tab_file
        ctk.CTkLabel(
            frame, text="Video oder Audio vom Rechner transkribieren",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            frame,
            text="Unterstützt mp4, mkv, mov, webm, mp3, m4a, wav … – alles, was ffmpeg lesen kann.",
            text_color=CLR_GREY,
        ).pack(anchor="w", padx=18, pady=(0, 14))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=18)
        self.file_var = StringVar()
        ctk.CTkEntry(
            row, textvariable=self.file_var, height=40,
            placeholder_text="Pfad zur Datei – oder rechts auf „Durchsuchen“ klicken",
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            row, text="📂 Durchsuchen", width=140, height=40, command=self._choose_file,
        ).pack(side="left", padx=(10, 0))

        self.file_start, self.file_end, self.file_dur = self._build_range_row(frame)

        ctk.CTkButton(
            frame, text="▶️  TRANSKRIPTION STARTEN", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=CLR_GREEN, hover_color="#00cc6d", text_color="#04120a",
            command=self._start_file_job,
        ).pack(fill="x", padx=18, pady=(22, 10))

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

        ctk.CTkButton(
            frame, text="▶️  LINK TRANSKRIBIEREN", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=CLR_BLUE, hover_color="#3d87bd",
            command=self._start_link_job,
        ).pack(fill="x", padx=18, pady=(16, 10))

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

        self.log_box = ctk.CTkTextbox(foot, height=130, fg_color=CLR_BG,
                                      font=ctk.CTkFont(size=12, family="monospace"))
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    # ══════════════════════════════════════════════════════════
    # AKTIONEN
    # ══════════════════════════════════════════════════════════
    def _choose_file(self):
        path = filedialog.askopenfilename(title="Video oder Audio auswählen", filetypes=FILETYPES)
        if path:
            self.file_var.set(path)

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
        }

    def _save_settings_clicked(self):
        self.settings = self._current_settings()
        save_settings(self.settings)
        self._log("💾 Einstellungen gespeichert.")

    def _check_environment(self):
        lines = [media.ffmpeg_status(), backend_status(), tts.tts_status()]
        try:
            import yt_dlp  # noqa: F401
            lines.append("✅ Online-Links: yt-dlp bereit")
        except ImportError:
            lines.append("⚠️ Online-Links brauchen yt-dlp (pip install yt-dlp)")

        short = " · ".join(line.split(":")[0] for line in lines)
        self.env_label.configure(text=short)
        if hasattr(self, "status_text"):
            self.status_text.configure(text="\n".join(lines))
        for line in lines:
            if line.startswith(("❌", "⚠️")):
                self._log(line)

    # ── AUFTRÄGE STARTEN ──────────────────────────────────────
    def _start_file_job(self):
        source = self.file_var.get().strip()
        if not source:
            messagebox.showinfo("Keine Datei", "Bitte zuerst eine Video- oder Audiodatei auswählen.")
            return
        self._start_job(source, self.file_start.get(), self.file_end.get(), self.file_dur.get())

    def _start_link_job(self):
        source = self.url_var.get().strip()
        if not source:
            messagebox.showinfo("Kein Link", "Bitte zuerst einen Link einfügen.")
            return
        if not media.looks_like_url(source):
            messagebox.showwarning("Link prüfen", "Das sieht nicht nach einem Link aus – er sollte mit http:// oder https:// beginnen.")
            return
        self._start_job(source, self.url_start.get(), self.url_end.get(), self.url_dur.get())

    def _start_job(self, source: str, start: str, end: str, duration: str):
        if self.busy:
            messagebox.showinfo("Läuft schon", "Es läuft bereits eine Transkription. Bitte kurz warten.")
            return

        self.settings = self._current_settings()
        save_settings(self.settings)

        job = Job(
            source=source,
            start=start or None,
            end=end or None,
            duration=duration or None,
            backend=self.backend_menu.get(),
            model=self.model_menu.get(),
            language=LANGUAGES.get(self.language_menu.get()),
            cookies_from_browser=self.cookies_var.get() or None,
        )

        self.busy = True
        self.progress.set(0)
        self._set_status("Läuft …")
        self._log("─" * 60)
        self._log(f"▶️ Start: {source}")
        threading.Thread(target=self._worker, args=(job,), daemon=True).start()

    def _worker(self, job: Job):
        """Läuft im Hintergrund – meldet sich nur über die Queue."""
        def report(share, message):
            if message:
                self.messages.put(("log", message))
            self.messages.put(("progress", share))

        try:
            transcript = run_job(job, progress=report)
            self.messages.put(("done", transcript))
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            self.messages.put(("error", detail))
            self.messages.put(("log", "🐞 " + traceback.format_exc(limit=2).strip().splitlines()[-1]))

    def _pump(self):
        """Holt Nachrichten aus dem Hintergrund in die Oberfläche."""
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._log(payload)
                    self._set_status(str(payload)[:110])
                elif kind == "progress":
                    if payload is None:
                        self.progress.configure(mode="indeterminate")
                        self.progress.start()
                    else:
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress.set(max(0.0, min(1.0, float(payload))))
                elif kind == "done":
                    self._on_job_done(payload)
                elif kind == "error":
                    self._on_job_failed(payload)
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def _on_job_done(self, transcript: Transcript):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1.0)
        self.transcript = transcript
        self._render_transcript()
        self.tabs.set("📝 Transkript")
        self._set_status("✅ Transkription fertig.")

        if self.autosave_var.get():
            try:
                written = save_all_formats(transcript, self.output_var.get())
                self._log(f"💾 Gespeichert in {Path(written[0]).parent}")
            except Exception as exc:
                self._log(f"⚠️ Automatisches Speichern nicht möglich: {exc}")

    def _on_job_failed(self, message: str):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self._set_status("❌ Abgebrochen.")
        self._log(f"❌ {message}")
        messagebox.showerror("Das hat nicht geklappt", message)

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
            written = save_all_formats(self.transcript, self.output_var.get())
            self._log("💾 " + " · ".join(p.name for p in written))
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

        def work():
            try:
                tts.speak(text, voice=self._selected_voice_id(), rate=int(self.rate_slider.get()))
                self.messages.put(("log", "🔊 Vorlesen beendet."))
            except Exception as exc:
                self.messages.put(("error", str(exc)))

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

        def work():
            try:
                tts.save_speech(text, path, voice=self._selected_voice_id(), rate=int(self.rate_slider.get()))
                self.messages.put(("log", f"💾 Audiodatei gespeichert: {path}"))
            except Exception as exc:
                self.messages.put(("error", str(exc)))

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
        self.destroy()


def main() -> None:
    VoiceApp().mainloop()


if __name__ == "__main__":
    main()
