"""Petit serveur local : l'interface s'ouvre dans le navigateur, tout reste sur l'ordinateur."""
import base64
import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from . import catalog, errlog, importer, isbn as isbnlib, pages as pagelib, render_pdf, render_pptx, render_png, sources, store, updater, version

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ID = "cmpl-catalogue"
PORT = 8766
TOKEN = secrets.token_urlsafe(16)
_state = {"bye_at": None}
LOCK = threading.RLock()
CAT = {"meta": {"titre": "", "date": ""}, "books": []}
JOB = {"job": None}


# ------------------------------------------------------------------ catalogue en mémoire
def load():
    global CAT
    CAT = store.load_catalogue()
    CAT.setdefault("meta", {"titre": "", "date": ""})
    CAT.setdefault("books", [])
    for b in CAT["books"]:                       # rétablit les champs ajoutés dans des versions plus récentes
        for k, v in catalog.new_book(b.get("isbn", "")).items():
            b.setdefault(k, v)


def save():
    with LOCK:
        store.save_catalogue(CAT)


def find(isbn):
    for b in CAT["books"]:
        if b["isbn"] == isbn:
            return b
    return None


def public_state():
    s = store.load_settings()
    return {"meta": CAT["meta"], "books": [catalog.public(b) for b in CAT["books"]], "settings": public_settings(s)}


def public_settings(s):
    out = dict(s)
    ck = out.pop("claude_key", "")
    out["claude_key_set"] = bool(ck)
    out["claude_key_hint"] = ("•••• " + ck[-4:]) if len(ck) >= 8 else ("••••" if ck else "")
    out.pop("ai_model", None)
    k = out.pop("google_key", "")
    out["google_key_set"] = bool(k)
    out["google_key_hint"] = ("•••• " + k[-4:]) if len(k) >= 8 else ("••••" if k else "")
    return out


def safe_name(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 _.-]+", "", t).strip(" .")
    return t or "Catalogue"


def add_rows(rows, replace=False):
    with LOCK:
        if replace:
            CAT["books"] = []
        added = 0
        for r in rows:
            b = find(r["isbn"])
            if b is None:
                CAT["books"].append(catalog.from_import_row(r))
                added += 1
            else:
                catalog.apply_row(b, r)
                catalog.use_dilicom_fallback(b) if b.get("fetched") else None
        save()
    return added


# ------------------------------------------------------------------ récupération en tâche de fond
def start_fetch(isbns, force=False):
    with LOCK:
        j = JOB["job"]
        if j and j.running:
            return j
        settings = store.load_settings()
        job = catalog.FetchJob(isbns, settings)
        JOB["job"] = job

    def get_book(i):
        with LOCK:
            b = find(i)
            return dict(b, edited=list(b["edited"])) if b else None

    def set_book(nb, ia=False):
        with LOCK:
            b = find(nb["isbn"])
            if b is not None:
                for k, v in nb.items():
                    if k == "edited" or (k in b["edited"] and k in EDITABLE):   # on ne touche pas à ce que l'utilisateur a saisi
                        continue
                    b[k] = v
                save()

    threading.Thread(target=catalog.run_fetch, args=(job, get_book, set_book, force), daemon=True, name="recuperation").start()
    return job


def start_ai(isbns):
    with LOCK:
        j = JOB["job"]
        if j and j.running:
            return j
        job = catalog.FetchJob(isbns, store.load_settings())
        job.kind = "ai"
        JOB["job"] = job

    def get_book(i):
        with LOCK:
            b = find(i)
            return dict(b, edited=list(b["edited"])) if b else None

    def set_book(nb, ia=False):
        with LOCK:
            b = find(nb["isbn"])
            if b is not None:
                b["resume"], b["resume_ia"] = nb["resume"], True
                if "resume" not in b["edited"]:
                    b["edited"].append("resume")
                save()

    threading.Thread(target=catalog.run_ai, args=(job, get_book, set_book), daemon=True, name="ia").start()
    return job


# ------------------------------------------------------------------ aperçu et génération
def build_pages():
    with LOCK:
        books = [dict(b) for b in CAT["books"]]
    return pagelib.build_pages(books, CAT["meta"].get("titre") or "Catalogue")


