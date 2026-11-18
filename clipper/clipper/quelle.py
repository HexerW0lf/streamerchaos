"""Quelle laden: URL (Twitch/YouTube/...) über yt-dlp oder lokale Datei."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _bin(name: str) -> str:
    pfad = shutil.which(name)
    if not pfad:
        raise SystemExit(f"'{name}' nicht gefunden. Bitte installieren (winget install {name}).")
    return pfad


def ist_url(quelle: str) -> bool:
    return quelle.startswith(("http://", "https://"))


@dataclass
class Info:
    quelle: str
    titel: str
    kanal: str
    dauer: float
    url: str | None  # None bei lokaler Datei


def hole_info(quelle: str) -> Info:
    if not ist_url(quelle):
        dauer = probe_dauer(Path(quelle))
        return Info(quelle, Path(quelle).stem, "", dauer, None)
    r = subprocess.run(
        [_bin("yt-dlp"), "-J", "--no-warnings", "--no-playlist", quelle],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise SystemExit(f"yt-dlp Fehler: {r.stderr.strip()[-500:]}")
    d = json.loads(r.stdout)
    return Info(
        quelle=quelle,
        titel=(d.get("title") or "").strip(),
        kanal=d.get("uploader") or d.get("channel") or d.get("uploader_id") or "",
        dauer=float(d.get("duration") or 0),
        url=d.get("webpage_url") or quelle,
    )


def probe_dauer(datei: Path) -> float:
    r = subprocess.run(
        [_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(datei)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _hls_abschnitt(url: str, fmt: str, start: float, ende: float | None, ziel: Path, nur_ton: bool) -> bool:
    """Abschnitt eines Twitch-VODs direkt über die HLS-Playlist laden.

    Bei laufenden Streams ist die Playlist noch offen; ffmpeg würde sie als Livestream lesen und
    am Live-Ende in Echtzeit mitschneiden. Deshalb wird eine lokale, abgeschlossene Kopie mit nur
    den nötigen Segmenten gebaut. Gibt False zurück, wenn das nicht geht (dann normaler Weg).
    """
    import urllib.parse
    r = subprocess.run([_bin("yt-dlp"), "--no-warnings", "--no-playlist", "-f", fmt, "-g", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m3u8 = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
    if ".m3u8" not in m3u8:
        return False
    t = subprocess.run(["curl", "-sSfL", m3u8], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if t.returncode != 0:
        return False
    segmente, pos, dauer = [], 0.0, None
    for zeile in t.stdout.splitlines():
        zeile = zeile.strip()
        if zeile.startswith("#EXTINF:"):
            dauer = float(zeile[8:].split(",")[0])
        elif zeile and not zeile.startswith("#") and dauer is not None:
            segmente.append((pos, dauer, urllib.parse.urljoin(m3u8, zeile)))
            pos += dauer
            dauer = None
    bis = ende if ende is not None else pos
    wahl = [sg for sg in segmente if sg[0] + sg[1] > start and sg[0] < bis]
    if not wahl:
        return False
    liste = ziel.parent / (ziel.stem + "_teil.m3u8")
    zeilen = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-PLAYLIST-TYPE:VOD",
              f"#EXT-X-TARGETDURATION:{int(max(sg[1] for sg in wahl)) + 1}", "#EXT-X-MEDIA-SEQUENCE:0"]
    for _, d, u in wahl:
        zeilen += [f"#EXTINF:{d:.3f},", u]
    zeilen.append("#EXT-X-ENDLIST")
    liste.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    versatz = max(0.0, start - wahl[0][0])
    laenge = min(bis, wahl[-1][0] + wahl[-1][1]) - start
    cmd = [_bin("ffmpeg"), "-y", "-v", "error", "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
           "-ss", f"{versatz:.3f}", "-i", str(liste), "-t", f"{laenge:.3f}"]
    if nur_ton:
        cmd += ["-vn", "-ac", "1", "-c:a", "aac", "-b:a", "96k"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k"]
    ok = subprocess.run(cmd + [str(ziel)]).returncode == 0 and ziel.is_file() and ziel.stat().st_size > 0
    liste.unlink(missing_ok=True)
    return ok


def lade_audio(info: Info, ziel: Path, start: float | None = None, ende: float | None = None) -> Path:
    """Nur den Ton laden (klein, schnell). Bei lokaler Datei: Ton extrahieren."""
    ziel.mkdir(parents=True, exist_ok=True)
    fertig = ziel / "audio.m4a"
    if fertig.is_file() and fertig.stat().st_size > 0:
        return fertig
    if info.url is None:
        cmd = [_bin("ffmpeg"), "-y", "-v", "error"]
        if start is not None:
            cmd += ["-ss", str(start)]
        cmd += ["-i", info.quelle]
        if ende is not None:
            cmd += ["-t", str(ende - (start or 0))]
        cmd += ["-vn", "-ac", "1", "-c:a", "aac", "-b:a", "96k", str(fertig)]
        subprocess.run(cmd, check=True)
        return fertig
    if (start is not None or ende is not None) and "twitch.tv/videos" in info.url:
        if _hls_abschnitt(info.url, "Audio_Only/bestaudio/worst", start or 0.0, ende, fertig, nur_ton=True):
            return fertig
    cmd = [
        _bin("yt-dlp"), "--no-warnings", "--no-playlist", "-N", "8",
        "-f", "Audio_Only/bestaudio/worst",
        "-o", str(ziel / "audio_roh.%(ext)s"),
    ]
    if start is not None or ende is not None:
        cmd += ["--download-sections", f"*{start or 0}-{ende if ende is not None else 'inf'}"]
    cmd.append(info.url)
    subprocess.run(cmd, check=True)
    roh = next(ziel.glob("audio_roh.*"))
    # Einheitlich in Mono-AAC umwandeln (auch wenn Video-Format geladen wurde)
    subprocess.run(
        [_bin("ffmpeg"), "-y", "-v", "error", "-i", str(roh), "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "96k", str(fertig)],
        check=True,
    )
    roh.unlink(missing_ok=True)
    return fertig


def lade_abschnitt(info: Info, start: float, ende: float, ziel: Path) -> Path:
    """Video-Abschnitt in max. 1080p laden. Gibt Datei zurück, die bei `start` beginnt."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    if ziel.is_file() and ziel.stat().st_size > 0:
        return ziel
    if info.url is None:
        subprocess.run(
            [_bin("ffmpeg"), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", info.quelle,
             "-t", f"{ende - start:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-c:a", "aac", "-b:a", "160k", str(ziel)],
            check=True,
        )
        return ziel
    if "twitch.tv/videos" in info.url and _hls_abschnitt(
            info.url, "b[height<=1080]/best", start, ende, ziel, nur_ton=False):
        return ziel
    vorlage = ziel.with_suffix("")
    subprocess.run(
        [_bin("yt-dlp"), "--no-warnings", "--no-playlist", "-N", "8",
         "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
         "--download-sections", f"*{start:.2f}-{ende:.2f}", "--force-keyframes-at-cuts",
         "--merge-output-format", "mp4",
         "-o", str(vorlage) + ".%(ext)s", info.url],
        check=True,
    )
    gefunden = next(p for p in ziel.parent.glob(vorlage.name + ".*") if p.suffix in (".mp4", ".mkv", ".webm"))
    if gefunden != ziel:
        gefunden.replace(ziel)
    return ziel
