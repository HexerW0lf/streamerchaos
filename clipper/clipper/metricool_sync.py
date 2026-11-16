"""Kanalzahlen über Claude (Metricool-Connector) holen und in kanal/zahlen.json speichern.

Claude ruft nur das Lese-Tool getAnalyticsDataByMetrics auf; gerechnet wird hier in Python.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import PROJEKT

BRAND_ID = "8154528"
TOOL = "mcp__claude_ai_Metricool_Social_Media_Management__getAnalyticsDataByMetrics"
KANAL = PROJEKT / "kanal"

# name: (Metrik, Tage zurück)
ABFRAGEN = {
    "abos": ("YTEV01", 90),        # YouTube-Abos (letzter Wert)
    "minuten": ("YTVV07", 365),    # Wiedergabeminuten aller Videos, 365 Tage (inkl. Shorts -> Näherung)
    "aufrufe90": ("YTEV02", 90),   # YouTube-Aufrufe 90 Tage (alle Videos -> Näherung für Shorts)
    "tt_follower": ("TKEV07", 30),  # TikTok-Follower (letzter Wert)
    "tt30": ("TKEV12", 30),        # TikTok-Videoaufrufe 30 Tage
}


def _prompt(heute: dt.date) -> str:
    zeilen = []
    for name, (metrik, tage) in ABFRAGEN.items():
        von = heute - dt.timedelta(days=tage)
        zeilen.append(f'- "{name}": brandId "{BRAND_ID}", metrics ["{metrik}"], '
                      f'from "{von.isoformat()}T00:00:00+01:00", to "{heute.isoformat()}T23:59:59+01:00"')
    return (
        "Rufe das Metricool-Tool getAnalyticsDataByMetrics genau 5-mal auf (warte, falls der Server noch verbindet):\n"
        + "\n".join(zeilen)
        + '\n\nAntworte NUR mit einem JSON-Objekt ohne Erklärung: {"abos": <rows>, "minuten": <rows>, '
          '"aufrufe90": <rows>, "tt_follower": <rows>, "tt30": <rows>}, wobei <rows> jeweils exakt das Feld '
          '"rows" aus der Tool-Antwort ist (oder null bei Fehler).'
    )


def _werte(rows) -> list[float]:
    raus = []
    for r in rows or []:
        try:
            raus.append(float(r[0]))
        except (TypeError, ValueError, IndexError):
            pass
    return raus


def hole(modell: str = "haiku") -> dict:
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude CLI nicht gefunden")
    heute = dt.date.today()
    r = subprocess.run(
        [claude, "-p", "--model", modell, "--allowedTools", TOOL],
        input=_prompt(heute), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, cwd=str(Path.home()),
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:])
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if not m:
        raise RuntimeError(f"keine Daten: {r.stdout.strip()[-300:]}")
    roh = json.loads(m.group(0))
    eintrag: dict = {"datum": heute.isoformat(), "quelle": "metricool"}
    if roh.get("abos"):
        eintrag["abos"] = _werte(roh["abos"])[-1] if _werte(roh["abos"]) else 0.0
    if roh.get("minuten") is not None:
        eintrag["stunden"] = round(sum(_werte(roh["minuten"])) / 60, 1)
    if roh.get("aufrufe90") is not None:
        eintrag["shorts90"] = sum(_werte(roh["aufrufe90"]))
    if roh.get("tt_follower"):
        eintrag["tt_follower"] = _werte(roh["tt_follower"])[-1] if _werte(roh["tt_follower"]) else 0.0
    if roh.get("tt30") is not None:
        eintrag["tt30"] = sum(_werte(roh["tt30"]))
    return eintrag


def speichere(eintrag: dict) -> list[dict]:
    KANAL.mkdir(exist_ok=True)
    f = KANAL / "zahlen.json"
    zahlen = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else []
    zahlen = [z for z in zahlen if z.get("datum") != eintrag["datum"]] + [eintrag]
    zahlen.sort(key=lambda z: z["datum"])
    f.write_text(json.dumps(zahlen, ensure_ascii=False, indent=1), encoding="utf-8")
    return zahlen


def main() -> None:
    e = hole()
    speichere(e)
    print(json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()
