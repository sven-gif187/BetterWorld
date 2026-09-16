"""
╔══════════════════════════════════════════════════════════════╗
║  ZEITCODES – Zeitangaben lesen, rechnen und formatieren      ║
╚══════════════════════════════════════════════════════════════╝

Hier landet alles, was mit Zeit zu tun hat:

  • "1:23:45", "12:30", "90", "1h2m3s", "90s"  →  Sekunden
  • Sekunden                                    →  "00:01:30,500" (SRT)
  • YouTube-Link mit "?t=90"                    →  90.0

Kein externes Paket nötig – reine Standard-Bibliothek.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

__all__ = [
    "parse_timecode",
    "format_timestamp",
    "format_hms",
    "parse_url_time",
    "resolve_range",
]

# 1h2m3s / 90s / 90 / 2m
_HMS_RE = re.compile(
    r"^(?:(?P<h>\d+)\s*h)?"
    r"(?:(?P<m>\d+)\s*m(?!s))?"
    r"(?:(?P<s>\d+(?:[.,]\d+)?)\s*s?)?$",
    re.IGNORECASE,
)


def parse_timecode(value) -> float | None:
    """
    Wandelt eine Zeitangabe in Sekunden um.

    Erlaubt sind:
        "1:23:45"   → 5025.0     (Stunden:Minuten:Sekunden)
        "12:30"     →  750.0     (Minuten:Sekunden)
        "90"        →   90.0     (nackte Sekunden)
        "1h2m3s"    → 3723.0     (YouTube-Schreibweise)
        "1m30s"     →   90.0
        "90.5"      →   90.5     (Komma geht auch: "90,5")
        None / ""   → None       (= "nicht angegeben")

    Wirft ValueError, wenn die Eingabe keinen Sinn ergibt.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds < 0:
            raise ValueError("Zeitangabe darf nicht negativ sein.")
        return seconds

    text = str(value).strip().lower().replace(" ", "")
    if not text:
        return None
    if text.startswith("-"):
        raise ValueError("Zeitangabe darf nicht negativ sein.")

    if ":" in text:
        parts = text.split(":")
        if len(parts) > 3 or any(p == "" for p in parts):
            raise ValueError(f"Unverständliche Zeitangabe: {value!r}")
        total = 0.0
        for part in parts:
            try:
                total = total * 60 + float(part.replace(",", "."))
            except ValueError:
                raise ValueError(f"Unverständliche Zeitangabe: {value!r}") from None
        return total

    match = _HMS_RE.match(text)
    if not match or not any(match.group(g) for g in ("h", "m", "s")):
        raise ValueError(f"Unverständliche Zeitangabe: {value!r}")

    hours = float(match.group("h") or 0)
    minutes = float(match.group("m") or 0)
    seconds = float((match.group("s") or "0").replace(",", "."))
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float, sep: str = ",") -> str:
    """Sekunden → "00:01:30,500" (SRT) bzw. "00:01:30.500" (WebVTT)."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, total_ms = divmod(total_ms, 3_600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def format_hms(seconds: float) -> str:
    """Sekunden → kompakte Anzeige: "3:07" oder "1:02:03"."""
    total = max(0, int(round(float(seconds))))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_url_time(url: str) -> float | None:
    """
    Holt die Sprungmarke aus einem Link.

        https://youtu.be/abc?t=90          → 90.0
        https://youtube.com/watch?v=x&t=1h2m3s → 3723.0
        https://example.com/video#t=42     → 42.0

    Gibt None zurück, wenn der Link keine Zeit enthält.
    """
    if not url:
        return None
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return None

    candidates: list[str] = []
    query = parse_qs(parsed.query)
    for key in ("t", "start", "time_continue", "begin"):
        candidates.extend(query.get(key, []))

    fragment = parsed.fragment or ""
    if fragment:
        frag_query = parse_qs(fragment)
        for key in ("t", "start"):
            candidates.extend(frag_query.get(key, []))
        if "=" not in fragment:
            candidates.append(fragment)

    for candidate in candidates:
        try:
            value = parse_timecode(candidate)
        except ValueError:
            continue
        if value is not None:
            return value
    return None


def resolve_range(start=None, end=None, duration=None) -> tuple[float | None, float | None]:
    """
    Bringt Start / Ende / Dauer auf einen gemeinsamen Nenner.

    Rückgabe: (start_sekunden, dauer_sekunden) – beides darf None sein
    ("von Anfang an" bzw. "bis zum Schluss").

    "Ende" und "Dauer" schließen sich gegenseitig aus; ist beides gesetzt,
    gewinnt das konkretere "Ende".
    """
    start_s = parse_timecode(start)
    end_s = parse_timecode(end)
    dur_s = parse_timecode(duration)

    if end_s is not None:
        base = start_s or 0.0
        if end_s <= base:
            raise ValueError(
                f"Das Ende ({format_hms(end_s)}) liegt vor dem Start ({format_hms(base)})."
            )
        return start_s, end_s - base

    return start_s, dur_s
