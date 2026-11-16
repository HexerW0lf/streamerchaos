"""Clipper – Stream-VOD rein, fertige 9:16-Clips raus.

Beispiele:
  python clipper.py vod https://www.twitch.tv/videos/123456789 --profil gta6
  python clipper.py vod meinvideo.mp4 --max-clips 5 --start 1:00:00 --ende 2:30:00
  python clipper.py vod URL --nur-analyse        (nur Kandidaten, kein Rendern)
"""

from __future__ import annotations

import argparse
import sys

from clipper.config import lade_profil


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="modus", required=True)

    v = sub.add_parser("vod", help="Fertiges VOD oder Video verarbeiten")
    v.add_argument("quelle", help="URL (Twitch, YouTube, ...) oder lokale Datei")
    v.add_argument("--profil", default="gta6")
    v.add_argument("--max-clips", type=int, default=8)
    v.add_argument("--start", help="ab Zeitpunkt (HH:MM:SS)")
    v.add_argument("--ende", help="bis Zeitpunkt (HH:MM:SS)")
    v.add_argument("--modell", default="sonnet", help="Claude-Modell für die Auswahl (haiku/sonnet/opus)")
    v.add_argument("--layout", choices=["blur", "crop", "facecam"], help="überschreibt das Profil")
    v.add_argument("--nur-analyse", action="store_true")

    sub.add_parser("sync", help="Kanalzahlen aus Metricool holen (über Claude)")
    au = sub.add_parser("auto", help="Automatik (Watchlist, Cloud): neu | analyse ID | render ID | erledigt ID | posts | markiere DATEI STATUS | status | aufraeumen")
    au.add_argument("befehl", nargs=argparse.REMAINDER)

    a = p.parse_args()
    if a.modus == "auto":
        from clipper.auto import main as auto_main
        return auto_main(a.befehl)
    if a.modus == "sync":
        from clipper.metricool_sync import main as sync_main
        sync_main()
        return 0
    if a.modus == "vod":
        from clipper.vod import lauf
        lauf(a.quelle, lade_profil(a.profil), a.max_clips, a.start, a.ende, a.modell, a.layout, a.nur_analyse)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
