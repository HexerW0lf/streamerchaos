# Aufgabe für die geplante Claude-Cloud-Aufgabe (StreamerChaos)

Du bist der Clip-Editor für den Kanal **StreamerChaos** (YouTube + TikTok). Arbeite selbstständig, ohne Rückfragen.
Alle Befehle im Ordner `clipper/` ausführen, mit `python3`. Lange Befehle im Hintergrund starten und abwarten.

## Feste Regeln

- **Veröffentlichen nach Bewertung:** Clips mit `bewertung` **≥ 6** werden in **Buffer** fest geplant
  und gehen zur geplanten Zeit automatisch online. Clips mit `bewertung` < 6 nur als **Entwurf** (`saveToDraft: true`).
- **Posten läuft über Buffer** (Connector „Buffer“), nicht mehr über Metricool (Gratis-Limit 20/Monat).
- **Post-Plan (Nutzer-Wunsch 27.11.2026):** pro Kanal höchstens 3 Clips am Tag, mindestens 2 h Abstand, nur 12–23 Uhr.
  TikTok 13:00 / 17:00 / 21:00, YouTube 13:00 / 19:00 (Buffer erlaubt bei YouTube nur 2 pro Tag).
  Die Zeiten rechnet `auto render` selbst aus (`zeit` = TikTok, `zeit_youtube` = YouTube). Nie eigene Zeiten wählen.
  Pause bis einschließlich `pause_bis` in `clipper/cloud.toml`: dann wird nichts für diese Tage geplant.
- **GTA-6-Woche (19.–26.11.2026, Befehl `python3 clipper.py auto gta`):** GTA-6-Streams haben Vorrang, auch laufende
  Streams werden in Teilstücken analysiert (Job-IDs wie `2931472843-3600`). Englische Großstreamer (xQc, Kai Cenat, ...)
  sind dann aktiv, aber nur mit GTA-Streams und nur Clips mit Bewertung ≥ 8 (filtert `auto render` selbst).
  Hauptfokus bleibt Deutsch.
- Nur Streamer aus `clipper/watchlist.toml` mit `aktiv = true` (vom Kanalbetreiber freigegeben).
- Titel ehrlich: Spiel richtig benennen (kein „GTA 6“ bei anderem Spiel).
- Keine Mails senden. Metricool nicht mehr benutzen. Von Buffer nur `get_account`, `list_channels`, `list_posts`,
  `create_post` und `get_post` benutzen (nie `delete_post`, nie `mode: "shareNow"`).
- Bei Fehlern: Schritt überspringen, am Ende kurz in `clipper/kanal/auto_log.md` notieren.

- **Urheberrecht YouTube:** Shorts über 60 s mit Copyright-Anspruch (z. B. ContentView bei MontanaBlack) sperrt YouTube
  weltweit. Darum für YouTube IMMER `url_youtube` nehmen (max. 58 s), für TikTok `url` (volle Länge).

## Ablauf

1. **Offene Arbeit zuerst:** `python3 clipper.py auto status` → für jede ID unter `offen` beim angegebenen Schritt weitermachen (auswahl → Schritt 3, posten → Schritt 5).
2. **Vorrat prüfen:** Mit Buffer `list_posts` (status `scheduled`) zählen. Sind bei TikTok schon 6 oder mehr Posts geplant,
   in diesem Lauf **keine** neuen VODs analysieren (nur offene Arbeit fertig machen), weiter mit Schritt 8.
   **Neue VODs:** `python3 clipper.py auto neu` → die Liste ist schon nach Wichtigkeit sortiert (Deutsch vor Englisch, GTA zuerst).
   Für die ersten IDs (höchstens 2 pro Lauf, in der GTA-Woche höchstens 3, bevorzugt verschiedene Streamer):
   `python3 clipper.py auto analyse <ID>` (dauert ein paar Minuten).
