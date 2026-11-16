"""9:16-Video rendern: Layout, eingebrannte Untertitel, Hook-Einblendung, Lautheit."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .transkript import Wort

B, H = 1080, 1920


def _ass_zeit(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_text(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def schreibe_ass(woerter: list[Wort], start: float, ende: float, hook: str, ziel: Path) -> None:
    kopf = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {B}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,Arial Black,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,2,2,60,60,470,1
Style: Hook,Arial Black,62,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,18,0,8,70,70,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    zeilen: list[str] = []
    if hook.strip():
        zeilen.append(f"Dialogue: 1,{_ass_zeit(0)},{_ass_zeit(3.5)},Hook,,0,0,0,,{_ass_text(hook.strip())}")

    # Wörter in kurze Gruppen (max. 2 Wörter, Bruch bei Pause)
    im_clip = [w for w in woerter if w.ende > start and w.start < ende]
    gruppen: list[list[Wort]] = []
    for w in im_clip:
        if (not gruppen or len(gruppen[-1]) >= 2 or w.start - gruppen[-1][-1].ende > 0.6
                or sum(len(x.text) for x in gruppen[-1]) + len(w.text) > 22):
            gruppen.append([w])
        else:
            gruppen[-1].append(w)
    for i, g in enumerate(gruppen):
        a = g[0].start - start
        e = g[-1].ende - start
        if i + 1 < len(gruppen):
            naechst = gruppen[i + 1][0].start - start
            if naechst - e < 0.35:
                e = naechst
        e = max(e, a + 0.3)
        text = " ".join(w.text for w in g).upper()
        zeilen.append(f"Dialogue: 0,{_ass_zeit(a)},{_ass_zeit(min(e, ende - start))},Text,,0,0,0,,{_ass_text(text)}")
    ziel.write_text(kopf + "\n".join(zeilen) + "\n", encoding="utf-8")


def _filter(layout: str, facecam: tuple[float, float, float, float] | None) -> str:
    if layout == "crop":
        bild = f"[0:v]scale=-2:{H},crop={B}:{H}[bild]"
    elif layout == "facecam" and facecam:
        x, y, w, h = facecam
        cam_h = 640
        spiel_h = H - cam_h
        bild = (
            f"[0:v]split[a][b];"
            f"[a]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale={B}:{cam_h}:force_original_aspect_ratio=increase,"
            f"crop={B}:{cam_h}[cam];"
            f"[b]scale=-2:{spiel_h},crop={B}:{spiel_h}[spiel];"
            f"[cam][spiel]vstack[bild]"
        )
    else:  # blur
        bild = (
            f"[0:v]split[a][b];"
            f"[a]scale={B}:{H}:force_original_aspect_ratio=increase,crop={B}:{H},boxblur=25:3,"
            f"eq=brightness=-0.12[hg];"
            f"[b]scale={B}*1.3:-2,crop={B}:ih[vg];"
            f"[hg][vg]overlay=(W-w)/2:(H-h)/2-80[bild]"
        )
    return bild + ";[bild]subtitles=untertitel.ass,format=yuv420p[v]"


def rendere(quelle: Path, woerter: list[Wort], start: float, ende: float, hook: str,
            ordner: Path, layout: str = "blur",
            facecam: tuple[float, float, float, float] | None = None,
            quelle_beginnt_bei: float | None = None) -> Path:
    """`quelle` beginnt bei `quelle_beginnt_bei` (Standard: `start`)."""
    ordner.mkdir(parents=True, exist_ok=True)
    schreibe_ass(woerter, start, ende, hook, ordner / "untertitel.ass")
    versatz = start - (quelle_beginnt_bei if quelle_beginnt_bei is not None else start)
    ziel = ordner / "clip.mp4"
    cmd = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error"]
    if versatz > 0.01:
        cmd += ["-ss", f"{versatz:.3f}"]
    cmd += [
        "-i", str(quelle.resolve()), "-t", f"{ende - start:.3f}",
        "-filter_complex", _filter(layout, facecam), "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", ziel.name,
    ]
    subprocess.run(cmd, check=True, cwd=ordner)
    return ziel
