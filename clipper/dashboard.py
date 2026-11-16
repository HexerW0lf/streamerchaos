"""Lokales Dashboard für Clipper und Kanal.

Start:  python dashboard.py        -> http://127.0.0.1:8780
Läuft nur auf diesem Rechner (127.0.0.1), nicht im Netzwerk erreichbar.
"""

from __future__ import annotations

import datetime as dt
import json
import mimetypes
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUSGABE = ROOT / "ausgabe"
JOBS_DIR = ROOT / "arbeit" / "jobs"
KANAL = ROOT / "kanal"
PORT = int(__import__("os").environ.get("PORT") or 8780)

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


# ---------- Daten ----------

def laeufe() -> list[dict]:
    raus = []
    if not AUSGABE.is_dir():
        return raus
    for lauf in sorted(AUSGABE.iterdir(), reverse=True):
        if not lauf.is_dir():
            continue
        clips = []
        for c in sorted(lauf.iterdir()):
            cj = c / "clip.json"
            if not cj.is_file():
                continue
            daten = json.loads(cj.read_text(encoding="utf-8"))
            info = (c / "info.md").read_text(encoding="utf-8") if (c / "info.md").is_file() else ""
            daten.update(
                id=f"{lauf.name}/{c.name}",
                video=f"/datei/{urllib.parse.quote(lauf.name)}/{urllib.parse.quote(c.name)}/clip.mp4",
                info=info,
                status=daten.get("status", "neu"),
            )
            clips.append(daten)
        kopf = ""
        ue = lauf / "übersicht.md"
        if ue.is_file():
            kopf = ue.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        raus.append({"name": lauf.name, "titel": kopf, "clips": clips})
    return raus


def setze_status(clip_id: str, status: str) -> bool:
    pfad = (AUSGABE / clip_id / "clip.json").resolve()
    if AUSGABE.resolve() not in pfad.parents or not pfad.is_file():
        return False
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["status"] = status
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def profile() -> list[str]:
    return sorted(p.stem for p in (ROOT / "profile").glob("*.toml"))


def kanal_zahlen() -> list[dict]:
    f = KANAL / "zahlen.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else []


def kanal_speichern(eintrag: dict) -> list[dict]:
    KANAL.mkdir(exist_ok=True)
    zahlen = [z for z in kanal_zahlen() if z.get("datum") != eintrag["datum"]]
    zahlen.append(eintrag)
    zahlen.sort(key=lambda z: z["datum"])
    (KANAL / "zahlen.json").write_text(json.dumps(zahlen, ensure_ascii=False, indent=1), encoding="utf-8")
    return zahlen


_sync = {"status": "bereit", "zeit": "", "fehler": ""}


def starte_sync() -> None:
    if _sync["status"] == "läuft":
        return

    def arbeit():
        from clipper.metricool_sync import hole, speichere
        try:
            speichere(hole())
            _sync.update(status="fertig", fehler="")
        except Exception as e:  # noqa: BLE001
            _sync.update(status="fehler", fehler=str(e)[:300])
        _sync["zeit"] = dt.datetime.now().strftime("%H:%M")

    _sync.update(status="läuft", fehler="")
    threading.Thread(target=arbeit, daemon=True).start()


VERB_FELDER = ("youtube", "tiktok", "gmail")


def verbindungen() -> dict:
    f = KANAL / "verbindungen.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}


def verbindungen_speichern(p: dict) -> dict:
    KANAL.mkdir(exist_ok=True)
    daten = verbindungen()
    for k in VERB_FELDER:
        if k in p:
            daten[k] = str(p[k]).strip()[:300]
    (KANAL / "verbindungen.json").write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    return daten


# ---------- Jobs ----------

