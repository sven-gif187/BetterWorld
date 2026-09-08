"""
╔══════════════════════════════════════════════════════════════╗
║  ZUSAMMENFASSUNG – aus einer Stunde Text werden zehn Zeilen  ║
╚══════════════════════════════════════════════════════════════╝

Ein Transkript ist selten das, was man eigentlich wissen will.
Nach einer Stunde Besprechung interessiert: Was wurde beschlossen?
Wer macht was? Worum ging es überhaupt?

Genau dafür ist dieses Modul da. Es schickt den Text an ein
Sprachmodell und bekommt eine Zusammenfassung zurück.

  🧠 Anthropic (Claude)  – wenn ANTHROPIC_API_KEY gesetzt ist
  🤖 OpenAI              – wenn OPENAI_API_KEY gesetzt ist
                           (den hat, wer schon die Cloud-Transkription nutzt)

Beides kostet Geld pro Anfrage und schickt den Text aus dem Haus.
Ohne Schlüssel passiert nichts – die Transkription selbst läuft
weiterhin vollständig offline.

Lange Transkripte werden in Häppchen zerlegt, einzeln zusammengefasst
und die Teilergebnisse anschließend noch einmal verdichtet.
"""

from __future__ import annotations

import os
import re
from typing import Callable

__all__ = [
    "ARTEN",
    "ZusammenfassungError",
    "verfuegbare_dienste",
    "zusammenfassung_status",
    "zusammenfassen",
    "haeppchen",
    "anweisung_bauen",
]

ProgressFn = Callable[[float | None, str], None]

# Ab hier wird stückweise gearbeitet. Rund 12 000 Zeichen sind etwa
# 20 Minuten gesprochener Text – das passt bequem in eine Anfrage.
MAX_ZEICHEN = 12_000

ANTHROPIC_MODELL = "claude-opus-5"
OPENAI_MODELL = "gpt-4o-mini"

ARTEN: dict[str, str] = {
    "stichpunkte": "Die wichtigsten Punkte als übersichtliche Liste",
    "fliesstext": "Ein zusammenhängender Absatz, wie man ihn jemandem erzählen würde",
    "protokoll": "Besprechungsprotokoll: Themen, Beschlüsse, offene Fragen",
    "aufgaben": "Nur die Aufgaben: wer macht was bis wann",
    "kurz": "Drei Sätze, mehr nicht",
}


class ZusammenfassungError(RuntimeError):
    """Die Zusammenfassung konnte nicht erstellt werden."""


