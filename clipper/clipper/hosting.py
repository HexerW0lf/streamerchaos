"""Clips öffentlich bereitstellen: Branch `clips` im GitHub-Repo, Abruf über raw.githubusercontent.com.

Der Branch wird bei jedem Push neu erzeugt (ein einziger Commit), damit das Repo nicht wächst.
Metricool lädt das Video beim Einplanen von dieser URL.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
import urllib.parse
from pathlib import Path

from .config import PROJEKT

ROOT = PROJEKT.parent  # Repo-Wurzel ("GTA 6 Clips ai")
VEROEFF = PROJEKT / "veroeffentlichen"
BRANCH = "clips"
ARBEITSKOPIE = ROOT / ".clips-branch"


def repo_name() -> str:
    cfg = PROJEKT / "cloud.toml"
    if cfg.is_file():
        name = tomllib.loads(cfg.read_text(encoding="utf-8-sig")).get("github_repo", "").strip()
        if name and "/" in name:
            return name
    raise SystemExit("clipper/cloud.toml: github_repo = \"BENUTZER/REPO\" fehlt")


def raw_url(datei: str) -> str:
    """datei relativ zu clipper/, z. B. veroeffentlichen/123/01_x.mp4"""
    pfad = urllib.parse.quote(datei.split("veroeffentlichen/", 1)[-1])
    return f"https://raw.githubusercontent.com/{repo_name()}/{BRANCH}/{pfad}"


def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def push() -> int:
    """Spiegelt veroeffentlichen/ in den Branch `clips` und pusht ihn (force)."""
    dateien = [p for p in VEROEFF.rglob("*") if p.is_file() and p.suffix in (".mp4", ".json")]
    if ARBEITSKOPIE.exists():
        try:
            _git("worktree", "remove", "--force", str(ARBEITSKOPIE))
        except RuntimeError:
            shutil.rmtree(ARBEITSKOPIE, ignore_errors=True)
            _git("worktree", "prune")
    _git("worktree", "add", "--detach", str(ARBEITSKOPIE))
    try:
        _git("checkout", "--orphan", "clips-neu", cwd=ARBEITSKOPIE)
        _git("rm", "-rf", "--quiet", ".", cwd=ARBEITSKOPIE)
        for p in ARBEITSKOPIE.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        for f in dateien:
            ziel = ARBEITSKOPIE / f.relative_to(VEROEFF)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, ziel)
        (ARBEITSKOPIE / "README.md").write_text("Automatisch erzeugt: fertige Clips für Metricool.\n", encoding="utf-8")
        _git("add", "-A", cwd=ARBEITSKOPIE)
        _git("-c", "user.name=StreamerChaos Clipper", "-c", "user.email=clipper@users.noreply.github.com",
             "commit", "-q", "-m", "Clips aktualisieren", cwd=ARBEITSKOPIE)
        _git("push", "-f", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=ARBEITSKOPIE)
    finally:
        try:
            _git("worktree", "remove", "--force", str(ARBEITSKOPIE))
        except RuntimeError:
            pass
        try:
            _git("branch", "-D", "clips-neu")
        except RuntimeError:
            pass
    return len([f for f in dateien if f.suffix == ".mp4"])