def preview(page=0, dpi=90):
    pgs = build_pages()
    page = max(0, min(int(page), len(pgs) - 1))
    pg = pgs[page]
    img = render_png.render_page(pg, dpi=dpi)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    k = dpi / 25.4
    hot = [{"isbn": h["isbn"], "x": h["x"] * k, "y": h["y"] * k, "w": h["w"] * k, "h": h["h"] * k} for h in pg.hot]
    where = {}
    for i, p in enumerate(pgs):
        for h in p.hot:
            where[h["isbn"]] = i
    return {"count": len(pgs), "page": page, "image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "w": img.width, "h": img.height, "hot": hot, "where": where}


def generate(out_dir, name, want_pdf=True, want_pptx=False):
    with LOCK:
        books = [dict(b) for b in CAT["books"]]
    if not books:
        raise ValueError("Le catalogue est vide.")
    name = safe_name(name or CAT["meta"].get("titre") or "Catalogue")
    folder = os.path.join(os.path.abspath(os.path.expanduser(out_dir)), name)
    os.makedirs(folder, exist_ok=True)
    pgs = pagelib.build_pages(books, name)
    files = []
    if want_pdf:
        p = os.path.join(folder, name + ".pdf")
        render_pdf.build_pdf(pgs, p, title=name, author="CMPL")
        files.append(p)
    if want_pptx:
        p = os.path.join(folder, name + ".pptx")
        render_pptx.build_pptx(pgs, p, title=name)
        files.append(p)
    return {"folder": folder, "files": files, "pages": len(pgs)}


# ------------------------------------------------------------------ utilitaires système
def browse_folder(initial):
    initial = initial if initial and os.path.isdir(initial) else os.path.expanduser("~")
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(initialdir=initial, title="Choisir un dossier", parent=root)
        root.destroy()
        return path or ""
    except Exception:
        pass
    if sys.platform.startswith("win"):
        ps = ("Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; "
              f"$f.SelectedPath = '{initial}'; if ($f.ShowDialog() -eq 'OK') {{ Write-Output $f.SelectedPath }}")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 creationflags=0x08000000, timeout=300)
            return out.stdout.strip()
        except Exception:
            return ""
    return ""


