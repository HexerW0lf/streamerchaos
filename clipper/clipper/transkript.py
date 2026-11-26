"""Transkript nur für Kandidaten-Fenster (OpenAI Whisper, Wort-Zeitstempel)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import finde_key

API = "https://api.openai.com/v1/audio/transcriptions"


@dataclass
class Wort:
    start: float  # absolut, Sekunden ab Quellstart
    ende: float
    text: str


def _multipart(felder: list[tuple[str, str]], datei_feld: str, datei: Path) -> tuple[bytes, str]:
    grenze = "----clipper" + uuid.uuid4().hex
    teile: list[bytes] = []
    for k, v in felder:
        teile.append(f"--{grenze}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    teile.append(
        f"--{grenze}\r\nContent-Disposition: form-data; name=\"{datei_feld}\"; filename=\"{datei.name}\"\r\n"
        "Content-Type: audio/mpeg\r\n\r\n".encode()
    )
    teile.append(datei.read_bytes())
    teile.append(f"\r\n--{grenze}--\r\n".encode())
    return b"".join(teile), f"multipart/form-data; boundary={grenze}"


def _whisper(datei: Path, sprache: str) -> dict:
    key = finde_key("OPENAI_API_KEY")
    # In der Claude-Cloud hängt der Proxy den Key an (Network secret) -> kein Key im Prozess
    proxy = os.environ.get("CLIPPER_KEY_PROXY") == "1"
    if not key and not proxy:
        raise SystemExit("OPENAI_API_KEY fehlt (Umgebung, .env im Projekt oder ~/.config/watch/.env).")
    body, ctype = _multipart(
        [("model", "whisper-1"), ("response_format", "verbose_json"),
         ("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment"),
         ("language", sprache)],
        "file", datei,
    )
    for versuch in range(3):
        kopf = {"Content-Type": ctype}
        if key:
            kopf["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(API, data=body, headers=kopf)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and versuch < 2:
                time.sleep(5 * (versuch + 1))
                continue
            raise SystemExit(f"Whisper Fehler {e.code}: {e.read()[:300]!r}")
        except urllib.error.URLError:
            if versuch < 2:
                time.sleep(5)
                continue
            raise
    raise RuntimeError("unerreichbar")


# --- Kostenloser Rückfall: faster-whisper lokal auf der CPU (z. B. wenn OpenAI-Guthaben leer ist) ---
_MODELL = None
_SPERRE = threading.Lock()
_OPENAI_KAPUTT = os.environ.get("CLIPPER_TRANSKRIPT") == "lokal"


def _lokal(datei: Path, sprache: str) -> dict:
    global _MODELL
    from faster_whisper import WhisperModel  # pip install faster-whisper
    with _SPERRE:
        if _MODELL is None:
            name = os.environ.get("CLIPPER_WHISPER_MODELL", "small")
            print(f"[transkript] lokales Modell {name} (faster-whisper, CPU)")
            _MODELL = WhisperModel(name, device="cpu", compute_type="int8")
        # Audio selbst per ffmpeg dekodieren (16 kHz mono float), unabhängig von PyAV-Versionen
        import numpy as np
        roh = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(datei),
                              "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        ton = np.frombuffer(roh, dtype=np.float32)
        segmente, _ = _MODELL.transcribe(ton, language=sprache, word_timestamps=True, vad_filter=False)
        segs, woerter = [], []
        for s in segmente:
            segs.append({"start": s.start, "end": s.end, "text": s.text})
            for w in s.words or []:
                woerter.append({"start": w.start, "end": w.end, "word": w.word})
    return {"segments": segs, "words": woerter}


def _transkribiere_datei(datei: Path, sprache: str) -> dict:
    """OpenAI zuerst; schlägt das fehl (z. B. 429 kein Guthaben), ab dann lokal."""
    global _OPENAI_KAPUTT
    if not _OPENAI_KAPUTT:
        try:
            return _whisper(datei, sprache)
        except (SystemExit, Exception) as e:  # noqa: BLE001
            print(f"[transkript] OpenAI nicht nutzbar ({str(e)[:120]}), nehme lokales Whisper")
            _OPENAI_KAPUTT = True
    return _lokal(datei, sprache)


def transkribiere(audio: Path, start: float, ende: float, audio_offset: float,
                  sprache: str, cache: Path) -> list[Wort]:
    """`start`/`ende` absolut; `audio_offset` = absolute Zeit, bei der audio.m4a beginnt."""
    cache.mkdir(parents=True, exist_ok=True)
    schluessel = cache / f"w_{int(start * 10)}_{int(ende * 10)}.json"
    if schluessel.is_file():
        daten = json.loads(schluessel.read_text(encoding="utf-8"))
    else:
        mp3 = cache / f"a_{int(start * 10)}.mp3"
        subprocess.run(
            [shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error",
             "-ss", f"{start - audio_offset:.2f}", "-i", str(audio), "-t", f"{ende - start:.2f}",
             "-ac", "1", "-ar", "16000", "-b:a", "48k", str(mp3)],
            check=True,
        )
        daten = _transkribiere_datei(mp3, sprache)
        schluessel.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        mp3.unlink(missing_ok=True)
    woerter = [Wort(start + float(w["start"]), start + float(w["end"]), str(w["word"]).strip())
               for w in daten.get("words") or [] if str(w.get("word", "")).strip()]
    if not woerter:  # Rückfall: Segmente gleichmäßig auf Wörter verteilen
        for s in daten.get("segments") or []:
            teile = str(s.get("text", "")).split()
            if not teile:
                continue
            a, b = float(s["start"]), float(s["end"])
            schritt = (b - a) / len(teile)
            for i, t in enumerate(teile):
                woerter.append(Wort(start + a + i * schritt, start + a + (i + 1) * schritt, t))
    return woerter


def als_text(woerter: list[Wort], von: float, bis: float) -> str:
    """Lesbares Transkript mit absoluten Zeitmarken alle ~5 s."""
    zeilen: list[str] = []
    aktuell: list[str] = []
    marke = None
    for w in woerter:
        if w.ende < von or w.start > bis:
            continue
        if marke is None or w.start - marke >= 5:
            if aktuell:
                zeilen.append(" ".join(aktuell))
            marke = w.start
            aktuell = [f"[{marke:.1f}]"]
        aktuell.append(w.text)
    if aktuell:
        zeilen.append(" ".join(aktuell))
    return "\n".join(zeilen)
