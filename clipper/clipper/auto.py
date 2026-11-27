"""Automatik für den Betrieb ohne Mensch (Claude-Cloud oder lokal).

Ablauf pro Lauf:
  1. `auto neu`          -> neue, fertige VODs der Watchlist finden (laufende Streams werden übersprungen)
  2. `auto analyse ID`   -> Ton laden, Kandidaten + Transkript, Auswahl-Prompt schreiben
  3. (Claude liest arbeit/auto/ID/auswahl_prompt.md und schreibt arbeit/auto/ID/auswahl.json)
  4. `auto render ID`    -> Clips rendern, nach veroeffentlichen/ legen, posts.json schreiben
  5. `auto erledigt ID`  -> VOD als verarbeitet merken

Jeder Schritt dauert wenige Minuten, damit er in eine Cloud-Sitzung passt.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from . import analyse, quelle, render, transkript
from .auswahl import clips_aus_json, baue_prompt
from .config import PROJEKT, lade_profil
from .vod import slug

WATCHLIST = PROJEKT / "watchlist.toml"
STATUS = PROJEKT / "kanal" / "auto_status.json"
ARBEIT = PROJEKT / "arbeit" / "auto"
VEROEFF = PROJEKT / "veroeffentlichen"

# Feste Post-Zeiten (Nutzer-Wunsch 27.11.2026): höchstens 3 pro Tag, mindestens 2 h Abstand, 12–23 Uhr.
# YouTube über Buffer: höchstens 2 Posts pro Tag. Überschreibbar in cloud.toml.
POST_UHRZEITEN_TIKTOK = ("13:00", "17:00", "21:00")
POST_UHRZEITEN_YOUTUBE = ("13:00", "19:00")
MIN_VORLAUF = dt.timedelta(minutes=60)  # Zeit für Upload und Buffer
AUTO_POST_AB = 6  # ab dieser Bewertung fest geplant, darunter Entwurf
TEIL_MAX = 4 * 3600  # Sekunden pro Analyse-Stück
YT_MAX = 58  # Sekunden; YouTube blockt Shorts > 60 s mit Copyright-Anspruch

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Berlin")
except Exception:  # pragma: no cover
    TZ = None


def jetzt() -> dt.datetime:
    """Ortszeit Berlin (die Cloud läuft in UTC)."""
    return dt.datetime.now(TZ).replace(tzinfo=None) if TZ else dt.datetime.now()


def _cloud() -> dict:
    f = PROJEKT / "cloud.toml"
    return tomllib.loads(f.read_text(encoding="utf-8-sig")) if f.is_file() else {}


def gta_woche(tag: dt.date | None = None) -> bool:
    """Sonderphase zum GTA-6-Release (Zeitraum in cloud.toml)."""
    c = _cloud()
    if not c.get("gta_woche_start"):
        return False
    tag = tag or jetzt().date()
    return dt.date.fromisoformat(c["gta_woche_start"]) <= tag <= dt.date.fromisoformat(c["gta_woche_ende"])


def ist_gta(titel: str) -> bool:
    t = (titel or "").lower()
    return "gta" in t or "grand theft auto" in t


def _yt(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([shutil.which("yt-dlp") or "yt-dlp", "--no-warnings", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def lade_status() -> dict:
    if STATUS.is_file():
        return json.loads(STATUS.read_text(encoding="utf-8"))
    return {"erledigt": {}, "offen": {}}


def speichere_status(s: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def lade_watchlist() -> list[dict]:
    if not WATCHLIST.is_file():
        return []
    woche = gta_woche()
    return [k for k in tomllib.loads(WATCHLIST.read_text(encoding="utf-8-sig")).get("kanal", [])
            if k.get("aktiv", True) and (woche or not k.get("nur_gta_woche"))]


def ist_live(name: str) -> bool:
    r = _yt(["--skip-download", "--print", "is_live", f"https://www.twitch.tv/{name}"])
    return r.returncode == 0 and "True" in r.stdout


def neue_vods(max_pro_kanal: int = 1, max_alter_tage: int = 3) -> list[dict]:
    """Neue VODs der Watchlist. In der GTA-Woche auch laufende Streams (in Teilen), GTA zuerst.

    Job-ID = VOD-ID, oder `VOD-ID-STARTSEKUNDE` für Teilstücke eines (noch laufenden) Streams.
    """
    status = lade_status()
    # Die Cloud vergisst arbeit/ zwischen Läufen: offene Jobs ohne Arbeitsordner neu einreihen
    tot = [i for i in status["offen"] if not (ARBEIT / i).is_dir()]
    if tot:
        for i in tot:
            status["offen"].pop(i)
        speichere_status(status)
        print(f"[auto] {len(tot)} offene Jobs ohne Arbeitsordner neu eingereiht: {', '.join(tot)}")
    teile = status.get("teile", {})
    offen_vods = {str(o.get("vod", i.split("-")[0])) for i, o in status["offen"].items()}
    woche = gta_woche()
    raus = []
    for k in lade_watchlist():
        name = k["twitch"]
        r = _yt(["--flat-playlist", "--playlist-end", "3", "-J",
                 f"https://www.twitch.tv/{name}/videos?filter=archives&sort=time"])
        if r.returncode != 0:
            print(f"[auto] {name}: Liste nicht lesbar: {r.stderr.strip()[-200:]}")
            continue
        eintraege = json.loads(r.stdout).get("entries") or []
        live = ist_live(name)
        gefunden = 0
        for i, e in enumerate(eintraege):
            vid = str(e.get("id", "")).lstrip("v")
            if not vid or vid in status["erledigt"] or vid in offen_vods:
                continue
            titel = e.get("title", "") or ""
            gta = ist_gta(titel)
            if k.get("nur_gta") and not gta:
                continue
            laeuft = i == 0 and live
            if laeuft and not woche:  # aktuelles VOD wächst noch
                continue
            ts = e.get("timestamp")
            if ts and dt.datetime.now().timestamp() - ts > max_alter_tage * 86400:
                continue
            dauer = float(e.get("duration") or 0)
            bis = float(teile.get(vid, 0))
            if dauer - bis < (45 * 60 if laeuft else 10 * 60 if bis else 30 * 60):
                continue
            ende = dauer if laeuft else k.get("ende")
            teil = laeuft
            if dauer - bis > TEIL_MAX:  # sehr lange Streams in Stücken (Download passt sonst nicht ins Zeitlimit)
                ende, teil = bis + TEIL_MAX, True
            profil = k.get("profil", "standard")
            if woche and gta:
                profil = "gta6_en" if k.get("sprache") == "en" else "gta6"
            raus.append({"id": f"{vid}-{int(bis)}" if (teil or bis) else vid, "vod": vid,
                         "kanal": name, "titel": titel, "dauer": dauer, "profil": profil,
                         "max_clips": int(k.get("max_clips", 4)),
                         "min_bewertung": int(k.get("min_bewertung", 0)),
                         "sprache": k.get("sprache", "de"),
                         "start": bis or k.get("start"), "ende": ende,
                         "teil": teil, "gta": gta})
            gefunden += 1
            if gefunden >= max_pro_kanal:
                break
    # Deutsch vor Englisch, GTA vor Rest, längere Streams zuerst
    raus.sort(key=lambda v: (v["sprache"] != "de", not v["gta"], -(v["dauer"] or 0)))
    return raus


def analysiere(vod: dict) -> Path:
    ordner = ARBEIT / vod["id"]
    ordner.mkdir(parents=True, exist_ok=True)
    profil = lade_profil(vod.get("profil", "standard"))
    info = quelle.hole_info(f"https://www.twitch.tv/videos/{vod.get('vod', vod['id'])}")
    start = float(vod.get("start") or 0)
    ende = vod.get("ende")
    audio = quelle.lade_audio(info, ordner / "ton", start or None, float(ende) if ende else None)
    db = analyse.lautstaerke(audio)
    anzahl = max(10, vod["max_clips"] * 3)
    kand = analyse.finde_kandidaten(db, anzahl=anzahl, offset=start)
    with ThreadPoolExecutor(max_workers=4) as pool:
        woerter = list(pool.map(
            lambda k: transkript.transkribiere(audio, k.start, k.ende, start, profil.sprache, ordner / "transkript"),
            kand))
    prompt = baue_prompt(kand, woerter, profil, vod["max_clips"], info.kanal, info.titel)
    (ordner / "auswahl_prompt.md").write_text(prompt, encoding="utf-8")
    (ordner / "meta.json").write_text(json.dumps(vod | {"kanal_name": info.kanal, "url": info.url,
                                                        "dauer": info.dauer}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    s = lade_status()
    s["offen"][vod["id"]] = {"seit": jetzt().isoformat(timespec="minutes"), "schritt": "auswahl",
                             "vod": vod.get("vod", vod["id"])}
    speichere_status(s)
    return ordner / "auswahl_prompt.md"


def _post_zeiten(anzahl: int, belegt: set[str], slots: tuple[str, ...]) -> list[str]:
    """Nächste freie feste Slots. Nicht vor jetzt + MIN_VORLAUF und nicht während einer Pause
    (`pause_bis` in cloud.toml, einschließlich dieses Tages)."""
    c = _cloud()
    slots = tuple(slots)
    start = jetzt() + MIN_VORLAUF
    if c.get("pause_bis"):
        nach_pause = dt.datetime.combine(dt.date.fromisoformat(c["pause_bis"]) + dt.timedelta(days=1), dt.time())
        start = max(start, nach_pause)
    raus: list[str] = []
    tag = start.date()
    while len(raus) < anzahl:
        for hhmm in slots:
            z = dt.datetime.combine(tag, dt.time.fromisoformat(hhmm))
            s_ = z.isoformat(timespec="seconds")
            if z >= start and s_ not in belegt and len(raus) < anzahl:
                raus.append(s_)
                belegt.add(s_)
        tag += dt.timedelta(days=1)
    return raus


def _belegt(feld: str) -> set[str]:
    """Schon vergebene Post-Zeiten (nur fest geplante Clips, keine Entwürfe/Fehler)."""
    raus = set()
    for p in alle_posts():
        if p.get("status") in ("entwurf", "fehler") or int(p.get("bewertung") or 0) < AUTO_POST_AB:
            continue
        z = p.get(feld) or p.get("zeit")
        if z:
            raus.add(z)
    return raus


def rendere(vid: str) -> Path:
    ordner = ARBEIT / vid
    meta = json.loads((ordner / "meta.json").read_text(encoding="utf-8"))
    profil = lade_profil(meta.get("profil", "standard"))
    auswahl = json.loads((ordner / "auswahl.json").read_text(encoding="utf-8"))
    clips = [c for c in clips_aus_json(auswahl, profil, meta["max_clips"])
             if c.bewertung >= int(meta.get("min_bewertung") or 0)]
    info = quelle.Info(meta["url"], meta.get("titel", ""), meta.get("kanal_name", ""), float(meta.get("dauer") or 0),
                       meta["url"])
    audio = ordner / "ton" / "audio.m4a"
    audio_start = float(meta.get("start") or 0)
    ziel = VEROEFF / vid
    ziel.mkdir(parents=True, exist_ok=True)
    c_cfg = _cloud()
    geplant = [c for c in clips if c.bewertung >= AUTO_POST_AB]
    zeiten_tt = iter(_post_zeiten(len(geplant), _belegt("zeit"),
                                  c_cfg.get("post_uhrzeiten_tiktok", POST_UHRZEITEN_TIKTOK)))
    zeiten_yt = iter(_post_zeiten(len(geplant), _belegt("zeit_youtube"),
                                  c_cfg.get("post_uhrzeiten_youtube", POST_UHRZEITEN_YOUTUBE)))
    entwurf_zeit = jetzt().replace(second=0, microsecond=0).isoformat(timespec="seconds")
    posts = []
    for nr, c in enumerate(clips, 1):
        if info.dauer:
            c.ende = min(c.ende, info.dauer)
        w = transkript.transkribiere(audio, c.start, c.ende, audio_start, profil.sprache, ordner / "transkript")
        roh = quelle.lade_abschnitt(info, c.start, c.ende, ordner / "abschnitte" / f"{int(c.start)}_{int(c.ende)}.mp4")
        tmp = ordner / f"render_{nr:02d}"
        render.rendere(roh, w, c.start, c.ende, c.hook, tmp, profil.layout, profil.facecam)
        datei = ziel / f"{nr:02d}_{slug(c.titel_youtube or c.hook, 30)}.mp4"
        shutil.move(str(tmp / "clip.mp4"), datei)
        shutil.rmtree(tmp, ignore_errors=True)
        # YouTube sperrt Shorts über 60 s mit Urheberrechts-Anspruch weltweit (Content ID, z. B. ContentView).
        # Deshalb eigene YouTube-Fassung mit max. YT_MAX s: Ende (Pointe) bleibt, Anfang wird gekürzt.
        datei_yt = datei
        if c.ende - c.start > YT_MAX:
            yt_start = c.ende - YT_MAX
            tmp = ordner / f"render_{nr:02d}_yt"
            render.rendere(roh, w, yt_start, c.ende, c.hook, tmp, profil.layout, profil.facecam,
                           quelle_beginnt_bei=c.start)
            datei_yt = datei.with_name(datei.stem + "_yt.mp4")
            shutil.move(str(tmp / "clip.mp4"), datei_yt)
            shutil.rmtree(tmp, ignore_errors=True)
        tags = list(dict.fromkeys(c.hashtags or profil.hashtags[:5]))
        quelle_txt = f"🎥 Original-Stream: {info.url}?t={int(c.start)}s\n👤 Streamer: {info.kanal}"
        posts.append({
            "datei": datei.relative_to(PROJEKT).as_posix(),
            "datei_youtube": datei_yt.relative_to(PROJEKT).as_posix(),
            "zeit": next(zeiten_tt) if c.bewertung >= AUTO_POST_AB else entwurf_zeit,  # TikTok
            "zeit_youtube": next(zeiten_yt) if c.bewertung >= AUTO_POST_AB else entwurf_zeit,
            "titel_youtube": c.titel_youtube[:100],
            "titel_tiktok": c.titel_tiktok,
            "text_youtube": f"{c.beschreibung}\n\n{quelle_txt}\n\n{' '.join(tags)}",
            "text_tiktok": f"{c.titel_tiktok} {' '.join(t for t in tags if t.lower() not in c.titel_tiktok.lower())}".strip(),
            "hashtags": tags, "hook": c.hook, "dauer": round(c.ende - c.start),
            "bewertung": c.bewertung, "streamer": info.kanal, "vod": meta.get("vod", vid),
            "sprache": meta.get("sprache", "de"),
            "status": "neu",
        })
    (ziel / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
    s = lade_status()
    if vid in s["offen"]:
        s["offen"][vid]["schritt"] = "posten"
    speichere_status(s)
    return ziel / "posts.json"


def alle_posts() -> list[dict]:
    raus = []
    for f in sorted(VEROEFF.glob("*/posts.json")):
        raus.extend(json.loads(f.read_text(encoding="utf-8")))
    return raus


def markiere_post(datei: str, status: str, info: str = "") -> bool:
    for f in VEROEFF.glob("*/posts.json"):
        posts = json.loads(f.read_text(encoding="utf-8"))
        for p in posts:
            if p["datei"] == datei:
                p["status"] = status
                if info:
                    p["info"] = info
                f.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
                return True
    return False


def erledigt(vid: str) -> None:
    """Job abschließen. Teilstück eines laufenden Streams: nur merken, bis wohin analysiert ist."""
    meta_f = ARBEIT / vid / "meta.json"
    meta = json.loads(meta_f.read_text(encoding="utf-8")) if meta_f.is_file() else {}
    s = lade_status()
    s["offen"].pop(vid, None)
    vod = str(meta.get("vod") or vid.split("-")[0])
    if meta.get("teil"):
        s.setdefault("teile", {})[vod] = float(meta.get("ende") or 0)
    else:
        s["erledigt"][vod] = jetzt().date().isoformat()
        s.get("teile", {}).pop(vod, None)
    speichere_status(s)
    shutil.rmtree(ARBEIT / vid, ignore_errors=True)


def aufraeumen() -> int:
    """Clips löschen, deren Posts erledigt sind.

    Buffer lädt das Video erst zur Veröffentlichung von der URL. Darum bleibt ein Clip im
    clips-Branch, bis sein Post-Zeitpunkt mindestens 1 Tag vorbei ist. Entwürfe nach 7 Tagen,
    Fehler-Posts nach 3 Tagen.
    """
    grenze = jetzt() - dt.timedelta(days=1)
    weg = 0
    for f in VEROEFF.glob("*/posts.json"):
        posts = json.loads(f.read_text(encoding="utf-8"))

        def fertig(p: dict) -> bool:
            zeiten = [dt.datetime.fromisoformat(z) for z in (p.get("zeit"), p.get("zeit_youtube")) if z]
            zeit = max(zeiten) if zeiten else grenze  # spätester Post (YouTube oft später als TikTok)
            if p["status"] == "geplant":
                return zeit < grenze
            if p["status"] == "entwurf":  # Nutzer plant Entwürfe evtl. später selbst ein
                return zeit < grenze - dt.timedelta(days=6)
            if p["status"] == "fehler":
                return zeit < grenze - dt.timedelta(days=2)
            return False

        if posts and all(fertig(p) for p in posts):
            shutil.rmtree(f.parent)
            weg += 1
    return weg


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "neu":
        vods = neue_vods()
        print(json.dumps(vods, ensure_ascii=False, indent=1))
        return 0
    befehl, *rest = argv
    if befehl == "gta":
        print("GTA-Woche aktiv" if gta_woche() else "keine GTA-Woche")
        return 0
    if befehl == "analyse":
        vods = {v["id"]: v for v in neue_vods(max_pro_kanal=3, max_alter_tage=30)}
        vod = vods.get(rest[0])
        if not vod:
            print(f"[auto] VOD {rest[0]} nicht in der Watchlist gefunden oder schon erledigt")
            return 1
        print(analysiere(vod).relative_to(PROJEKT).as_posix())
    elif befehl == "render":
        print(rendere(rest[0]).relative_to(PROJEKT).as_posix())
    elif befehl == "erledigt":
        erledigt(rest[0])
    elif befehl == "posts":
        from .hosting import raw_url
        offen = [p | {"url": raw_url(p["datei"]), "url_youtube": raw_url(p.get("datei_youtube") or p["datei"])}
                 for p in alle_posts() if p["status"] == "neu"]
        print(json.dumps(offen, ensure_ascii=False, indent=1))
    elif befehl == "hochladen":
        from .hosting import push
        print(f"{push()} Clips im Branch 'clips' bereitgestellt")
    elif befehl == "markiere":
        print("ok" if markiere_post(rest[0], rest[1], " ".join(rest[2:])) else "nicht gefunden")
    elif befehl == "status":
        print(json.dumps(lade_status(), ensure_ascii=False, indent=1))
    elif befehl == "aufraeumen":
        print(f"{aufraeumen()} alte Ordner gelöscht")
    else:
        print(__doc__)
        return 1
    return 0
