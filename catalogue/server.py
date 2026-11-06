"""Petit serveur local : l'interface s'ouvre dans le navigateur, tout reste sur l'ordinateur."""
import base64
import copy
from collections import OrderedDict
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

from . import fixed as fixedlib, catalog, prix as prixlib, errlog, importer, isbn as isbnlib, pages as pagelib, libs, render_pdf, render_pptx, render_png, sources, store, updater, version

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
    _normalize()                                 # rétablit les champs ajoutés dans des versions plus récentes
    HIST.update(stack=[_snap()], idx=0, t=0.0, jobstep=False)


REV = {"n": 0}                       # change à chaque modification : invalide la mise en page et les images d'aperçu
LAY_LOCK = threading.Lock()
LAY = {"rev": -1, "all": ([], [], [], [])}
PNG_LOCK = threading.Lock()
PNGS = OrderedDict()


HIST = {"stack": [], "idx": -1, "t": 0.0, "jobstep": False}
HIST_MAX = 60


def _snap():
    return json.dumps(CAT, ensure_ascii=False, sort_keys=True)


def _job_running():
    j = JOB.get("job")
    return bool(j and j.running)


def _hist_push():
    """Mémorise l'état courant pour « Annuler ». Les modifications rapprochées (saisie, récupération en lot) forment une seule étape."""
    s = _snap()
    st, i = HIST["stack"], HIST["idx"]
    if i >= 0 and st[i] == s:
        return
    now = time.time()
    running = _job_running()
    merge = i >= 1 and i == len(st) - 1 and ((running and HIST["jobstep"]) or (not running and not HIST["jobstep"] and now - HIST["t"] < 1.2))
    if merge:
        st[i] = s
    else:
        del st[i + 1:]
        st.append(s)
        if len(st) > HIST_MAX:
            del st[0]
        HIST["idx"] = len(st) - 1
    HIST["jobstep"] = running
    HIST["t"] = now


def hist_state():
    return {"undo": HIST["idx"] > 0, "redo": HIST["idx"] < len(HIST["stack"]) - 1}


def _autosave_lib():
    cid = CAT["meta"].get("lib_id")
    if cid:
        try:
            libs.save_catalogue(CAT, libs.load_catalogue(cid).get("nom"), cid)
        except Exception:
            CAT["meta"].pop("lib_id", None)


def save():
    with LOCK:
        REV["n"] += 1
        _hist_push()
        store.save_catalogue(CAT)
        _autosave_lib()


def _normalize():
    CAT.setdefault("meta", {"titre": "", "date": ""})
    CAT.setdefault("books", [])
    for b in CAT["books"]:
        for k, v in catalog.new_book(b.get("isbn", "")).items():
            b.setdefault(k, v)


def replace_catalogue(new, reason="remplace", history=True):
    """Remplace tout le catalogue en cours (ouverture, restauration, annulation), avec une copie de secours avant."""
    with LOCK:
        if reason and reason != "annuler":
            libs.backup(CAT, reason)
        CAT.clear()
        CAT.update(copy.deepcopy(new))
        _normalize()
        REV["n"] += 1
        if history:
            _hist_push()
        store.save_catalogue(CAT)
        _autosave_lib()


def undo_redo(step):
    with LOCK:
        if _job_running():
            raise ValueError("Attends la fin de la récupération en cours.")
        i = HIST["idx"] + step
        if not 0 <= i < len(HIST["stack"]):
            raise ValueError("Rien à annuler." if step < 0 else "Rien à rétablir.")
        HIST["idx"] = i
        HIST["jobstep"] = False
        HIST["t"] = 0.0
        CAT.clear()
        CAT.update(json.loads(HIST["stack"][i]))
        _normalize()
        REV["n"] += 1
        store.save_catalogue(CAT)
        _autosave_lib()


def find(isbn):
    for b in CAT["books"]:
        if b["isbn"] == isbn:
            return b
    return None


