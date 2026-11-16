"""Claude wählt die besten Momente und schreibt Hook, Titel, Beschreibung."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from .analyse import Kandidat
from .config import Profil
from .transkript import Wort, als_text


@dataclass
class Clip:
    start: float
    ende: float
    hook: str
    titel_youtube: str
    titel_tiktok: str
    beschreibung: str
    hashtags: list[str] = field(default_factory=list)
    grund: str = ""
    bewertung: int = 0


def _prompt(kandidaten: list[Kandidat], texte: list[str], profil: Profil,
            max_clips: int, kanal: str, titel: str) -> str:
    bloecke = []
    for i, (k, t) in enumerate(zip(kandidaten, texte), 1):
        bloecke.append(
            f"### Kandidat {i}\nFenster {k.start:.1f}–{k.ende:.1f} s, lautester Punkt {k.zeit:.1f} s, "
            f"Lautstärke-Ausschlag {k.punkte:.1f} dB\nTranskript (Zahlen in [] = Sekunden):\n{t or '(kein Text)'}"
        )
    tiktok = (" Für TikTok-Geld müssen Clips länger als 60 s sein; wähle daher wenn möglich 61–"
              f"{profil.clip_max} s." if profil.tiktok_ueber_60 else "")
    return f"""Du bist Clip-Editor für einen deutschen Gaming-Shorts-Kanal ({profil.spiel or 'Gaming'}).
Quelle: Stream von {kanal or 'unbekannt'} – "{titel}".

Aus einem langen Stream wurden laute Momente vorausgewählt. Wähle die besten {max_clips} (oder weniger, wenn
nicht genug gut sind) und lege für jeden Start und Ende fest.

Regeln:
- Länge {profil.clip_min}–{profil.clip_max} s.{tiktok}
- Start und Ende in absoluten Sekunden, innerhalb des Kandidaten-Fensters (±10 s erlaubt).
- Start kurz vor dem Aufbau, damit man versteht, was passiert. Ende direkt nach der Pointe/Reaktion, nicht mitten im Satz.
- Ehrlich bleiben: Prüfe am Stream-Titel und Transkript, welches Spiel es wirklich ist. Ist es nicht
  {profil.spiel or 'das Profil-Spiel'}, dann Titel/Hashtags NICHT als {profil.spiel or 'dieses Spiel'} ausgeben, sondern das echte Spiel nennen.
- Nur Momente, die ohne Vorwissen funktionieren. Langweiliges (Menüs, Warten, Werbung, Sponsoren) weglassen.
- hook: Text, der in den ersten 3 Sekunden oben eingeblendet wird. Max. 8 Wörter, neugierig machend, nichts verraten, keine Lügen.
- titel_youtube: max. 70 Zeichen, inkl. 1–2 passender Hashtags am Ende.
- titel_tiktok: max. 100 Zeichen.
- beschreibung: 1–2 Sätze, was passiert (ohne Pointe vorwegzunehmen).
- hashtags: 4–6, aus diesen wählen/ergänzen: {' '.join(profil.hashtags)}
- bewertung: 1–10, wie viral der Moment wohl ist.
Beispiele für Hooks: {' | '.join(profil.hook_beispiele)}
Profil-Hinweise: {profil.hinweise.strip()}

{chr(10).join(bloecke)}

Antworte NUR mit JSON, ohne Erklärung, in genau diesem Format:
{{"clips": [{{"start": 123.4, "ende": 190.2, "hook": "...", "titel_youtube": "...", "titel_tiktok": "...",
"beschreibung": "...", "hashtags": ["#..."], "grund": "kurz warum", "bewertung": 8}}]}}
"""


def _json_aus_text(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("kein JSON in Antwort")
    return json.loads(m.group(0))


def frage_claude(prompt: str, modell: str) -> dict:
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude CLI nicht gefunden")
    r = subprocess.run(
        [claude, "-p", "--model", modell, "--output-format", "json"],
        input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude Fehler: {(r.stderr or r.stdout).strip()[-400:]}")
    huelle = json.loads(r.stdout)
    return _json_aus_text(huelle.get("result", ""))


def _rueckfall(kandidaten: list[Kandidat], profil: Profil, max_clips: int) -> list[Clip]:
    beste = sorted(kandidaten, key=lambda k: -k.punkte)[:max_clips]
    laenge = 62 if profil.tiktok_ueber_60 else profil.clip_min + 10
    raus = []
    for k in sorted(beste, key=lambda k: k.zeit):
        s = max(k.start, k.zeit - laenge + 12)
        raus.append(Clip(s, s + laenge, profil.hook_beispiele[0] if profil.hook_beispiele else "",
                         "Krasser Moment", "Krasser Moment", "", profil.hashtags[:5],
                         "Rückfall: lautester Moment", 5))
    return raus


def baue_prompt(kandidaten: list[Kandidat], woerter: list[list[Wort]], profil: Profil, max_clips: int,
                kanal: str, titel: str) -> str:
    texte = [als_text(w, k.start, k.ende) for k, w in zip(kandidaten, woerter)]
    return _prompt(kandidaten, texte, profil, max_clips, kanal, titel)


def waehle(kandidaten: list[Kandidat], woerter: list[list[Wort]], profil: Profil, max_clips: int,
           kanal: str, titel: str, modell: str = "sonnet") -> tuple[list[Clip], str]:
    prompt = baue_prompt(kandidaten, woerter, profil, max_clips, kanal, titel)
    try:
        daten = frage_claude(prompt, modell)
        quelle = f"claude ({modell})"
    except Exception as e:  # noqa: BLE001 - jeder Fehler -> Rückfall
        print(f"[clipper] Claude-Auswahl fehlgeschlagen ({e}); nehme lauteste Momente.")
        return _rueckfall(kandidaten, profil, max_clips), "rückfall"
    clips = clips_aus_json(daten, profil, max_clips)
    if not clips:
        return _rueckfall(kandidaten, profil, max_clips), "rückfall"
    return clips, quelle


def clips_aus_json(daten: dict, profil: Profil, max_clips: int) -> list[Clip]:
    clips: list[Clip] = []
    for c in daten.get("clips", [])[:max_clips]:
        try:
            s, e = float(c["start"]), float(c["ende"])
        except (KeyError, TypeError, ValueError):
            continue
        if e - s < 8:
            continue
        e = min(e, s + profil.clip_max + 10)
        clips.append(Clip(
            start=s, ende=e, hook=str(c.get("hook", ""))[:80],
            titel_youtube=str(c.get("titel_youtube", "")), titel_tiktok=str(c.get("titel_tiktok", "")),
            beschreibung=str(c.get("beschreibung", "")), hashtags=[str(h) for h in c.get("hashtags", [])],
            grund=str(c.get("grund", "")), bewertung=int(c.get("bewertung", 0) or 0),
        ))
    return sorted(clips, key=lambda c: -c.bewertung)
