"""Le catalogue : liste de livres, fusion des infos, statut de complétude."""
import os
import threading
import time

from . import ai, isbn as isbnlib, net, sources, store

FIELDS = ("titre", "auteurs", "resume", "date", "collection", "editeur", "pages", "illustrations", "dimensions", "prix",
          "edition", "taux", "titre_tableau", "prix_ar")


def new_book(isbn, **kw):
    b = {"isbn": isbn, "titre": "", "auteurs": [], "resume": "", "date": "", "collection": "", "editeur": "",
         "pages": "", "illustrations": "", "dimensions": "", "prix": None, "sujets": [],
         "edition": "", "taux": "", "titre_tableau": "", "prix_ar": "", "rubrique": "", "prix_ancien": "",
         "resume_ia": False, "cover_path": "", "cover_origin": "", "cover_log": [], "titre_origin": "", "dispo": "", "dilicom": {}, "edited": [], "fetched": False, "errors": []}
    b.update(kw)
    return b


NOT_EDITED = ("prix", "dilicom", "dispo")      # informations de l'import qui ne sont pas des saisies de l'utilisateur


def apply_row(b, row):
    for k, v in row.items():
        if k != "isbn":
            b[k] = v
            if k not in NOT_EDITED and k not in b["edited"]:
                b["edited"].append(k)
    return b


def from_import_row(row):
    return apply_row(new_book(row["isbn"]), row)


def use_dilicom_fallback(book):
    """Titre / auteurs / éditeur du fichier Dilicom, seulement si rien d'autre n'a été trouvé."""
    d = book.get("dilicom") or {}
    if not book.get("titre") and d.get("titre"):
        book["titre"], book["titre_origin"] = d["titre"], "dilicom"
    if not book.get("auteurs") and d.get("auteurs"):
        book["auteurs"] = list(d["auteurs"])
    if not book.get("editeur") and d.get("editeur"):
        book["editeur"] = d["editeur"]
    return book


def apply_fetch(book, raw, settings, covers_dir):
    """Remplit la fiche avec ce qui a été trouvé, sans écraser ce que l'utilisateur a saisi."""
    fields = sources.merge(book["isbn"], raw, int(settings.get("resume_max") or 420), store.editeurs())
    for k, v in fields.items():
        if k in book["edited"]:
            continue
        book[k] = v
    book["errors"] = list((raw or {}).get("errors") or [])
    book["fetched"] = True
    if "titre" not in book["edited"] and book.get("titre_origin") == "dilicom":
        book["titre_origin"] = ""
    use_dilicom_fallback(book)
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
        o = book.get("cover_origin") or ""
        book["cover_path"], book["cover_origin"] = cached, o if o not in ("", "manuel", "dossier") else "web?"
        return
    if download:
        p, origin, log = sources.download_cover(book["isbn"], raw)
        book["cover_log"] = log
        if p:
            book["cover_path"], book["cover_origin"] = p, origin
            return
    book["cover_path"], book["cover_origin"] = "", ""


def missing(book):
    """Ce qui manque et qui compte (pastille orange). Pages, collection, illustrations : voir infos()."""
    m = []
    if not book.get("titre"):
        m.append("titre")
    if not book.get("auteurs"):
        m.append("auteurs")
    if not book.get("resume"):
        m.append("résumé")
    if not book.get("date"):
        m.append("date de parution")
    if not book.get("editeur"):
        m.append("éditeur")
    if not (book.get("cover_path") and os.path.isfile(book["cover_path"])):
        m.append("couverture")
    if book.get("prix") in (None, ""):
        m.append("prix")
    return m


def infos(book):
    """Informations facultatives absentes : simple indication, jamais bloquant."""
    if not book.get("fetched"):
        return []
    out = []
    if not book.get("pages"):
        out.append("nombre de pages non trouvé")
    if not book.get("collection"):
        out.append("pas de collection")
    if not book.get("illustrations"):
        out.append("illustrations non précisées")
    return out


def status(book):
    """('vert'|'orange'|'rouge'|'gris', texte)"""
    if not book.get("fetched"):
        return "gris", "pas encore récupéré"
    if not book.get("titre"):
        return "rouge", "introuvable : à saisir à la main"
    m = missing(book)
    if (book.get("cover_origin") or "").endswith("?"):
        m = m + ["couverture à vérifier"]
    if book.get("resume_ia") and book.get("resume"):
        m = m + ["résumé écrit par l'IA : à relire"]
    if book.get("titre_origin") == "dilicom" and "titre" not in book.get("edited", []):
        m = m + ["titre à vérifier (sans accents)"]
    if not m:
        return "vert", "complet"
    return "orange", "manque : " + ", ".join(m)


def dispo_alert(dispo):
    t = (dispo or "").strip().upper()
    if not t or t == "DISPONIBLE":
        return ""
    return {"EN RUPTURE DE STOCK": "en rupture de stock", "IMPRESSION A LA DEMANDE": "impression à la demande",
            "PROVISOIREMENT NON DISPONIBLE": "provisoirement indisponible"}.get(t, t.lower())