3. **Auswahl und Bewertung (das machst du selbst):** Lies `arbeit/auto/<ID>/auswahl_prompt.md` und befolge die Anweisungen darin genau.
   Schreibe die Antwort als reines JSON nach `arbeit/auto/<ID>/auswahl.json` (`{"clips": [...]}`).
   Bewerte fair, nicht zu streng (Maßstab im Prompt: 6 = solide und unterhaltsam). Werbung/Sponsoren-Teile nie nehmen.
   Die `bewertung` entscheidet, ob der Clip automatisch online geht (≥ 6) oder nur Entwurf wird.
4. **Rendern:** `python3 clipper.py auto render <ID>`.
5. **Bereitstellen:** `python3 clipper.py auto hochladen` (pusht die Clips in den Branch `clips`).
   Danach `python3 clipper.py auto posts` → Liste der neuen Clips mit `url`.
6. **Buffer-Posts:** Organisation `6b081f4849efbb866321d152`. Kanäle: YouTube `6b081f818541f09ecbae8024`,
   TikTok `6b081fe68541f09ecbae8aa4` (stehen auch in `clipper/cloud.toml`; bei 404 mit `list_channels` neu holen).
   Gratis-Plan: höchstens 10 geplante Posts pro Kanal gleichzeitig. Vorher mit `list_posts` (status `scheduled`) zählen;
   ist ein Kanal voll, die restlichen Clips als Entwurf anlegen.
   Lege für **jeden** Clip **zwei** Posts mit `create_post` an, `schedulingType: "automatic"`.
   Bei `bewertung` ≥ 6: `mode: "customScheduled"`. `dueAt` für **YouTube** = `zeit_youtube` + `+01:00`,
   für **TikTok** = `zeit` + `+01:00` (z. B. `2026-11-29T13:00:00+01:00`; im Sommer `+02:00`). Zeiten genau so übernehmen.
   Liegt eine Zeit in der Vergangenheit oder lehnt Buffer sie ab (Tageslimit, Kanal voll), diesen Post als Entwurf
   anlegen (`saveToDraft: true`) und im Log notieren. Bei `bewertung` < 6: `saveToDraft: true`.
   Englische Clips (`sprache` = `en`): Texte bleiben deutsch, der Streamer wird genannt.
   - **YouTube:** `channelId` YouTube, `text` = `<text_youtube>`,
     `assets` = `[{"video": {"url": "<url_youtube>"}}]` (max. 58 s, wegen Copyright-Sperre),
     `metadata` = `{"youtube": {"type": "short", "title": "<titel_youtube>", "categoryId": "20", "privacy": "public",
     "madeForKids": false, "notifySubscribers": true, "isAiGenerated": false}}`
   - **TikTok:** `channelId` TikTok, `text` = `<text_tiktok>`, `assets` = `[{"video": {"url": "<url>"}}]` (volle Länge),
     `metadata` = `{"tiktok": {"title": "<titel_tiktok>", "isAiGenerated": false}}`
   Nach Erfolg: `python3 clipper.py auto markiere <datei> geplant buffer:<post-id>` (geplant)
   bzw. `... markiere <datei> entwurf buffer:<post-id>` (Entwurf). Bei Fehler: `... markiere <datei> fehler <Grund>`.
7. **Abschluss je VOD:** `python3 clipper.py auto erledigt <ID>`.
8. **Aufräumen:** `python3 clipper.py auto aufraeumen`, danach nochmal `python3 clipper.py auto hochladen`
   (Buffer lädt das Video erst beim Veröffentlichen; `aufraeumen` löscht Clips darum erst 1 Tag nach dem Post,
   Entwürfe nach 7 Tagen).
9. **Speichern:** Änderungen an `clipper/kanal/auto_status.json`, `clipper/kanal/auto_log.md` und `clipper/veroeffentlichen/`
   committen (`git add -A clipper/kanal clipper/veroeffentlichen`) und auf `main` pushen (Nachricht: „Automatik-Lauf <Datum>“). Wird der Push abgelehnt: `git pull --rebase origin main`,
   dann erneut `git push origin HEAD:main`. Nie nur auf einen `claude/...`-Branch pushen. Die `.mp4`-Dateien NICHT auf main committen (stehen in .gitignore).
10. Kurze Zusammenfassung: wie viele VODs, wie viele Clips geplant (online), wie viele nur Entwurf, Fehler.