def starte_job(p: dict) -> str:
    quelle = str(p.get("quelle", "")).strip()
    if not quelle:
        raise ValueError("Quelle fehlt")
    if quelle.startswith("-"):
        raise ValueError("ungültige Quelle")
    cmd = [sys.executable, str(ROOT / "clipper.py"), "vod", quelle,
           "--profil", str(p.get("profil") or "gta6"),
           "--max-clips", str(int(p.get("max_clips") or 6)),
           "--modell", str(p.get("modell") or "sonnet")]
    for k in ("start", "ende"):
        v = str(p.get(k) or "").strip()
        if v:
            if not all(ch.isdigit() or ch == ":" for ch in v):
                raise ValueError(f"{k}: Format HH:MM:SS")
            cmd += [f"--{k}", v]
    if p.get("layout") in ("blur", "crop", "facecam"):
        cmd += ["--layout", p["layout"]]
    if p.get("nur_analyse"):
        cmd.append("--nur-analyse")
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jid = time.strftime("%Y%m%d-%H%M%S")
    log = JOBS_DIR / f"{jid}.log"
    fh = open(log, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    with _lock:
        _jobs[jid] = {"id": jid, "quelle": quelle, "proc": proc, "log": log, "fh": fh,
                      "gestartet": dt.datetime.now().strftime("%H:%M")}
    return jid


def jobs() -> list[dict]:
    raus = []
    with _lock:
        for j in sorted(_jobs.values(), key=lambda j: j["id"], reverse=True):
            code = j["proc"].poll()
            if code is not None and not j["fh"].closed:
                j["fh"].close()
            text = j["log"].read_text(encoding="utf-8", errors="replace") if j["log"].is_file() else ""
            zeilen = [z for z in text.splitlines() if z.startswith("[clipper]") or "Traceback" in z
                      or "Error" in z or "Fehler" in z]
            raus.append({
                "id": j["id"], "quelle": j["quelle"], "gestartet": j["gestartet"],
                "status": "läuft" if code is None else ("fertig" if code == 0 else f"Fehler ({code})"),
                "zeilen": zeilen[-12:],
            })
    return raus


def stoppe_job(jid: str) -> bool:
    with _lock:
        j = _jobs.get(jid)
        if j and j["proc"].poll() is None:
            j["proc"].terminate()
            return True
    return False


# ---------- HTTP ----------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # ruhig
        pass

    def _json(self, daten, code=200):
        body = json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        pfad = urllib.parse.urlparse(self.path).path
        if pfad in ("/", "/index.html"):
            body = (ROOT / "dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif pfad == "/api/status":
            self._json({"laeufe": laeufe(), "jobs": jobs(), "profile": profile(),
                        "kanal": kanal_zahlen(), "verbindungen": verbindungen(), "sync": _sync, "heute": dt.date.today().isoformat()})
        elif pfad.startswith("/datei/"):
            self._datei(urllib.parse.unquote(pfad[len("/datei/"):]))
        else:
            self.send_error(404)

    def do_POST(self):
        pfad = urllib.parse.urlparse(self.path).path
        # Nur Anfragen von dieser Seite selbst annehmen
        herkunft = self.headers.get("Origin")
        if herkunft and herkunft not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self._json({"fehler": "fremde Herkunft"}, 403)
        try:
            p = self._body()
            if pfad == "/api/start":
                return self._json({"id": starte_job(p)})
            if pfad == "/api/stop":
                return self._json({"ok": stoppe_job(str(p.get("id")))})
            if pfad == "/api/clipstatus":
                return self._json({"ok": setze_status(str(p["id"]), str(p["status"]))})
            if pfad == "/api/sync":
                starte_sync()
                return self._json({"sync": _sync})
            if pfad == "/api/verbindungen":
                return self._json({"verbindungen": verbindungen_speichern(p)})
            if pfad == "/api/kanal":
                eintrag = {"datum": str(p.get("datum") or dt.date.today().isoformat())}
                for k in ("abos", "stunden", "shorts90", "tt_follower", "tt30"):
                    if p.get(k) not in (None, ""):
                        eintrag[k] = float(p[k])
                return self._json({"kanal": kanal_speichern(eintrag)})
        except (ValueError, KeyError) as e:
            return self._json({"fehler": str(e)}, 400)
        self.send_error(404)

    def _datei(self, rel: str):
        datei = (AUSGABE / rel).resolve()
        if AUSGABE.resolve() not in datei.parents or not datei.is_file():
            return self.send_error(404)
        groesse = datei.stat().st_size
        typ = mimetypes.guess_type(datei.name)[0] or "application/octet-stream"
        start, ende = 0, groesse - 1
        bereich = self.headers.get("Range")
        if bereich and bereich.startswith("bytes="):
            a, _, b = bereich[6:].partition("-")
            start = int(a) if a else 0
            ende = int(b) if b else groesse - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{ende}/{groesse}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(ende - start + 1))
        self.end_headers()
        with open(datei, "rb") as f:
            f.seek(start)
            rest = ende - start + 1
            try:
                while rest > 0:
                    block = f.read(min(1 << 20, rest))
                    if not block:
                        break
                    self.wfile.write(block)
                    rest -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Dashboard: http://127.0.0.1:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