def public_state():
    s = store.load_settings()
    lib = None
    if CAT["meta"].get("lib_id"):
        try:
            lib = {"id": CAT["meta"]["lib_id"], "nom": libs.load_catalogue(CAT["meta"]["lib_id"]).get("nom", "")}
        except Exception:
            CAT["meta"].pop("lib_id", None)
    return {"meta": CAT["meta"], "books": [catalog.public(b) for b in CAT["books"]], "settings": public_settings(s), "lib": lib, "themes": [list(t) for t in fixedlib.THEMES]}


def public_settings(s):
    out = dict(s)
    ck = out.pop("claude_key", "")
    out["claude_key_set"] = bool(ck)
    out["claude_key_hint"] = ("•••• " + ck[-4:]) if len(ck) >= 8 else ("••••" if ck else "")
    out.pop("ai_model", None)
    out["conditions_defaut"] = fixedlib.CONDITIONS
    k = out.pop("google_key", "")
    out["google_key_set"] = bool(k)
    out["google_key_hint"] = ("•••• " + k[-4:]) if len(k) >= 8 else ("••••" if k else "")
    return out


def safe_name(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 _.-]+", "", t).strip(" .")
    return t or "Catalogue"


def add_rows(rows, replace=False):
    """Ajoute ou met à jour des livres. Retourne (nombre ajouté, prix modifiés)."""
    changes = []
    with LOCK:
        if replace:
            libs.backup(CAT, "import")
            CAT["books"] = []
        added = 0
        for r in rows:
            b = find(r["isbn"])
            if b is None:
                CAT["books"].append(catalog.from_import_row(r))
                added += 1
            else:
                old = b.get("prix")
                catalog.apply_row(b, r)
                catalog.use_dilicom_fallback(b) if b.get("fetched") else None
                new = b.get("prix")
                if old not in (None, "") and new not in (None, "") and abs(float(old) - float(new)) > 0.004:
                    b["prix_ancien"] = old
                    changes.append({"isbn": b["isbn"], "titre": b.get("titre") or b["isbn"], "ancien": old, "nouveau": new})
        save()
    return added, changes


# ------------------------------------------------------------------ tri
def _fold(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"^(le|la|les|l'|un|une|des|the)\s+", "", t)


def _date_key(b):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", b.get("date") or "") or re.search(r"()(\d{1,2})/(\d{4})", b.get("date") or "")
    if m:
        g = m.groups()
        return (int(g[2]), int(g[1]), int(g[0] or 0))
    m = re.search(r"(\d{4})", b.get("date") or "")
    return (int(m.group(1)), 0, 0) if m else (0, 0, 0)


def sort_books(key):
    keys = {"titre": lambda b: _fold(b.get("titre")) or "~",
            "auteur": lambda b: _fold((b.get("auteurs") or [""])[0]) or "~",
            "editeur": lambda b: _fold(b.get("editeur")) or "~",
            "rubrique": lambda b: (not (b.get("rubrique") or "").strip(), _fold(b.get("rubrique"))),
            "prix": lambda b: (b.get("prix") in (None, ""), float(b.get("prix") or 0)),
            "date": lambda b: tuple(-x for x in _date_key(b))}
    if key not in keys:
        raise ValueError("tri inconnu")
    with LOCK:
        CAT["books"].sort(key=keys[key])
        save()


