"""Le catalogue : liste de livres, fusion des infos, statut de complétude."""
import os
import threading
import time

from . import isbn as isbnlib, sources, store

FIELDS = ("titre", "auteurs", "resume", "date", "collection", "editeur", "pages", "illustrations", "dimensions", "prix")


def new_book(isbn, **kw):
    b = {"isbn": isbn, "titre": "", "auteurs": [], "resume": "", "date": "", "collection": "", "editeur": "",
         "pages": "", "illustrations": "", "dimensions": "", "prix": None, "sujets": [],
         "cover_path": "", "cover_origin": "", "edited": [], "fetched": False, "errors": []}
    b.update(kw)
    return b


def from_import_row(row):
    b = new_book(row["isbn"])
    for k, v in row.items():
        if k != "isbn":
            b[k] = v
            if k != "prix":
                b["edited"].append(k)
    return b


def apply_fetch(book, raw, settings, covers_dir):
    """Remplit la fiche avec ce qui a été trouvé, sans écraser ce que l'utilisateur a saisi."""
    fields = sources.merge(book["isbn"], raw, int(settings.get("resume_max") or 420), store.editeurs())
    for k, v in fields.items():
        if k in book["edited"]:
            continue
        book[k] = v
    book["errors"] = list((raw or {}).get("errors") or [])
    book["fetched"] = True
    return book


def resolve_cover(book, raw, covers_dir, download=True):
    """Dossier de couvertures d'abord, puis couverture déjà téléchargée, puis Google."""
    if book.get("cover_origin") == "retiré":
        book["cover_path"] = ""
        return
    if book.get("cover_origin") == "manuel" and book.get("cover_path") and os.path.isfile(book["cover_path"]):
        return
    f = sources.find_cover_file(book["isbn"], covers_dir)
    if f:
        book["cover_path"], book["cover_origin"] = f, "dossier"
        return
    cached = os.path.join(store.cover_cache_dir(), book["isbn"] + ".jpg")
    if os.path.isfile(cached):
        book["cover_path"], book["cover_origin"] = cached, book.get("cover_origin") if book.get("cover_origin", "").startswith("google") else "google?"
        return
    if download:
        p, origin = sources.download_cover(book["isbn"], raw)
        if p:
            book["cover_path"], book["cover_origin"] = p, origin
            return
    book["cover_path"], book["cover_origin"] = "", ""


def missing(book):
    m = []
    if not book.get("titre"):
        m.append("titre")
    if not book.get("auteurs"):
        m.append("auteurs")
    if not book.get("resume"):
        m.append("résumé")
    if not book.get("date"):
        m.append("date")
    if not book.get("editeur"):
        m.append("éditeur")
    if not book.get("pages"):
        m.append("pages")
    if not (book.get("cover_path") and os.path.isfile(book["cover_path"])):
        m.append("couverture")
    if book.get("prix") in (None, ""):
        m.append("prix")
    return m


def status(book):
    """('vert'|'orange'|'rouge'|'gris', texte)"""
    if not book.get("fetched"):
        return "gris", "pas encore récupéré"
    if not book.get("titre"):
        return "rouge", "introuvable : à saisir à la main"
    m = missing(book)
    if book.get("cover_origin") == "google?":
        m = m + ["couverture à vérifier"]
    if not m:
        return "vert", "complet"
    return "orange", "manque : " + ", ".join(m)


def public(book):
    s, txt = status(book)
    d = dict(book)
    d["statut"], d["statut_txt"] = s, txt
    d["has_cover"] = bool(book.get("cover_path") and os.path.isfile(book["cover_path"]))
    d.pop("cover_path", None)
    return d


# ---------------------------------------------------------------- récupération en tâche de fond
class FetchJob:
    def __init__(self, isbns, settings):
        self.isbns, self.settings = list(isbns), settings
        self.done = 0
        self.running = True
        self.cancel = False
        self.updated = []        # isbn déjà traités (pour que l'interface se mette à jour)
        self.message = ""


def run_fetch(job, get_book, set_book, force=False):
    s = job.settings
    covers_dir = s.get("covers_dir", "")
    try:
        for isbn in job.isbns:
            if job.cancel:
                break
            b = get_book(isbn)
            if b is None:
                job.done += 1
                continue
            if force and b.get("cover_origin") == "retiré":
                b["cover_origin"] = ""
            raw = sources.fetch_raw(isbn, s.get("google_key", ""), use_cache=not force)
            apply_fetch(b, raw, s, covers_dir)
            resolve_cover(b, raw, covers_dir)
            set_book(b)
            job.done += 1
            job.updated.append(isbn)
            if raw.get("google") is None and not raw.get("errors"):
                pass
            time.sleep(0.15)
    finally:
        job.running = False
