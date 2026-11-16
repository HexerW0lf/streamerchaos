"""Modus 1: fertiges VOD / Video -> Clips."""

from __future__ import annotations

import datetime as dt
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from . import analyse, quelle, render, transkript
from .auswahl import Clip, waehle
from .config import PROJEKT, Profil


def zeit(text: str | None) -> float | None:
    if text is None:
        return None
    teile = [float(x) for x in str(text).split(":")]
    s = 0.0
    for t in teile:
        s = s * 60 + t
    return s


def hms(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def slug(text: str, laenge: int = 40) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:laenge] or "clip"


def post_zeiten(anzahl: int, ab: dt.date) -> list[str]:
    slots = []
    tag = ab
    while len(slots) < anzahl:
        for uhr in ("12:00", "18:00"):
            wt = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[tag.weekday()]
            slots.append(f"{wt} {tag.strftime('%d.%m.')} {uhr}")
        tag += dt.timedelta(days=1)
    return slots[:anzahl]


def info_md(clip: Clip, info: quelle.Info, profil: Profil, nr: int, post: str) -> str:
    tags = " ".join(dict.fromkeys(clip.hashtags or profil.hashtags[:5]))

    def ohne_doppelte(text: str) -> str:
        # Hashtags im Titel nicht noch einmal anhängen
        return " ".join(t for t in tags.split() if t.lower() not in text.lower())
    quelle_txt = f"Clip aus dem Stream von {info.kanal}" if info.kanal else "Clip"
    if info.url:
        quelle_txt += f": {info.url}?t={int(clip.start)}s" if "twitch.tv" in info.url else f": {info.url}"
    return f"""# Clip {nr:02d} – Bewertung {clip.bewertung}/10

Quelle: {hms(clip.start)} – {hms(clip.ende)} ({clip.ende - clip.start:.0f} s)
Warum: {clip.grund}
Posten: {post}

## YouTube Shorts
**Titel:** {clip.titel_youtube}

**Beschreibung:**
{clip.beschreibung}

{quelle_txt}
{tags}

## TikTok
**Text:** {clip.titel_tiktok} {ohne_doppelte(clip.titel_tiktok)}
{"Länge über 60 s: zählt für Creator Rewards." if clip.ende - clip.start > 60 else "Unter 60 s: zählt NICHT für TikTok Creator Rewards."}

## Vor dem Posten
- [ ] Erlaubnis des Streamers vorhanden ({info.kanal or 'Streamer'})
- [ ] Eigener Beitrag drin? (Voice-over, Kommentar oder Einordnung – sonst Risiko "wiederverwendete Inhalte")
- [ ] Clip angeschaut, Untertitel ok
"""


def lauf(quelle_arg: str, profil: Profil, max_clips: int, start: str | None, ende: str | None,
         modell: str, layout: str | None, nur_analyse: bool = False) -> Path:
    info = quelle.hole_info(quelle_arg)
    s0, e0 = zeit(start), zeit(ende)
    print(f"[clipper] {info.titel} ({hms(info.dauer)}) von {info.kanal or '?'}")

    arbeit = PROJEKT / "arbeit" / slug(f"{info.kanal}-{info.titel}", 60)
    audio = quelle.lade_audio(info, arbeit / f"ton_{int(s0 or 0)}_{int(e0 or 0)}", s0, e0)
    offset = s0 or 0.0
    print("[clipper] Lautstärke auswerten ...")
    db = analyse.lautstaerke(audio)
    kand = analyse.finde_kandidaten(db, anzahl=max(10, max_clips * 3), offset=offset)
    print(f"[clipper] {len(kand)} Kandidaten. Transkribiere ...")

    def tr(k: analyse.Kandidat) -> list[transkript.Wort]:
        return transkript.transkribiere(audio, k.start, k.ende, offset, profil.sprache, arbeit / "transkript")

    with ThreadPoolExecutor(max_workers=4) as pool:
        woerter = list(pool.map(tr, kand))

    (arbeit / "kandidaten.json").write_text(json.dumps(
        [asdict(k) | {"text": transkript.als_text(w, k.start, k.ende)} for k, w in zip(kand, woerter)],
        ensure_ascii=False, indent=1), encoding="utf-8")
    if nur_analyse:
        print(f"[clipper] Nur Analyse: {arbeit / 'kandidaten.json'}")
        return arbeit

    print(f"[clipper] Auswahl mit Claude ({modell}) ...")
    clips, wer = waehle(kand, woerter, profil, max_clips, info.kanal, info.titel, modell)
    if info.dauer:
        for c in clips:
            c.start = max(0.0, c.start)
            c.ende = min(info.dauer, c.ende)
    print(f"[clipper] {len(clips)} Clips gewählt ({wer}). Rendere ...")

    heute = dt.date.today()
    ausgabe = PROJEKT / "ausgabe" / f"{heute.isoformat()}_{slug(info.kanal or info.titel, 30)}"
    ausgabe.mkdir(parents=True, exist_ok=True)
    zeiten = post_zeiten(len(clips), heute + dt.timedelta(days=1))
    uebersicht = [f"# Clips: {info.titel}\n", f"Quelle: {info.url or info.quelle}  ",
                  f"Profil: {profil.name}, Auswahl: {wer}\n",
                  "| # | Bewertung | Länge | Posten | Titel |", "|---|---|---|---|---|"]
    for nr, c in enumerate(clips, 1):
        ordner = ausgabe / f"{nr:02d}_{slug(c.titel_youtube or c.hook)}"
        print(f"[clipper] Clip {nr}/{len(clips)}: {hms(c.start)}–{hms(c.ende)} {c.titel_youtube}")
        w = transkript.transkribiere(audio, c.start, c.ende, offset, profil.sprache, arbeit / "transkript")
        video = quelle.lade_abschnitt(info, c.start, c.ende, arbeit / "abschnitte" / f"{int(c.start * 10)}_{int(c.ende * 10)}.mp4")
        render.rendere(video, w, c.start, c.ende, c.hook, ordner, layout or profil.layout, profil.facecam)
        (ordner / "info.md").write_text(info_md(c, info, profil, nr, zeiten[nr - 1]), encoding="utf-8")
        (ordner / "clip.json").write_text(json.dumps(asdict(c), ensure_ascii=False, indent=1), encoding="utf-8")
        uebersicht.append(f"| {nr} | {c.bewertung} | {c.ende - c.start:.0f} s | {zeiten[nr - 1]} | {c.titel_youtube} |")
    (ausgabe / "übersicht.md").write_text("\n".join(uebersicht) + "\n", encoding="utf-8")
    print(f"[clipper] Fertig: {ausgabe}")
    return ausgabe