# ------------------------------------------------------------------ contrôle avant génération
def check():
    """Liste ce qui reste à vérifier : groupes de livres + informations sur les pages."""
    with LOCK:
        books = [dict(b) for b in CAT["books"]]
    groups = {}

    def add(key, label, level, b):
        g = groups.setdefault(key, {"key": key, "label": label, "level": level, "items": []})
        g["items"].append({"isbn": b["isbn"], "titre": b.get("titre") or b["isbn"]})

    for b in books:
        if not b.get("fetched"):
            add("nofetch", "pas encore cherchés", "warn", b)
            continue
        if not b.get("titre"):
            add("notitre", "sans titre (introuvables)", "bad", b)
        else:
            for m in catalog.missing(b):
                add("m_" + m, {"auteurs": "sans auteur", "résumé": "sans résumé", "date de parution": "sans date de parution",
                                "éditeur": "sans éditeur", "couverture": "sans couverture", "prix": "sans prix"}.get(m, "sans " + m), "bad" if m in ("prix", "couverture") else "warn", b)
        if (b.get("cover_origin") or "").endswith("?") and b.get("cover_path"):
            add("covq", "couverture à vérifier", "warn", b)
        if b.get("resume_ia") and b.get("resume"):
            add("ia", "résumé écrit par l'IA, à relire", "info", b)
        if b.get("titre_origin") == "dilicom" and "titre" not in b.get("edited", []):
            add("dtitre", "titre à vérifier (sans accents)", "warn", b)
        al = catalog.dispo_alert(b.get("dispo"))
        if al:
            add("dispo_" + al, f"Dilicom : {al}", "warn", b)
    order = {"bad": 0, "warn": 1, "info": 2}
    out = sorted(groups.values(), key=lambda g: order[g["level"]])
    fr, bp, pp, post = build_all()
    blanks = sum(1 for p in post if p.name == "Page blanche")
    last = 0
    if bp:
        ids = {h["isbn"] for h in bp[-1].hot}
        last = len(ids)
    return {"groups": out, "total": len(books), "pages": len(fr) + len(bp) + len(pp) + len(post), "blanches": blanks,
            "pages_livres": len(bp), "dernier_nb": last}


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
def garde_image():
    p = os.path.join(store.data_dir(), "garde.jpg")
    try:
        im = Image.open(p)
        im.load()
        return im.convert("RGB")
    except Exception:
        return None


def build_all(with_prices=None):
    """(page de garde, pages de livres, pages du tableau, pages finales) : les pages décochées sont absentes."""
    with LOCK:
        books = [dict(b) for b in CAT["books"]]
        meta = dict(CAT["meta"])
    s = store.load_settings()
    name = meta.get("titre") or "Catalogue"
    col = fixedlib.theme_color(meta.get("garde_couleur"))
    book_pages = pagelib.build_pages(books, name, col)
    if with_prices is None:
        with_prices = bool(s.get("inclure_prix", True))
    price_pages = prixlib.build_pages(books, meta.get("selection") or name, meta.get("indicatif", ""), s.get("taux") or 3366, s.get("arrondi") or 1) if (with_prices and books) else []
    front = [fixedlib.cover_page(meta, garde_image(), prixlib.mois_annee())] if s.get("p_garde", True) else []
    post = []
    if s.get("p_cond", True):
        post.append(fixedlib.conditions_page(s.get("conditions_texte") or ""))
    if s.get("p_proforma", True):
        post.append(fixedlib.proforma_page())
    if s.get("p_dos", True):
        post.append(fixedlib.back_page(col))
    if s.get("p_multi4", True):                    # impression en folio : nombre de pages multiple de 4, pages blanches avant la 4e de couverture
        reste = (-(len(front) + len(book_pages) + len(price_pages) + len(post))) % 4
        at = len(post) - 1 if s.get("p_dos", True) else len(post)
        for _ in range(reste):
            post.insert(at, fixedlib.blank_page())
    return front, book_pages, price_pages, post


def build_pages(with_prices=None):
    """(pages de livres, pages du tableau des prix)."""
    _, bp, pp, _ = build_all(with_prices)
    return bp, pp


def layout_pages():
    """(version, garde, livres, tableau, fin) : recalculé seulement si le catalogue a changé."""
    with LAY_LOCK:
        rev = REV["n"]
        if LAY["rev"] != rev:
            LAY.update(rev=rev, all=build_all())
            with PNG_LOCK:
                PNGS.clear()
        return (LAY["rev"],) + tuple(LAY["all"])


def _all_pages():
    rev, fr, bp, pp, post = layout_pages()
    labels = [p.name for p in fr] + [f"Page {i + 1}" for i in range(len(bp))] + \
             [f"Tableau des prix {i + 1}/{len(pp)}" for i in range(len(pp))] + [p.name for p in post]
    return rev, fr, bp, pp, post, fr + bp + pp + post, labels