def open_folder(path, create=False):
    path = os.path.abspath(path)
    if create:
        os.makedirs(path, exist_ok=True)
    if not os.path.isdir(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def open_file(path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


EDITABLE = ("titre", "auteurs", "resume", "date", "collection", "editeur", "pages", "illustrations", "dimensions", "prix")


def update_book(isbn, fields):
    with LOCK:
        b = find(isbn)
        if b is None:
            raise ValueError("livre introuvable")
        if fields.get("resume_ia") is False:
            b["resume_ia"] = False
        for k, v in fields.items():
            if k not in EDITABLE:
                continue
            if k == "resume" and v != b.get("resume"):
                b["resume_ia"] = False
            if k == "auteurs":
                v = [x.strip() for x in (v if isinstance(v, list) else str(v).split("\n")) if x.strip()]
            elif k == "prix":
                v = importer.parse_price(v)
            else:
                v = str(v or "").strip() if k != "resume" else re.sub(r"\s+", " ", str(v or "")).strip()
            b[k] = v
            if k != "prix" and k not in b["edited"]:
                b["edited"].append(k)
        save()
        return catalog.public(b)


def set_prices(prices):
    with LOCK:
        n = 0
        for isbn, v in (prices or {}).items():
            b = find(isbn)
            if b is None:
                continue
            p = importer.parse_price(v)
            if p is not None or v in ("", None):
                b["prix"] = p
                n += 1
        save()
        return n


def set_cover(isbn, data):
    with LOCK:
        b = find(isbn)
        if b is None:
            raise ValueError("livre introuvable")
        covers_dir = store.load_settings()["covers_dir"]
        try:
            path = sources.save_cover_bytes(data, covers_dir, isbn)
        except Exception:
            raise ValueError("Ce fichier n'est pas une image lisible (JPG, PNG…).")
        b["cover_path"], b["cover_origin"] = path, "manuel"
        save()
        return catalog.public(b)


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "CMPLCat/1.0"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def _token_ok(self):
        if self.headers.get("X-Token") == TOKEN:
            return True
        return ("t=" + TOKEN) in (self.path.split("?", 1)[1] if "?" in self.path else "")

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf8")
        elif isinstance(body, str):
            body = body.encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "host"})
        path, _, query = self.path.partition("?")
        _state["bye_at"] = None
        if path == "/":
            with open(os.path.join(HERE, "web", "index.html"), encoding="utf8") as fh:
                html = fh.read().replace("__TOKEN__", TOKEN)
            return self._send(200, html, "text/html; charset=utf-8")
        if path in ("/favicon.png", "/favicon.ico"):
            with open(os.path.join(HERE, "web", "favicon.png"), "rb") as fh:
                return self._send(200, fh.read(), "image/png")
        if path == "/api/ping":
            return self._send(200, {"app": APP_ID})
        if not self._token_ok():
            return self._send(403, {"error": "forbidden"})
        if path == "/api/bootstrap":
            return self._send(200, dict(public_state(), version=version.VERSION))
        if path == "/api/template":
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                fp = os.path.join(tmp, "m.xlsx")
                importer.make_template(fp)
                data = open(fp, "rb").read()
            return self._send(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              {"Content-Disposition": 'attachment; filename="Modele-ISBN-catalogue-CMPL.xlsx"'})
        if path == "/api/cover":
            m = re.search(r"isbn=(\d+)", query)
            b = find(m.group(1)) if m else None
            if not b or not b.get("cover_path") or not os.path.isfile(b["cover_path"]):
                return self._send(404, {"error": "pas de couverture"})
            im = Image.open(b["cover_path"])
            im.thumbnail((260, 360))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=85)
            return self._send(200, buf.getvalue(), "image/jpeg", {"Cache-Control": "no-cache"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok() or not self._token_ok():
            return self._send(403, {"error": "forbidden"})
        path = self.path.split("?", 1)[0]
        if path != "/api/bye":
            _state["bye_at"] = None
        try:
            b = self._json()
            if path == "/api/bye":
                _state["bye_at"] = time.time()
                return self._send(200, {})
            if path == "/api/state":
                return self._send(200, public_state())
            if path == "/api/import":
                rows, problems = importer.read_rows(base64.b64decode(b["data"]), b.get("filename", ""))
                added = add_rows(rows, replace=bool(b.get("replace")))
                return self._send(200, {"added": added, "problems": problems, "state": public_state()})
            if path == "/api/add_isbns":
                found = re.findall(r"[0-9][0-9\- ]{8,15}[0-9Xx]", b.get("text", ""))
                rows, bad = [], []
                for f in found:
                    d = isbnlib.to13(f)
                    (rows if d else bad).append({"isbn": d} if d else f)
                if not found and b.get("text", "").strip():
                    bad.append(b["text"].strip()[:40])
                added = add_rows(rows)
                return self._send(200, {"added": added, "problems": [f"« {x} » n'est pas un ISBN valide." for x in bad],
                                        "state": public_state()})
            if path == "/api/fetch":
                with LOCK:
                    if b.get("isbns"):
                        todo = [i for i in b["isbns"] if find(i)]
                    elif b.get("all"):
                        todo = [x["isbn"] for x in CAT["books"]]
                    else:
                        todo = [x["isbn"] for x in CAT["books"] if not x.get("fetched")]
                job = start_fetch(todo, force=bool(b.get("force")))
                return self._send(200, {"total": len(job.isbns), "running": job.running})
            if path == "/api/ai":
                s = store.load_settings()
                if not s.get("claude_key"):
                    return self._send(400, {"error": "Pas de clé Claude : ajoute-la dans les Réglages."})
                with LOCK:
                    if b.get("isbns"):
                        todo = [i for i in b["isbns"] if find(i)]
                    elif b.get("all"):
                        todo = [x["isbn"] for x in CAT["books"] if x.get("titre")]
                    else:
                        todo = [x["isbn"] for x in CAT["books"] if x.get("titre") and not x.get("resume")]
                if not todo:
                    return self._send(200, {"total": 0, "running": False})
                job = start_ai(todo)
                return self._send(200, {"total": len(job.isbns), "running": job.running})
            if path == "/api/fetch/status":
                j = JOB["job"]
                if not j:
                    return self._send(200, {"running": False, "done": 0, "total": 0, "updated": []})
                since = int(b.get("since", 0))
                with LOCK:
                    upd = [catalog.public(find(i)) for i in j.updated[since:] if find(i)]
                return self._send(200, {"running": j.running, "done": j.done, "total": len(j.isbns), "updated": upd,
                                        "next": len(j.updated), "kind": j.kind, "errors": list(j.errors)})
            if path == "/api/fetch/cancel":
                if JOB["job"]:
                    JOB["job"].cancel = True
                return self._send(200, {})
            if path == "/api/prices":
                n = set_prices(b.get("prices") or {})
                return self._send(200, {"n": n, "state": public_state()})
            if path == "/api/book/update":
                return self._send(200, {"book": update_book(b["isbn"], b["fields"])})
            if path == "/api/book/remove":
                with LOCK:
                    CAT["books"] = [x for x in CAT["books"] if x["isbn"] != b["isbn"]]
                    save()
                return self._send(200, {"state": public_state()})
            if path == "/api/book/move":
                with LOCK:
                    L = CAT["books"]
                    i = next((k for k, x in enumerate(L) if x["isbn"] == b["isbn"]), None)
                    if i is not None:
                        j = max(0, min(len(L) - 1, i + int(b.get("dir", 0))))
                        L.insert(j, L.pop(i))
                        save()
                return self._send(200, {"state": public_state()})
            if path == "/api/clear":
                n = 0
                with LOCK:
                    CAT["books"] = []
                    CAT["meta"] = {"titre": "", "date": ""}
                    save()
                if b.get("cache"):
                    store.clear_cache()
                if b.get("covers_folder"):
                    n = sources.delete_cover_files(store.load_settings().get("covers_dir", ""))
                return self._send(200, {"state": public_state(), "deleted": n})
            if path == "/api/update/status":
                return self._send(200, updater.status())
            if path == "/api/update/check":
                if updater.STATE["state"] not in ("downloading", "ready", "checking"):
                    updater.start_check(0.0, silent=False)
                return self._send(200, updater.status())
            if path == "/api/update/start":
                updater.start_download()
                return self._send(200, updater.status())
            if path == "/api/update/cancel":
                updater.cancel()
                return self._send(200, updater.status())
            if path == "/api/update/apply":
                try:
                    updater.apply()
                except Exception as e:
                    updater._set(state="error", error=f"Installation impossible : {e}")
                    return self._send(200, updater.status())
                self._send(200, updater.status())
                threading.Timer(0.4, lambda: os._exit(0)).start()
                return
            if path == "/api/meta":
                with LOCK:
                    CAT["meta"].update({k: str(v) for k, v in b.items() if k in ("titre", "date")})
                    save()
                return self._send(200, {})
            if path == "/api/cover/upload":
                return self._send(200, {"book": set_cover(b["isbn"], base64.b64decode(b["data"]))})
            if path == "/api/cover/clear":
                with LOCK:
                    x = find(b["isbn"])
                    if x:
                        x["cover_path"], x["cover_origin"] = "", "retiré"
                        save()
                        return self._send(200, {"book": catalog.public(x)})
                return self._send(404, {"error": "livre introuvable"})
            if path == "/api/cover/confirm":
                with LOCK:
                    x = find(b["isbn"])
                    if x and (x.get("cover_origin") or "").endswith("?"):
                        x["cover_origin"] = x["cover_origin"][:-1]
                        save()
                    return self._send(200, {"book": catalog.public(x)})
            if path == "/api/cover/confirm_all":
                n = 0
                with LOCK:
                    for x in CAT["books"]:
                        if (x.get("cover_origin") or "").endswith("?") and x.get("cover_path"):
                            x["cover_origin"] = x["cover_origin"][:-1]
                            n += 1
                    save()
                return self._send(200, {"n": n, "state": public_state()})
            if path == "/api/preview":
                return self._send(200, preview(b.get("page", 0), int(b.get("dpi", 90))))
            if path == "/api/generate":
                s = store.load_settings()
                r = generate(b.get("out_dir") or s["out_dir"], b.get("name", ""), bool(b.get("pdf", True)), bool(b.get("pptx", False)))
                return self._send(200, r)
            if path == "/api/settings":
                patch = {k: v for k, v in b.items() if k in store.SETTING_KEYS}
                if "google_key" in patch:
                    patch["google_key"] = str(patch["google_key"] or "").strip()
                    if patch["google_key"].startswith("••"):
                        patch.pop("google_key")
                if "claude_key" in patch:
                    patch["claude_key"] = str(patch["claude_key"] or "").strip()
                    if patch["claude_key"].startswith("••"):
                        patch.pop("claude_key")
                store.update_settings(patch)
                return self._send(200, {"settings": public_settings(store.load_settings())})
            if path == "/api/browse":
                return self._send(200, {"path": browse_folder(b.get("initial"))})
            if path == "/api/open_folder":
                return self._send(200, {"ok": open_folder(b.get("path", ""), bool(b.get("create")))})
            if path == "/api/open_file":
                return self._send(200, {"opened": open_file(b.get("path", ""))})
            if path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Timer(0.3, lambda: os._exit(0)).start()
                return
        except Exception as e:
            errlog.record(path, e)
            import traceback
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": "not found"})


def _watchdog():
    while True:
        time.sleep(1.0)
        t = _state.get("bye_at")
        if t and time.time() - t > 8:
            os._exit(0)


def already_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=1.5) as r:
            return json.loads(r.read().decode()).get("app") == APP_ID
    except Exception:
        return False


def main(open_browser=True, relance=False):
    import webbrowser
    if relance:                                   # on attend que l'ancienne version ait libéré le port
        for _ in range(60):
            if not already_running():
                break
            time.sleep(0.25)
    if already_running():
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return
    load()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=_watchdog, daemon=True).start()
    errlog.install_thread_hook()
    updater.cleanup_old()
    updater.start_check(delay=2.5)
    url = f"http://127.0.0.1:{port}/"
    if sys.stdout:
        print(f"Générateur de catalogue CMPL : {url}\nFerme l'onglet pour arrêter.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
