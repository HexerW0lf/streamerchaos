# Clipper

Stream-VOD rein, fertige 9:16-Clips mit Untertiteln, Hook und Texten raus. Hochladen machst du selbst (YouTube Studio / TikTok planen).

## Voraussetzungen

- Python 3.11+ mit `numpy`
- `ffmpeg`, `ffprobe`, `yt-dlp` im PATH
- `OPENAI_API_KEY` (Whisper) – wird aus Umgebung, `.env` hier im Ordner oder `~/.config/watch/.env` gelesen
- `claude` CLI (für die Auswahl; ohne Claude werden einfach die lautesten Momente genommen)

## Benutzen

```bash
python clipper.py vod https://www.twitch.tv/videos/123456789 --profil gta6
```

Optionen:

| Option | Bedeutung |
|---|---|
| `--max-clips 8` | wie viele Clips höchstens |
| `--start 2:00:00 --ende 3:00:00` | nur diesen Teil des Streams |
| `--modell sonnet` | Claude-Modell für die Auswahl (`haiku` spart Limit) |
| `--layout blur/crop/facecam` | Bildaufteilung, überschreibt das Profil |
| `--nur-analyse` | nur Kandidaten finden, nichts rendern |

## Ablauf

1. Nur der Ton wird geladen (klein, schnell).
2. Lautstärke-Spitzen gegenüber den letzten ~3 Minuten = Kandidaten.
3. Nur die Kandidaten werden mit Whisper transkribiert (kostet wenige Cent).
4. Claude wählt die besten Momente, legt Start/Ende fest und schreibt Hook, Titel, Beschreibung, Hashtags.
5. Nur diese Abschnitte werden als Video geladen und in 1080×1920 gerendert (Untertitel eingebrannt, Hook oben, Lautheit -14 LUFS).

## Ausgabe

`ausgabe/<datum>_<kanal>/`
- `übersicht.md` – alle Clips mit Bewertung und Post-Zeitpunkt
- `NN_titel/clip.mp4` – fertiges Video
- `NN_titel/info.md` – Titel, Beschreibung, Hashtags für YouTube und TikTok, Quellenangabe, Checkliste

`arbeit/` ist Zwischenspeicher (Ton, Transkripte, Abschnitte) und kann gelöscht werden.

## Profile

`profile/*.toml` – pro Spiel: Stichworte, Hashtags, Hook-Beispiele, Cliplänge, Layout. Neues Spiel = Datei kopieren und anpassen.

Facecam-Layout: in der Profil-Datei `layout = "facecam"` und `facecam = [x, y, breite, höhe]` (Anteile 0..1 vom Quellbild) setzen.

## Wichtig

- Fremde Clips nur mit Erlaubnis des Streamers oder aus offiziellen Clipping-Kampagnen posten.
- Für die Monetarisierung braucht jeder Clip einen eigenen Beitrag (Voice-over, Kommentar, Einordnung). Siehe Skill `/kanal-start`.