def preview(page=0, dpi=100):
    rev, fr, bp, pp, post, pgs, labels = _all_pages()
    page = max(0, min(int(page), len(pgs) - 1))
    pg = pgs[page]
    k = dpi / 25.4
    hot = [dict(h, x=h["x"] * k, y=h["y"] * k, w=h["w"] * k, h=h["h"] * k) for h in getattr(pg, "hot", [])]
    where = {}
    for i, p in enumerate(bp):
        for h in p.hot:
            where.setdefault(h["isbn"], len(fr) + i)
    kinds = ["garde"] * len(fr) + ["livres"] * len(bp) + ["tableau"] * len(pp) + \
            [{"Conditions de vente": "conditions", "Demande de facture proforma": "proforma", "Page blanche": "blanche", "4e de couverture": "dos"}.get(p.name, "autre") for p in post]
    return {"count": len(pgs), "page": page, "label": labels[page], "rev": rev, "pages": [{"label": l, "kind": k} for l, k in zip(labels, kinds)], "table_start": len(fr) + len(bp) if pp else None,
            "w": round(pg.w * k), "h": round(pg.h * k), "hot": hot, "where": where}


def page_png(n, dpi=100):
    rev, fr, bp, pp, post, pgs, labels = _all_pages()
    n = max(0, min(int(n), len(pgs) - 1))
    key = (rev, n, dpi)
    with PNG_LOCK:
        data = PNGS.get(key)
    if data is None:
        buf = io.BytesIO()
        render_png.render_page(pgs[n], dpi=dpi).save(buf, "PNG", compress_level=1)
        data = buf.getvalue()
        with PNG_LOCK:
            PNGS[key] = data
            while len(PNGS) > 80:
                PNGS.popitem(last=False)
    return data


def generate(out_dir, name, want_pdf=True, want_pptx=False, want_xlsx=False):
    with LOCK:
        books = [dict(b) for b in CAT["books"]]
    if not books:
        raise ValueError("Le catalogue est vide.")
    name = safe_name(name or CAT["meta"].get("titre") or "Catalogue")
    folder = os.path.join(os.path.abspath(os.path.expanduser(out_dir)), name)
    os.makedirs(folder, exist_ok=True)
    libs.backup(CAT, "generation")
    fr, bp, pp, post = build_all()
    files = []
    if want_pdf:
        p = os.path.join(folder, name + ".pdf")
        render_pdf.build_pdf(fr + bp + pp + post, p, title=name, author="CMPL")
        files.append(p)
    if want_pptx:
        p = os.path.join(folder, name + ".pptx")
        render_pptx.build_pptx(fr + bp + pp + post, p, title=name)
        files.append(p)
    if want_xlsx:
        s = store.load_settings()
        meta = dict(CAT["meta"])
        p = os.path.join(folder, name + " - Tableau des prix.xlsx")
        prixlib.export_xlsx(p, books, meta.get("selection") or name, meta.get("indicatif", ""), s.get("taux") or 3366, s.get("arrondi") or 1)
        files.append(p)
    return {"folder": folder, "files": files, "pages": len(fr) + len(bp) + len(pp) + len(post), "tableau": len(pp)}


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