def public(book):
    s, txt = status(book)
    d = dict(book)
    d["statut"], d["statut_txt"] = s, txt
    d["alerte"] = dispo_alert(book.get("dispo"))
    d["infos"] = infos(book)
    d["has_cover"] = bool(book.get("cover_path") and os.path.isfile(book["cover_path"]))
    d.pop("cover_path", None)
    return d


# ---------------------------------------------------------------- récupération en tâche de fond
NET_POLL = 5.0            # secondes entre deux tests de connexion pendant une pause
NET_WAIT_MAX = 900.0      # pause maximale (15 min) avant d'abandonner proprement
MAX_PAUSES = 3            # pauses successives pour un même livre avant de le laisser « en attente »


class FetchJob:
    def __init__(self, isbns, settings):
        self.isbns, self.settings = list(isbns), settings
        self.done = 0
        self.running = True
        self.cancel = False
        self.updated = []        # isbn déjà traités (pour que l'interface se mette à jour)
        self.message = ""
        self.waiting = False     # en pause : connexion perdue, reprise automatique
        self.pending = []        # isbn non traités faute de connexion (rien n'est perdu : à relancer)
        self.kind = "fetch"
        self.errors = []


def wait_for_net(job):
    """Met le travail en pause jusqu'au retour d'internet. True = on peut reprendre ; False = annulé ou trop long."""
    job.waiting = True
    job.message = "Connexion perdue, reprise automatique…"
    t0 = time.time()
    try:
        while not job.cancel and time.time() - t0 < NET_WAIT_MAX:
            time.sleep(NET_POLL)
            if net.online(True):
                return True
        return False
    finally:
        job.waiting = False
        job.message = ""


def _retry_on_net(job, call, failed):
    """Appelle call() tant que failed(résultat) est vrai (coupure), en attendant le retour d'internet entre deux essais.
    Retourne (résultat, état) avec état = ok | skip (internet revenu mais service injoignable) | abort (annulé / trop long)."""
    pauses = 0
    while True:
        res = call()
        if not failed(res):
            return res, "ok"
        pauses += 1
        if pauses > MAX_PAUSES:
            return res, "skip"
        if not wait_for_net(job):
            return res, "abort"


def run_fetch(job, get_book, set_book, force=False):
    s = job.settings
    covers_dir = s.get("covers_dir", "")
    try:
        for i, isbn in enumerate(job.isbns):
            if job.cancel:
                break
            b = get_book(isbn)
            if b is None:
                job.done += 1
                continue
            if force and b.get("cover_origin") == "retiré":
                b["cover_origin"] = ""
            raw, state = _retry_on_net(job, lambda: sources.fetch_raw(isbn, s.get("google_key", ""), use_cache=not force),
                                       lambda r: r.get("net_error"))
            if state == "abort":                  # annulé ou coupure trop longue : le reste attend, sans rien marquer « introuvable »
                job.pending.extend(job.isbns[i:])
                break
            if state == "skip":                   # le livre n'a pas pu être interrogé : il reste « pas encore récupéré »
                job.pending.append(isbn)
                job.done += 1
                continue
            apply_fetch(b, raw, s, covers_dir)
            resolve_cover(b, raw, covers_dir)
            if not b.get("cover_path") and not net.online():       # couverture manquée à cause d'une coupure ?
                if wait_for_net(job):
                    resolve_cover(b, raw, covers_dir)
                else:
                    b["fetched"] = False          # on garde les infos, mais le livre sera relancé (depuis le cache) pour sa couverture
                    set_book(b)
                    job.pending.extend(job.isbns[i:])
                    break
            set_book(b)
            job.done += 1
            job.updated.append(isbn)
            time.sleep(0.15)
    finally:
        job.running = False
        job.waiting = False


# ---------------------------------------------------------------- descriptions écrites par l'IA
def run_ai(job, get_book, set_book, force=False):
    s = job.settings
    key, model = s.get("claude_key", ""), s.get("ai_model") or None
    rmax = int(s.get("resume_max") or 420)

    def describe(b):
        try:
            return ai.describe(b, key, rmax, model)
        except ai.AINetworkError as e:
            return e

    try:
        for i, isbn in enumerate(job.isbns):
            if job.cancel:
                break
            b = get_book(isbn)
            if b is None or not b.get("titre"):
                job.done += 1
                continue
            try:
                txt, state = _retry_on_net(job, lambda: describe(b), lambda r: isinstance(r, ai.AINetworkError))
            except ai.AIError as e:
                job.errors.append(str(e))
                if "clé" in str(e) or "crédit" in str(e):       # inutile d'insister : tous les livres échoueraient
                    break
                job.done += 1
                continue
            if state == "abort":
                job.pending.extend(job.isbns[i:])
                break
            if state == "skip":
                job.pending.append(isbn)
                job.done += 1
                continue
            b["resume"], b["resume_ia"] = txt, True
            if "resume" not in b["edited"]:
                b["edited"].append("resume")
            set_book(b, ia=True)
            job.done += 1
            job.updated.append(isbn)
    finally:
        job.running = False
        job.waiting = False
