# Cloud-Automatik einrichten (einmalig, ca. 10 Minuten)

Alles auf **https://claude.ai/code** im Browser.

## 1. GitHub verbinden
- Falls noch nicht geschehen: Claude Code mit GitHub verbinden (beim ersten Öffnen wird danach gefragt).
- Der Claude-App Zugriff auf das Repo **HexerW0lf/streamerchaos** geben.

## 2. Umgebung anlegen
Neue Cloud-Umgebung, Name z. B. **StreamerChaos**:

| Einstellung | Wert |
|---|---|
| Netzwerkzugriff | **Full** (Twitch nutzt sehr viele Server-Adressen) |
| Setup script | `bash cloud/setup.sh` |
| Umgebungsvariablen | `CLIPPER_KEY_PROXY=1` und `BASH_MAX_TIMEOUT_MS=1800000` |
| Network secret | Host `api.openai.com`, Wert = dein OpenAI-API-Key (wie in `~/.config/watch/.env`) |

Den OpenAI-Key **nur** als Network secret eintragen, nicht als Umgebungsvariable und nicht in den Chat.

## 3. Geplante Aufgabe anlegen
| Einstellung | Wert |
|---|---|
| Repository | HexerW0lf/streamerchaos |
| Umgebung | StreamerChaos |
| Modell | Sonnet |
| Zeitplan | täglich, z. B. 06:07 und 15:07 Uhr (eigener Cron: `7 6,15 * * *`) |
| Connectoren | nur **Buffer** (Metricool und Gmail aus) |
| Prompt | `Lies cloud/AUFGABE.md und führe die Aufgabe genau so aus.` |

## 4. Erster Test
- Bei der Aufgabe auf **„Jetzt ausführen“** klicken.
- Vorher in `clipper/watchlist.toml` mindestens einen Streamer mit Erlaubnis auf `aktiv = true` setzen und pushen
  (oder Claude im Chat bitten).
- Danach in Buffer unter **Entwürfe** bzw. **Queue** nachsehen.

## Jeden Abend (5–10 Minuten)
Buffer-App öffnen → Entwürfe → Clip ansehen → **Planen** (oder löschen). Clips ab Bewertung 6 gehen von selbst online.
