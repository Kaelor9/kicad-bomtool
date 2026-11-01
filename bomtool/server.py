"""Local web server (127.0.0.1 only). Standard library only."""
import json
import mimetypes
import os
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import __version__, config, datasheet, fpcompare, history, updater
from .analyze import Analysis, run_alternatives
from .providers import ProviderError, make_providers, mouser_cart

WEB = os.path.join(os.path.dirname(__file__), "web")
MAX_UPLOAD = 400 * 1024 * 1024
UPLOADS = {}        # token -> (name, bytes, time)
JOBS = {}           # id -> dict
LOCK = threading.Lock()


def _cleanup():
    now = time.time()
    with LOCK:
        for t in [t for t, v in UPLOADS.items() if now - v[2] > 3600]:
            del UPLOADS[t]
        for j in [j for j, v in JOBS.items() if now - v["time"] > 6 * 3600]:
            del JOBS[j]


def _run_job(job_id, body):
    job = JOBS[job_id]

    def progress(msg, pct):
        job["msg"], job["progress"] = msg, round(pct)

    try:
        def files(kind):
            out = []
            for t in body.get(kind, []):
                if t not in UPLOADS:
                    raise ValueError("En uploadet fil er udløbet – upload den igen.")
                out.append(UPLOADS[t][:2])
            return out
        settings = body.get("settings") or {}
        analysis = Analysis(files("project"), files("dist"), files("refs"), settings, config.load(), progress)
        job["result"] = analysis.run()
        if settings.get("save_history", True):
            try:
                job["result"]["history_id"] = history.save(job["result"])["id"]
            except OSError as e:
                job["result"]["errors"].append(f"Kunne ikke gemme i historikken: {e}")
        job["state"] = "done"
    except Exception as e:  # noqa: BLE001 - surfaced to the user in the UI
        traceback.print_exc()
        job["state"], job["error"] = "error", str(e) or e.__class__.__name__


def _line(job, line_id):
    if not job or job.get("state") != "done":
        return None
    return next((l for l in job["result"]["lines"] if l["id"] == line_id), None)


