"""Einstellungen, Profile und API-Keys."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
PROFIL_ORDNER = PROJEKT / "profile"


def _lese_env(pfad: Path) -> dict[str, str]:
    werte: dict[str, str] = {}
    if not pfad.is_file():
        return werte
    for zeile in pfad.read_text(encoding="utf-8", errors="replace").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, v = zeile.split("=", 1)
        werte[k.strip()] = v.strip().strip('"').strip("'")
    return werte


def finde_key(name: str) -> str | None:
    """Reihenfolge: Umgebung -> Projekt-.env -> ~/.config/watch/.env."""
    if os.environ.get(name):
        return os.environ[name]
    for pfad in (PROJEKT / ".env", Path.home() / ".config" / "watch" / ".env"):
        wert = _lese_env(pfad).get(name)
        if wert:
            return wert
    return None


@dataclass
class Profil:
    name: str
    spiel: str = ""
    sprache: str = "de"
    stichworte: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    hook_beispiele: list[str] = field(default_factory=list)
    clip_min: int = 25
    clip_max: int = 75
    tiktok_ueber_60: bool = True
    layout: str = "blur"  # blur | crop | facecam
    # facecam: Anteile des Quellbilds (x, y, b, h), 0..1
    facecam: tuple[float, float, float, float] | None = None
    hinweise: str = ""


def lade_profil(name: str) -> Profil:
    pfad = Path(name)
    if not pfad.is_file():
        pfad = PROFIL_ORDNER / f"{name}.toml"
    if not pfad.is_file():
        verfuegbar = ", ".join(p.stem for p in PROFIL_ORDNER.glob("*.toml"))
        raise SystemExit(f"Profil '{name}' nicht gefunden. Verfügbar: {verfuegbar}")
    daten = tomllib.loads(pfad.read_text(encoding="utf-8-sig"))
    fc = daten.get("facecam")
    return Profil(
        name=pfad.stem,
        spiel=daten.get("spiel", ""),
        sprache=daten.get("sprache", "de"),
        stichworte=list(daten.get("stichworte", [])),
        hashtags=list(daten.get("hashtags", [])),
        hook_beispiele=list(daten.get("hook_beispiele", [])),
        clip_min=int(daten.get("clip_min", 25)),
        clip_max=int(daten.get("clip_max", 75)),
        tiktok_ueber_60=bool(daten.get("tiktok_ueber_60", True)),
        layout=daten.get("layout", "blur"),
        facecam=tuple(fc) if fc else None,
        hinweise=daten.get("hinweise", ""),
    )
