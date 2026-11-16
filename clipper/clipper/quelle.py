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