# ══════════════════════════════════════════════════════════════
# WELCHE DIENSTE STEHEN BEREIT?
# ══════════════════════════════════════════════════════════════
def _paket_da(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def verfuegbare_dienste() -> list[str]:
    """Dienste, die tatsächlich nutzbar sind – bester zuerst."""
    dienste = []
    if _paket_da("anthropic") and os.getenv("ANTHROPIC_API_KEY"):
        dienste.append("anthropic")
    if _paket_da("openai") and os.getenv("OPENAI_API_KEY"):
        dienste.append("openai")
    return dienste


def zusammenfassung_status() -> str:
    """Statuszeile für die Oberfläche."""
    dienste = verfuegbare_dienste()
    if dienste:
        return "✅ Zusammenfassung: " + " · ".join(dienste)
    return "⚠️ Zusammenfassung: kein API-Schlüssel hinterlegt (optional)"


def _dienst_waehlen(dienst: str) -> str:
    verfuegbar = verfuegbare_dienste()
    if dienst and dienst != "auto":
        if dienst not in verfuegbar:
            raise ZusammenfassungError(
                f"Der Dienst '{dienst}' steht nicht zur Verfügung.\n"
                f"Nutzbar wäre: {', '.join(verfuegbar) or 'nichts'}"
            )
        return dienst
    if not verfuegbar:
        raise ZusammenfassungError(
            "Für die Zusammenfassung wird ein Sprachmodell gebraucht.\n\n"
            "Variante A – Claude:\n"
            "    pip install anthropic\n"
            "    ANTHROPIC_API_KEY=sk-ant-... in die .env eintragen\n\n"
            "Variante B – OpenAI:\n"
            "    pip install openai\n"
            "    OPENAI_API_KEY=sk-... in die .env eintragen\n\n"
            "Beides kostet pro Anfrage und schickt den Text an einen\n"
            "Online-Dienst. Die Transkription selbst bleibt davon unberührt."
        )
    return verfuegbar[0]


# ══════════════════════════════════════════════════════════════
# TEXT VORBEREITEN – ohne Netz, deshalb gut testbar
# ══════════════════════════════════════════════════════════════
def haeppchen(text: str, max_zeichen: int = MAX_ZEICHEN) -> list[str]:
    """
    Zerlegt langen Text in handliche Stücke.

    Getrennt wird an Satzenden, nicht mitten im Wort – sonst fehlt dem
    Modell am Rand der Zusammenhang. Ein einzelner Satz, der länger ist
    als das erlaubte Stück (kommt bei Transkripten ohne Satzzeichen vor),
    wird notgedrungen hart geschnitten.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_zeichen:
        return [text]

    saetze = re.split(r"(?<=[.!?…])\s+", text)
    stuecke: list[str] = []
    aktuell = ""

    for satz in saetze:
        while len(satz) > max_zeichen:            # Notfall: Bandwurmsatz
            if aktuell:
                stuecke.append(aktuell.strip())
                aktuell = ""
            stuecke.append(satz[:max_zeichen])
            satz = satz[max_zeichen:]
        if not aktuell:
            aktuell = satz
        elif len(aktuell) + 1 + len(satz) <= max_zeichen:
            aktuell += " " + satz
        else:
            stuecke.append(aktuell.strip())
            aktuell = satz

    if aktuell.strip():
        stuecke.append(aktuell.strip())
    return [s for s in stuecke if s.strip()]


def anweisung_bauen(art: str = "stichpunkte", sprache: str = "Deutsch") -> str:
    """Baut die Anweisung an das Sprachmodell."""
    if art not in ARTEN:
        raise ZusammenfassungError(
            f"Unbekannte Art '{art}'. Möglich: {', '.join(ARTEN)}"
        )

    vorgaben = {
        "stichpunkte": (
            "Fasse den Text als Stichpunktliste zusammen. Jeder Punkt eine Zeile, "
            "beginnend mit '- '. Sortiere nach Wichtigkeit, nicht nach Reihenfolge."
        ),
        "fliesstext": (
            "Fasse den Text in zusammenhängenden Absätzen zusammen, so wie du es "
            "jemandem erzählen würdest, der nicht dabei war."
        ),
        "protokoll": (
            "Erstelle ein Besprechungsprotokoll mit den Überschriften "
            "'Themen', 'Beschlüsse' und 'Offene Fragen'. Lass eine Überschrift weg, "
            "wenn es dazu nichts gibt."
        ),
        "aufgaben": (
            "Liste ausschließlich die Aufgaben auf, im Format "
            "'- [Wer]: [Was] (bis [Wann])'. Ist etwas davon unklar, schreibe "
            "'unklar' statt zu raten. Gibt es keine Aufgaben, schreibe das."
        ),
        "kurz": "Fasse den Text in höchstens drei Sätzen zusammen.",
    }

    return (
        f"{vorgaben[art]}\n\n"
        f"Antworte auf {sprache}.\n\n"
        "Der Text stammt aus einer automatischen Spracherkennung und enthält "
        "deshalb Hörfehler, abgebrochene Sätze und fehlende Satzzeichen. "
        "Gib nur wieder, was tatsächlich dasteht – ergänze nichts aus eigenem "
        "Wissen. Ist eine Stelle unverständlich, lass sie weg, statt zu raten."
    )


# ══════════════════════════════════════════════════════════════
# DIE DIENSTE
# ══════════════════════════════════════════════════════════════
def _frag_anthropic(anweisung: str, text: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic()
    argumente = dict(
        model=ANTHROPIC_MODELL,
        max_tokens=max_tokens,
        system=anweisung,
        messages=[{"role": "user", "content": text}],
        # Zusammenfassen ist Fleißarbeit, kein Knobeln – niedriger Aufwand
        # liefert hier dasselbe Ergebnis für einen Bruchteil der Kosten.
        output_config={"effort": "low"},
    )

    try:
        antwort = client.messages.create(**argumente)
    except TypeError:
        # Ältere SDK-Fassungen kennen output_config noch nicht.
        argumente.pop("output_config", None)
        antwort = client.messages.create(**argumente)
    except anthropic.BadRequestError:
        argumente.pop("output_config", None)
        antwort = client.messages.create(**argumente)
    except anthropic.AuthenticationError as exc:
        raise ZusammenfassungError("Der ANTHROPIC_API_KEY wird nicht akzeptiert.") from exc
    except anthropic.RateLimitError as exc:
        raise ZusammenfassungError("Zu viele Anfragen – bitte kurz warten.") from exc
    except anthropic.APIConnectionError as exc:
        raise ZusammenfassungError("Keine Verbindung zu Anthropic.") from exc
    except anthropic.APIStatusError as exc:
        raise ZusammenfassungError(f"Anthropic meldet einen Fehler: {exc}") from exc

    if getattr(antwort, "stop_reason", None) == "refusal":
        raise ZusammenfassungError(
            "Das Modell hat die Zusammenfassung abgelehnt. "
            "Das kann bei heiklen Inhalten passieren – das Transkript selbst "
            "bleibt davon unberührt."
        )

    return "\n".join(
        block.text for block in antwort.content if getattr(block, "type", "") == "text"
    ).strip()


def _frag_openai(anweisung: str, text: str, max_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI()
    try:
        antwort = client.chat.completions.create(
            model=OPENAI_MODELL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": anweisung},
                {"role": "user", "content": text},
            ],
        )
    except Exception as exc:
        raise ZusammenfassungError(f"OpenAI meldet einen Fehler: {exc}") from exc

    return (antwort.choices[0].message.content or "").strip()


_DIENSTE = {"anthropic": _frag_anthropic, "openai": _frag_openai}


# ══════════════════════════════════════════════════════════════
# HAUPT-EINSTIEG
# ══════════════════════════════════════════════════════════════
def zusammenfassen(
    text: str,
    art: str = "stichpunkte",
    sprache: str = "Deutsch",
    dienst: str = "auto",
    progress: ProgressFn | None = None,
) -> str:
    """
    Fasst ein Transkript zusammen.

    Lange Texte werden in Häppchen zerlegt, einzeln zusammengefasst und
    die Teilergebnisse danach noch einmal verdichtet – sonst passt eine
    zweistündige Aufnahme in keine einzelne Anfrage.
    """
    melden: ProgressFn = progress or (lambda anteil, meldung: None)

    text = (text or "").strip()
    if not text:
        raise ZusammenfassungError("Es gibt nichts zusammenzufassen – der Text ist leer.")

    gewaehlt = _dienst_waehlen(dienst)
    anweisung = anweisung_bauen(art, sprache)
    frage = _DIENSTE[gewaehlt]

    stuecke = haeppchen(text)
    if len(stuecke) == 1:
        melden(None, f"📝 Zusammenfassung wird erstellt ({gewaehlt}) …")
        return frage(anweisung, stuecke[0], 4096)

    melden(None, f"📝 Text ist lang – wird in {len(stuecke)} Teilen bearbeitet ({gewaehlt}) …")
    teilergebnisse = []
    for nummer, stueck in enumerate(stuecke, start=1):
        melden((nummer - 1) / (len(stuecke) + 1), f"📝 Teil {nummer}/{len(stuecke)} …")
        teilergebnisse.append(
            frage(anweisung_bauen("stichpunkte", sprache), stueck, 2048)
        )

    melden(len(stuecke) / (len(stuecke) + 1), "📝 Teile werden zusammengeführt …")
    gesammelt = "\n\n".join(
        f"--- Abschnitt {i} ---\n{teil}" for i, teil in enumerate(teilergebnisse, start=1)
    )
    schluss = frage(
        anweisung
        + "\n\nDu bekommst die Zusammenfassungen einzelner Abschnitte einer "
          "längeren Aufnahme. Führe sie zu einem Ganzen zusammen, ohne "
          "Wiederholungen und ohne die Abschnittsnummern zu erwähnen.",
        gesammelt,
        4096,
    )
    melden(1.0, "📝 Zusammenfassung fertig.")
    return schluss
