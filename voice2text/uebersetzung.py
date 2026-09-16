"""
╔══════════════════════════════════════════════════════════════╗
║  ÜBERSETZUNG – Fremdsprachen lesbar machen                   ║
╚══════════════════════════════════════════════════════════════╝

Ein englisches Video soll deutschen Text ergeben. Oder umgekehrt.

Drei Wege, absteigend nach Bequemlichkeit:

  ⚡ Whisper selbst  – kann beim Erkennen direkt ins Englische
                       übersetzen. Kostenlos, offline, kein Zusatzpaket.
                       Aber: nur nach Englisch, in keine andere Sprache.
                       (Steckt in transcribe.py, nicht hier.)

  🌍 Argos Translate – übersetzt offline in jede Richtung, kostenlos,
                       kein Konto. Die Sprachpakete lädt es beim ersten
                       Mal selbst herunter (~100 MB je Sprachpaar).

  🧠 Sprachmodell    – die beste Qualität, besonders bei Fachbegriffen
                       und Redewendungen. Kostet pro Anfrage und
                       schickt den Text aus dem Haus.

Ohne all das bleibt das Transkript einfach in seiner Originalsprache –
kaputt geht nichts.
"""

from __future__ import annotations

import os
from typing import Callable

__all__ = [
    "SPRACHEN",
    "UebersetzungError",
    "verfuegbare_uebersetzer",
    "uebersetzung_status",
    "uebersetzen",
    "sprachkuerzel",
    "sprachname",
    "absatz_haeppchen",
]

ProgressFn = Callable[[float | None, str], None]

# Ab hier stückweise. Eigener Name, weil die Zusammenfassung ihre eigene
# Grenze hat – in einer Einzeldatei würden sich gleiche Namen beißen.
MAX_ZEICHEN_UEBERSETZUNG = 8_000

ANTHROPIC_MODELL = "claude-opus-5"
OPENAI_MODELL = "gpt-4o-mini"

SPRACHEN: dict[str, str] = {
    "Deutsch": "de",
    "Englisch": "en",
    "Französisch": "fr",
    "Spanisch": "es",
    "Italienisch": "it",
    "Niederländisch": "nl",
    "Polnisch": "pl",
    "Portugiesisch": "pt",
    "Russisch": "ru",
    "Türkisch": "tr",
    "Arabisch": "ar",
    "Chinesisch": "zh",
    "Japanisch": "ja",
}


class UebersetzungError(RuntimeError):
    """Die Übersetzung konnte nicht erstellt werden."""


def sprachkuerzel(sprache: str | None) -> str | None:
    """
    Macht aus "Englisch" das Kürzel "en".

    Kürzel werden unverändert durchgelassen, damit beides geht –
    "Deutsch" aus der Oberfläche und "de" von der Kommandozeile.
    """
    if not sprache:
        return None
    sprache = str(sprache).strip()
    if sprache in SPRACHEN:
        return SPRACHEN[sprache]
    kurz = sprache.lower()
    if kurz in SPRACHEN.values():
        return kurz
    # Auch "englisch" klein geschrieben soll gehen.
    for name, kuerzel in SPRACHEN.items():
        if name.lower() == kurz:
            return kuerzel
    raise UebersetzungError(
        f"Unbekannte Sprache '{sprache}'. Möglich: {', '.join(SPRACHEN)}"
    )


def sprachname(kuerzel: str) -> str:
    """Rückweg fürs Anzeigen: "en" → "Englisch"."""
    for name, kurz in SPRACHEN.items():
        if kurz == kuerzel:
            return name
    return kuerzel