class Handler(BaseHTTPRequestHandler):
    server_version = "bomtool"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False, default=lambda o: list(o) if isinstance(o, (set, tuple)) else str(o)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("Filen er for stor.")
        return self.rfile.read(n) if n else b""

    def _same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = urlparse(origin).netloc
        return host == self.headers.get("Host")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        if path.startswith("/api/job/"):
            job = JOBS.get(path.rsplit("/", 1)[-1])
            if not job:
                return self._json({"error": "Ukendt job"}, 404)
            out = {k: job[k] for k in ("state", "msg", "progress", "error") if k in job}
            if job["state"] == "done":
                out["result"] = job["result"]
            return self._json(out)
        if path == "/api/settings":
            return self._json(config.masked(config.load()))
        if path == "/api/history":
            return self._json(history.entries())
        if path == "/api/version":
            force = "force" in (urlparse(self.path).query or "")
            if not force and config.load().get("check_updates", "1") != "1":
                return self._json({"current": __version__, "newer": False, "disabled": True})
            return self._json(updater.check(force))
        if path.startswith("/api/datasheet/"):
            # /api/datasheet/<job>/<line id> - the cached PDF, so the window can show the drawing page
            parts = path.split("/")
            job = JOBS.get(parts[3]) if len(parts) > 4 else None
            line = _line(job, unquote(parts[4])) if job else None
            if not line or not (line.get("datasheet") or "").startswith("http"):
                self.send_error(404)
                return
            try:
                data = datasheet.fetch(line["datasheet"])
            except ValueError as e:
                return self._json({"error": str(e)}, 502)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return
        fpath = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fpath.startswith(WEB) or not os.path.isfile(fpath):
            self.send_error(404)
            return
        with open(fpath, "rb") as fh:
            data = fh.read()
        ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._same_origin():
            return self._json({"error": "Forkert origin"}, 403)
        path = urlparse(self.path).path
        try:
            if path == "/api/upload":
                _cleanup()
                name = self.headers.get("X-Filename", "fil")
                name = unquote(name)
                data = self._body()
                token = uuid.uuid4().hex
                with LOCK:
                    UPLOADS[token] = (name, data, time.time())
                return self._json({"id": token, "name": name, "size": len(data)})
            body = json.loads(self._body() or b"{}")
            if path == "/api/analyze":
                job_id = uuid.uuid4().hex
                JOBS[job_id] = {"state": "running", "msg": "Starter …", "progress": 0, "time": time.time()}
                threading.Thread(target=_run_job, args=(job_id, body), daemon=True).start()
                return self._json({"job": job_id})
            if path == "/api/alternatives":
                job = JOBS.get(body.get("job"))
                if not job or job["state"] != "done":
                    return self._json({"error": "Analysen findes ikke længere – kør den igen."}, 404)
                settings = dict(job["result"].get("settings") or {})
                res = run_alternatives(job["result"], body.get("line"), config.load(), settings)
                return self._json(res)
            if path == "/api/fpcompare":
                job = JOBS.get(body.get("job"))
                line = _line(job, body.get("line"))
                if not line:
                    return self._json({"error": "Analysen findes ikke længere – kør den igen."}, 404)
                return self._json(fpcompare.build(line))
            if path == "/api/update":
                msg = updater.install()
                # Answer first, then leave so the new version can take over.
                threading.Timer(1.0, lambda: os._exit(0)).start()
                return self._json({"ok": True, "msg": msg})
            if path == "/api/history/open":
                data = history.load(body.get("id"))
                job_id = uuid.uuid4().hex
                JOBS[job_id] = {"state": "done", "msg": "", "progress": 100, "time": time.time(), "result": data["result"]}
                return self._json({"job": job_id, "result": data["result"]})
            if path == "/api/history/delete":
                history.delete(body.get("id"))
                return self._json({"ok": True})
            if path == "/api/compare":
                job = JOBS.get(body.get("job"))
                if not job or job["state"] != "done":
                    return self._json({"error": "Analysen findes ikke længere – kør den igen."}, 404)
                old = history.load(body.get("id"))
                out = history.diff(old["result"], job["result"])
                out["old_meta"] = old["meta"]
                return self._json(out)
            if path == "/api/cart/mouser":
                job = JOBS.get(body.get("job"))
                if not job or job["state"] != "done":
                    return self._json({"error": "Analysen findes ikke længere – kør den igen."}, 404)
                items = []
                for l in job["result"]["lines"]:
                    b = (l.get("plan") or {}).get("per_seller", {}).get(body.get("seller") or "Mouser")
                    if b and b.get("sku"):
                        items.append((b["sku"], b["qty"], ",".join(l["refs"])))
                if not items:
                    return self._json({"error": "Ingen linjer har et Mouser-varenummer."}, 400)
                try:
                    return self._json(mouser_cart(config.load(), items))
                except ProviderError as e:
                    return self._json({"error": str(e)}, 502)
            if path == "/api/settings":
                cfg = config.save(body)
                return self._json(config.masked(cfg))
            if path == "/api/test-keys":
                cfg = config.load()
                out = {}
                for prov in make_providers(cfg):
                    try:
                        parts = prov.lookup("LM317T")
                        out[prov.name] = {"ok": True, "msg": f"OK – fandt {len(parts)} resultat(er)."}
                    except ProviderError as e:
                        out[prov.name] = {"ok": False, "msg": str(e)}
                    except Exception as e:  # noqa: BLE001
                        out[prov.name] = {"ok": False, "msg": f"Fejl: {e}"}
                if not out:
                    out["-"] = {"ok": False, "msg": "Ingen nøgler indtastet."}
                return self._json(out)
            return self._json({"error": "Ukendt adresse"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)


def make_server(port=8765):
    """Bind 127.0.0.1 on the first free port from `port`. Returns (server, url)."""
    for p in [port] + list(range(port + 1, port + 20)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            return server, f"http://127.0.0.1:{p}/"
        except OSError:
            continue
    raise SystemExit("Kunne ikke finde en ledig port.")


def serve(port=8765, open_browser=True):
    server, url = make_server(port)
    print(f"KiCad BOM-værktøj kører på {url}  (Ctrl+C for at stoppe)")
    if open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