EDITABLE = ("titre", "auteurs", "resume", "date", "collection", "editeur", "pages", "illustrations", "dimensions", "prix",
            "edition", "taux", "titre_tableau", "prix_ar", "rubrique")


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
            elif k == "prix_ar":
                tv = re.sub(r"[^\d.,]", "", str(v or "")).replace(",", ".")
                try:
                    v = int(round(float(tv))) if tv else ""
                except ValueError:
                    v = ""
            elif k == "taux":
                tv = str(v or "").replace(",", ".").replace(" ", "")
                try:
                    v = (int(float(tv)) if float(tv) == int(float(tv)) else float(tv)) if tv else ""
                except ValueError:
                    v = ""
            else:
                v = str(v or "").strip() if k != "resume" else re.sub(r"\s+", " ", str(v or "")).strip()
            b[k] = v
            if k not in ("prix", "taux", "prix_ar") and k not in b["edited"]:
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
        if ctype.startswith("application/json"):
            h = hist_state()
            self.send_header("X-Hist", f"{int(h['undo'])}{int(h['redo'])}")
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
        if path == "/api/page.png":
            m = re.search(r"n=(\d+)", query)
            d = re.search(r"dpi=(\d+)", query)
            return self._send(200, page_png(int(m.group(1)) if m else 0, max(30, min(int(d.group(1)) if d else 100, 200))),
                              "image/png", {"Cache-Control": "private, max-age=600"})
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
                with LOCK:
                    libs.backup(CAT, "fermeture")
                return self._send(200, {})
            if path == "/api/state":
                return self._send(200, public_state())
            if path in ("/api/undo", "/api/redo"):
                undo_redo(-1 if path == "/api/undo" else 1)
                return self._send(200, {"state": public_state()})
            if path == "/api/prices/revert":
                with LOCK:
                    for i in b.get("isbns", []):
                        x = find(i)
                        if x is not None and x.get("prix_ancien") not in (None, ""):
                            x["prix"], x["prix_ancien"] = x["prix_ancien"], ""
                    save()
                return self._send(200, {"state": public_state()})
            if path == "/api/sort":
                sort_books(b.get("key", "titre"))
                return self._send(200, {"state": public_state()})
            if path == "/api/reorder":
                with LOCK:
                    L = CAT["books"]
                    mv = find(b.get("isbn"))
                    if mv is not None and b.get("isbn") != b.get("before"):
                        L.remove(mv)
                        j = next((k for k, x in enumerate(L) if x["isbn"] == b.get("before")), len(L))
                        L.insert(j, mv)
                        save()
                return self._send(200, {"state": public_state()})
            if path == "/api/rubrique":
                with LOCK:
                    for i in b.get("isbns", []):
                        x = find(i)
                        if x is not None:
                            x["rubrique"] = str(b.get("rubrique") or "").strip()
                    save()
                return self._send(200, {"state": public_state()})
            if path == "/api/check":
                return self._send(200, check())
            if path == "/api/lib/list":
                return self._send(200, {"items": libs.list_catalogues(), "backups": libs.list_backups(), "current": CAT["meta"].get("lib_id")})
            if path == "/api/lib/save":
                with LOCK:
                    cid = CAT["meta"].get("lib_id") if not b.get("new") else None
                    cid = libs.save_catalogue(CAT, b.get("nom") or CAT["meta"].get("titre"), cid)
                    CAT["meta"]["lib_id"] = cid
                    if b.get("nom"):
                        libs.rename_catalogue(cid, b["nom"])
                    save()
                return self._send(200, {"state": public_state()})
            if path == "/api/lib/open":
                c = libs.load_catalogue(b["id"])
                replace_catalogue({"meta": dict(c.get("meta", {}), lib_id=c["id"]), "books": c.get("books", [])}, "ouverture")
                return self._send(200, {"state": public_state()})
            if path == "/api/lib/duplicate":
                cid = libs.duplicate_catalogue(b["id"], b.get("nom"))
                if b.get("open"):
                    c = libs.load_catalogue(cid)
                    replace_catalogue({"meta": c.get("meta", {}), "books": c.get("books", [])}, "ouverture")
                return self._send(200, {"state": public_state()})
            if path == "/api/lib/rename":
                libs.rename_catalogue(b["id"], b.get("nom", ""))
                return self._send(200, {"state": public_state()})
            if path == "/api/lib/delete":
                libs.delete_catalogue(b["id"])
                with LOCK:
                    if CAT["meta"].get("lib_id") == b["id"]:
                        CAT["meta"].pop("lib_id", None)
                        save()
                return self._send(200, {"state": public_state()})
            if path == "/api/backup/restore":
                replace_catalogue(libs.load_backup(b.get("name")), "restauration")
                return self._send(200, {"state": public_state()})
            if path == "/api/import":
                rows, problems = importer.read_rows(base64.b64decode(b["data"]), b.get("filename", ""))
                added, changes = add_rows(rows, replace=bool(b.get("replace")))
                return self._send(200, {"added": added, "problems": problems, "changes": changes, "state": public_state()})
            if path == "/api/add_isbns":
                found = re.findall(r"[0-9][0-9\- ]{8,15}[0-9Xx]", b.get("text", ""))
                rows, bad = [], []
                for f in found:
                    d = isbnlib.to13(f)
                    (rows if d else bad).append({"isbn": d} if d else f)
                if not found and b.get("text", "").strip():
                    bad.append(b["text"].strip()[:40])
                added, _ = add_rows(rows)
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
                    libs.backup(CAT, "nouveau")
                    CAT.get("meta", {}).pop("lib_id", None)
                    CAT["books"] = []
                    CAT["meta"] = {"titre": "", "date": ""}
                    try:
                        os.remove(os.path.join(store.data_dir(), "garde.jpg"))
                    except OSError:
                        pass
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
                    CAT["meta"].update({k: str(v) for k, v in b.items() if k in ("titre", "date", "indicatif", "selection", "garde_titre", "garde_date", "garde_acc", "garde_couleur")})
                    save()
                return self._send(200, {})
            if path == "/api/garde/image":
                gp = os.path.join(store.data_dir(), "garde.jpg")
                if not b.get("data"):
                    if os.path.exists(gp):
                        os.remove(gp)
                else:
                    im = Image.open(io.BytesIO(base64.b64decode(b["data"])))
                    im.load()
                    if im.mode in ("RGBA", "LA", "P"):
                        bg = Image.new("RGB", im.size, "#FFFFFF")
                        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
                        im = bg
                    im = im.convert("RGB")
                    im.thumbnail((1600, 1600))
                    im.save(gp, "JPEG", quality=90)
                with LOCK:
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
                return self._send(200, preview(b.get("page", 0), int(b.get("dpi", 100))))
            if path == "/api/generate":
                s = store.load_settings()
                r = generate(b.get("out_dir") or s["out_dir"], b.get("name", ""), bool(b.get("pdf", True)), bool(b.get("pptx", False)), bool(b.get("xlsx", False)))
                return self._send(200, r)
            if path == "/api/settings":
                patch = {k: v for k, v in b.items() if k in store.SETTING_KEYS}
                if "google_key" in patch:
                    patch["google_key"] = str(patch["google_key"] or "").strip()
                    if patch["google_key"].startswith("••"):
                        patch.pop("google_key")
                if "taux" in patch:
                    try:
                        t = float(str(patch["taux"]).replace(",", ".").replace(" ", ""))
                        if not 0 < t < 1_000_000:
                            raise ValueError
                    except ValueError:
                        return self._send(400, {"error": "Le taux doit être un nombre positif (ex. 3366)."})
                    patch["taux"] = int(t) if t == int(t) else t
                if "arrondi" in patch:
                    patch["arrondi"] = int(patch["arrondi"]) if str(patch["arrondi"]).isdigit() and int(patch["arrondi"]) in (1, 5, 10, 50, 100, 500, 1000) else 1
                for k in ("inclure_prix", "p_garde", "p_cond", "p_proforma", "p_dos", "p_multi4"):
                    if k in patch:
                        patch[k] = bool(patch[k])
                if "conditions_texte" in patch:
                    patch["conditions_texte"] = str(patch["conditions_texte"] or "").strip()
                    if patch["conditions_texte"] == fixedlib.CONDITIONS.strip():
                        patch["conditions_texte"] = ""
                if "claude_key" in patch:
                    patch["claude_key"] = str(patch["claude_key"] or "").strip()
                    if patch["claude_key"].startswith("••"):
                        patch.pop("claude_key")
                store.update_settings(patch)
                REV["n"] += 1
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