# ══════════════════════════════════════════════════════════════
# WELCHE DIENSTE STEHEN BEREIT?
# ══════════════════════════════════════════════════════════════
def _paket_da(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def verfuegbare_uebersetzer() -> list[str]:
    """
    Nutzbare Übersetzer – bester zuerst.

    Argos steht vorn, weil es nichts kostet und den Text nicht aus dem
    Haus schickt. Ein Sprachmodell liefert schöneres Deutsch, aber dafür
    muss man bezahlen und die Aufnahme verlässt den Rechner.
    """
    dienste = []
    if _paket_da("argostranslate"):
        dienste.append("argos")
    if _paket_da("anthropic") and os.getenv("ANTHROPIC_API_KEY"):
        dienste.append("anthropic")
    if _paket_da("openai") and os.getenv("OPENAI_API_KEY"):
        dienste.append("openai")
    return dienste


def uebersetzung_status() -> str:
    dienste = verfuegbare_uebersetzer()
    if dienste:
        return "✅ Übersetzung: " + " · ".join(dienste)
    return ("⚠️ Übersetzung: nicht eingerichtet (optional) – "
            "ins Englische geht es auch ohne, direkt beim Erkennen")


def _uebersetzer_waehlen(dienst: str) -> str:
    verfuegbar = verfuegbare_uebersetzer()
    if dienst and dienst != "auto":
        if dienst not in verfuegbar:
            raise UebersetzungError(
                f"Der Übersetzer '{dienst}' steht nicht zur Verfügung.\n"
                f"Nutzbar wäre: {', '.join(verfuegbar) or 'nichts'}"
            )
        return dienst
    if not verfuegbar:
        raise UebersetzungError(
            "Für die Übersetzung fehlt noch ein Übersetzer.\n\n"
            "Kostenlos und offline (empfohlen):\n"
            "    pip install argostranslate\n\n"
            "Oder mit Sprachmodell (bessere Qualität, kostet pro Anfrage):\n"
            "    pip install anthropic     und ANTHROPIC_API_KEY in die .env\n\n"
            "Hinweis: Ins Englische übersetzt Whisper auch ohne all das –\n"
            "dafür in den Einstellungen 'Übersetzen nach: Englisch' wählen."
        )
    return verfuegbar[0]


# ══════════════════════════════════════════════════════════════
# TEXT ZERLEGEN – ohne Netz, deshalb gut testbar
# ══════════════════════════════════════════════════════════════
def absatz_haeppchen(text: str, max_zeichen: int = MAX_ZEICHEN_UEBERSETZUNG) -> list[str]:
    """
    Zerlegt langen Text an Absatz- und Satzgrenzen.

    Übersetzer arbeiten satzweise; mitten im Wort zu trennen ergäbe
    Kauderwelsch. Absätze bleiben möglichst zusammen, damit der
    Zusammenhang erhalten bleibt.
    """
    import re

    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_zeichen:
        return [text]

    stuecke: list[str] = []
    aktuell = ""
    for absatz in text.split("\n"):
        if len(absatz) > max_zeichen:
            # Zu langer Absatz: an Satzenden weiter zerlegen.
            for satz in re.split(r"(?<=[.!?…])\s+", absatz):
                while len(satz) > max_zeichen:
                    if aktuell:
                        stuecke.append(aktuell.strip())
                        aktuell = ""
                    stuecke.append(satz[:max_zeichen])
                    satz = satz[max_zeichen:]
                if len(aktuell) + len(satz) + 1 > max_zeichen and aktuell:
                    stuecke.append(aktuell.strip())
                    aktuell = satz
                else:
                    aktuell = f"{aktuell} {satz}".strip()
            continue

        if len(aktuell) + len(absatz) + 1 > max_zeichen and aktuell:
            stuecke.append(aktuell.strip())
            aktuell = absatz
        else:
            aktuell = f"{aktuell}\n{absatz}".strip() if aktuell else absatz

    if aktuell.strip():
        stuecke.append(aktuell.strip())
    return [s for s in stuecke if s.strip()]


# ══════════════════════════════════════════════════════════════
# DIE ÜBERSETZER
# ══════════════════════════════════════════════════════════════
def _argos_paket_sichern(von: str, nach: str, melden: ProgressFn) -> None:
    """Lädt das Sprachpaket, falls es noch fehlt."""
    import argostranslate.package
    import argostranslate.translate

    vorhanden = {
        (s.code, z.code)
        for s in argostranslate.translate.get_installed_languages()
        for z in s.translations_from
    } if hasattr(argostranslate.translate, "get_installed_languages") else set()
    if (von, nach) in vorhanden:
        return

    melden(None, f"🌍 Sprachpaket {von} → {nach} wird geholt (~100 MB, nur dieses eine Mal) …")
    try:
        argostranslate.package.update_package_index()
        pakete = argostranslate.package.get_available_packages()
        passend = next(
            (p for p in pakete if p.from_code == von and p.to_code == nach), None
        )
        if passend is None:
            raise UebersetzungError(
                f"Für {sprachname(von)} → {sprachname(nach)} gibt es bei Argos kein "
                "Sprachpaket.\nMit einem Sprachmodell ginge es trotzdem – siehe Einstellungen."
            )
        argostranslate.package.install_from_path(passend.download())
    except UebersetzungError:
        raise
    except Exception as exc:
        raise UebersetzungError(
            f"Das Sprachpaket konnte nicht geladen werden: {exc}\n"
            "Meist fehlt schlicht die Internetverbindung."
        ) from exc


def _uebersetze_argos(text: str, von: str, nach: str, melden: ProgressFn) -> str:
    import argostranslate.translate

    _argos_paket_sichern(von, nach, melden)
    melden(None, f"🌍 Übersetzung {sprachname(von)} → {sprachname(nach)} läuft (offline) …")
    try:
        return argostranslate.translate.translate(text, von, nach).strip()
    except Exception as exc:
        raise UebersetzungError(f"Argos konnte nicht übersetzen: {exc}") from exc


def _anweisung(nach: str) -> str:
    return (
        f"Übersetze den folgenden Text nach {sprachname(nach)}.\n\n"
        "Der Text stammt aus einer automatischen Spracherkennung: Er enthält "
        "Hörfehler, abgebrochene Sätze und fehlende Satzzeichen. Übersetze, "
        "was dasteht – erfinde nichts dazu und lass nichts weg. Ist eine "
        "Stelle unverständlich, übernimm sie unverändert statt zu raten.\n\n"
        "Gib ausschließlich die Übersetzung zurück, ohne Vorrede und ohne "
        "Anmerkungen. Zeilenumbrüche und Sprecher-Angaben wie 'Sprecher 1:' "
        "bleiben erhalten."
    )


def _uebersetze_anthropic(text: str, von: str, nach: str, melden: ProgressFn) -> str:
    import anthropic

    client = anthropic.Anthropic()
    argumente = dict(
        model=ANTHROPIC_MODELL,
        max_tokens=8192,
        system=_anweisung(nach),
        messages=[{"role": "user", "content": text}],
        # Übersetzen ist Handwerk, kein Knobeln – niedriger Aufwand genügt.
        output_config={"effort": "low"},
    )
    try:
        antwort = client.messages.create(**argumente)
    except (TypeError, anthropic.BadRequestError):
        argumente.pop("output_config", None)
        antwort = client.messages.create(**argumente)
    except anthropic.AuthenticationError as exc:
        raise UebersetzungError("Der ANTHROPIC_API_KEY wird nicht akzeptiert.") from exc
    except anthropic.APIConnectionError as exc:
        raise UebersetzungError("Keine Verbindung zu Anthropic.") from exc
    except anthropic.APIStatusError as exc:
        raise UebersetzungError(f"Anthropic meldet einen Fehler: {exc}") from exc

    if getattr(antwort, "stop_reason", None) == "refusal":
        raise UebersetzungError(
            "Das Modell hat die Übersetzung abgelehnt. Das Transkript selbst "
            "bleibt davon unberührt."
        )
    return "\n".join(
        block.text for block in antwort.content if getattr(block, "type", "") == "text"
    ).strip()


def _uebersetze_openai(text: str, von: str, nach: str, melden: ProgressFn) -> str:
    from openai import OpenAI

    client = OpenAI()
    try:
        antwort = client.chat.completions.create(
            model=OPENAI_MODELL,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": _anweisung(nach)},
                {"role": "user", "content": text},
            ],
        )
    except Exception as exc:
        raise UebersetzungError(f"OpenAI meldet einen Fehler: {exc}") from exc
    return (antwort.choices[0].message.content or "").strip()


