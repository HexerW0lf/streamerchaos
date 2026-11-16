"""Laute Momente finden: Lautstärke-Spitzen im Vergleich zur Umgebung."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 8000
FENSTER = 0.5  # Sekunden pro Messpunkt


@dataclass
class Kandidat:
    zeit: float      # Spitze, Sekunden ab Quellstart
    start: float     # Fenster für Transkript
    ende: float
    punkte: float    # Lautstärke-Ausschlag in dB über Umgebung


def lautstaerke(audio: Path) -> np.ndarray:
    """dB-Pegel je 0,5 s."""
    proc = subprocess.Popen(
        [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(audio),
         "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
    )
    n = int(RATE * FENSTER)
    werte: list[float] = []
    rest = b""
    assert proc.stdout is not None
    while True:
        block = proc.stdout.read(n * 2 * 512)
        if not block:
            break
        block = rest + block
        nutzbar = len(block) // (n * 2) * (n * 2)
        rest = block[nutzbar:]
        if not nutzbar:
            continue
        s = np.frombuffer(block[:nutzbar], dtype=np.int16).astype(np.float32).reshape(-1, n)
        rms = np.sqrt(np.mean(s * s, axis=1)) + 1.0
        werte.extend((20 * np.log10(rms / 32768.0)).tolist())
    proc.wait()
    return np.array(werte, dtype=np.float32)


def _gleitend(x: np.ndarray, breite: int) -> np.ndarray:
    if breite <= 1 or len(x) < breite:
        return x.copy()
    kern = np.ones(breite, dtype=np.float32) / breite
    pad = breite // 2
    xp = np.pad(x, (pad, breite - 1 - pad), mode="edge")
    return np.convolve(xp, kern, mode="valid")


def finde_kandidaten(
    db: np.ndarray,
    anzahl: int,
    vor: float = 45.0,
    nach: float = 25.0,
    abstand: float = 90.0,
    offset: float = 0.0,
) -> list[Kandidat]:
    """Spitzen: kurzzeitig (4 s) deutlich lauter als die letzten ~3 Minuten."""
    if len(db) == 0:
        return []
    pro_s = 1 / FENSTER
    kurz = _gleitend(db, int(4 * pro_s))
    umgebung = _gleitend(db, int(180 * pro_s))
    # Stille/Pausen nicht als Basis nehmen
    umgebung = np.maximum(umgebung, np.percentile(db, 30))
    ausschlag = kurz - umgebung
    reihenfolge = np.argsort(-ausschlag)
    gewaehlt: list[int] = []
    min_abstand = int(abstand * pro_s)
    for i in reihenfolge:
        if ausschlag[i] <= 0.5:
            break
        if all(abs(int(i) - g) >= min_abstand for g in gewaehlt):
            gewaehlt.append(int(i))
            if len(gewaehlt) >= anzahl:
                break
    dauer = len(db) * FENSTER
    raus = []
    for i in sorted(gewaehlt):
        t = i * FENSTER
        raus.append(Kandidat(
            zeit=offset + t,
            start=offset + max(0.0, t - vor),
            ende=offset + min(dauer, t + nach),
            punkte=float(ausschlag[i]),
        ))
    return raus
