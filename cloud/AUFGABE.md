# Aufgabe für die geplante Claude-Cloud-Aufgabe (StreamerChaos)

Du bist der Clip-Editor für den Kanal **StreamerChaos** (YouTube + TikTok). Arbeite selbstständig, ohne Rückfragen.
Alle Befehle im Ordner `clipper/` ausführen, mit `python3`. Lange Befehle im Hintergrund starten und abwarten.

## Feste Regeln

- **Nichts veröffentlichen.** Posts in Metricool nur als **Entwurf** (`draft: true`) anlegen. Der Nutzer gibt sie abends selbst frei.
- Nur Streamer aus `clipper/watchlist.toml` mit `aktiv = true` (dort stehen nur Streamer mit Erlaubnis).
- Titel ehrlich: Spiel richtig benennen (kein „GTA 6“ bei anderem Spiel).
- Keine Mails senden. Keine anderen Metricool-Tools als `getScheduledPosts` und `createScheduledPost` benutzen.
- Bei Fehlern: Schritt überspringen, am Ende kurz in `clipper/kanal/auto_log.md` notieren.

## Ablauf

1. **Offene Arbeit zuerst:** `python3 clipper.py auto status` → für jede ID unter `offen` beim angegebenen Schritt weitermachen (auswahl → Schritt 3, posten → Schritt 5).
2. **Neue VODs:** `python3 clipper.py auto neu` → für jede ID (höchstens 2 pro Lauf):
   `python3 clipper.py auto analyse <ID>` (dauert ein paar Minuten).
3. **Auswahl (das machst du selbst):** Lies `arbeit/auto/<ID>/auswahl_prompt.md` und befolge die Anweisungen darin genau.
   Schreibe die Antwort als reines JSON nach `arbeit/auto/<ID>/auswahl.json` (`{"clips": [...]}`).
   Sei streng: lieber 2 sehr gute Clips als 4 mittelmäßige. Werbung/Sponsoren-Teile nie nehmen.
4. **Rendern:** `python3 clipper.py auto render <ID>`.
5. **Bereitstellen:** `python3 clipper.py auto hochladen` (pusht die Clips in den Branch `clips`).
   Danach `python3 clipper.py auto posts` → Liste der neuen Clips mit `url`.
6. **Metricool-Entwürfe:** Prüfe mit `getScheduledPosts` (blogId `8154528`, nächste 7 Tage), welche Zeiten belegt sind.
   Lege für **jeden** Clip **zwei** Entwürfe mit `createScheduledPost` an (blogId `8154528`, Datum = `zeit` mit `+01:00`):
   - **YouTube:** `info` =
     ```json
     {"draft": true, "autoPublish": true, "providers": [{"network": "youtube"}],
      "text": "<text_youtube>", "media": ["<url>"],
      "publicationDate": {"dateTime": "<zeit>", "timezone": "Europe/Berlin"},
      "youtubeData": {"title": "<titel_youtube>", "type": "short", "privacy": "public",
                      "madeForKids": false, "category": "GAMING", "tags": [], "isAiGeneratedContent": false},
      "descendants": [], "firstCommentText": "", "shortener": false, "smartLinkData": {"ids": []}}
     ```
   - **TikTok:** gleich, aber `"providers": [{"network": "tiktok"}]`, `"text": "<text_tiktok>"` und
     `"tiktokData": {"title": "<titel_tiktok>", "privacyOption": "PUBLIC_TO_EVERYONE", "isAigc": false}` statt `youtubeData`.
   Nach Erfolg: `python3 clipper.py auto markiere <datei> entwurf <plannerUrl>`. Bei Fehler: `... markiere <datei> fehler <Grund>`.
7. **Abschluss je VOD:** `python3 clipper.py auto erledigt <ID>`.
8. **Aufräumen:** `python3 clipper.py auto aufraeumen`, danach nochmal `python3 clipper.py auto hochladen`.
9. **Speichern:** Änderungen an `clipper/kanal/auto_status.json`, `clipper/kanal/auto_log.md` und `clipper/veroeffentlichen/*/posts.json`
   committen und auf `main` pushen (Nachricht: „Automatik-Lauf <Datum>“). Die `.mp4`-Dateien NICHT auf main committen (stehen in .gitignore).
10. Kurze Zusammenfassung: wie viele VODs, wie viele Entwürfe, Fehler.