_UEBERSETZER = {
    "argos": _uebersetze_argos,
    "anthropic": _uebersetze_anthropic,
    "openai": _uebersetze_openai,
}


# ══════════════════════════════════════════════════════════════
# HAUPT-EINSTIEG
# ══════════════════════════════════════════════════════════════
def uebersetzen(
    text: str,
    nach: str = "de",
    von: str | None = None,
    dienst: str = "auto",
    progress: ProgressFn | None = None,
) -> str:
    """
    Übersetzt einen Text.

    `von` darf None sein, wenn der Dienst die Sprache selbst erkennt;
    Argos braucht die Angabe und nimmt dann Englisch an, weil das der
    häufigste Fall ist.
    """
    melden: ProgressFn = progress or (lambda anteil, meldung: None)

    text = (text or "").strip()
    if not text:
        raise UebersetzungError("Es gibt nichts zu übersetzen – der Text ist leer.")

    ziel = sprachkuerzel(nach)
    quelle = sprachkuerzel(von) if von else None
    if quelle == ziel:
        melden(1.0, f"🌍 Der Text ist schon auf {sprachname(ziel)} – nichts zu tun.")
        return text

    gewaehlt = _uebersetzer_waehlen(dienst)
    if gewaehlt == "argos" and not quelle:
        # Argos muss wissen, woher. Englisch ist die häufigste Quelle.
        quelle = "en" if ziel != "en" else "de"
        melden(None, f"🌍 Quellsprache unbekannt – nehme {sprachname(quelle)} an.")

    uebersetzer = _UEBERSETZER[gewaehlt]
    stuecke = absatz_haeppchen(text)

    if len(stuecke) == 1:
        return uebersetzer(stuecke[0], quelle, ziel, melden)

    melden(None, f"🌍 Text ist lang – wird in {len(stuecke)} Teilen übersetzt ({gewaehlt}) …")
    teile = []
    for nummer, stueck in enumerate(stuecke, start=1):
        melden((nummer - 1) / len(stuecke), f"🌍 Teil {nummer}/{len(stuecke)} …")
        teile.append(uebersetzer(stueck, quelle, ziel, melden))
    melden(1.0, "🌍 Übersetzung fertig.")
    return "\n\n".join(teile)
