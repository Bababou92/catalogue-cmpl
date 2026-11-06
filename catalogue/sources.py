"""Récupération des fiches livres : Google Books (clé API) + catalogue de la BnF, puis fusion et nettoyage.

Tout accès réseau passe par http_get() (remplaçable dans les tests)."""
import html
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image

from . import errlog, isbn as isbnlib, store

UA = {"User-Agent": "catalogue-cmpl/0.1 (+https://github.com/Bababou92/catalogue-cmpl)"}


class SourceError(Exception):
    pass


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- accès brut
def google_raw(isbn, key):
    if not key:
        raise SourceError("pas de clé Google Books (Réglages)")
    url = ("https://www.googleapis.com/books/v1/volumes?q=isbn:%s&maxResults=1&key=%s"
           % (isbn, urllib.parse.quote(key)))
    try:
        j = json.loads(http_get(url).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SourceError("Google Books : quota du jour atteint, réessaie plus tard")
        if e.code in (400, 403):
            raise SourceError("Google Books : clé refusée (vérifie-la dans les Réglages)")
        raise SourceError(f"Google Books : erreur HTTP {e.code}")
    items = j.get("items") or []
    if not items:
        return None
    # le premier résultat n'est pas toujours le bon livre : on prend celui dont l'ISBN correspond
    pick = items[0]
    for it in items:
        ids = [x.get("identifier", "") for x in (it.get("volumeInfo", {}).get("industryIdentifiers") or [])]
        if isbn in ids:
            pick = it
            break
    return {"volumeInfo": pick.get("volumeInfo", {}), "saleInfo": pick.get("saleInfo", {}), "id": pick.get("id", "")}


def bnf_raw(isbn):
    q = urllib.parse.quote(f'bib.isbn adj "{isbn}"')
    url = ("https://catalogue.bnf.fr/api/SRU?version=1.2&operation=searchRetrieve&query=%s"
           "&recordSchema=dublincore&maximumRecords=1" % q)
    try:
        root = ET.fromstring(http_get(url))
    except urllib.error.HTTPError as e:
        raise SourceError(f"BnF : erreur HTTP {e.code}")
    recs = [e for e in root.iter() if e.tag.endswith("}dc") or e.tag == "dc"]
    if not recs:
        return None
    r = recs[0]

    def all_(name):
        return [(e.text or "").strip() for e in r if e.tag.split("}")[-1] == name and (e.text or "").strip()]

    return {"title": all_("title"), "creator": all_("creator"), "contributor": all_("contributor"),
            "publisher": all_("publisher"), "date": all_("date"), "format": all_("format"),
            "description": all_("description"), "subject": all_("subject"), "identifier": all_("identifier")}


def fetch_raw(isbn, key, use_cache=True):
    """Interroge les sources (ou le cache). Retourne {google, bnf, errors}."""
    if use_cache:
        c = store.cache_get(isbn)
        if c is not None:
            return c
    raw = {"google": None, "bnf": None, "errors": []}
    for name, fn in (("google", lambda: google_raw(isbn, key)), ("bnf", lambda: bnf_raw(isbn))):
        try:
            raw[name] = fn()
        except SourceError as e:
            raw["errors"].append(str(e))
        except Exception as e:                      # réseau coupé, XML illisible…
            errlog.record(f"source {name} {isbn}", e)
            raw["errors"].append(f"{'Google Books' if name == 'google' else 'BnF'} : {type(e).__name__}")
    if not raw["errors"]:                           # on ne garde en cache que les réponses sans erreur
        store.cache_put(isbn, raw)
    return raw


# ---------------------------------------------------------------- nettoyage
_EXCLUDED_ROLES = ("traduct", "préfac", "prefac", "postfac", "illustr", "cartograph", "photograph", "adaptat", "narrat", "compositeur")
_PARTICLES = {"de", "du", "des", "del", "della", "di", "le", "la", "les", "van", "von", "der", "den", "el", "al", "ben", "bin", "da", "dos", "d'", "st", "saint"}


def parse_bnf_author(s):
    """'Marion, Alain (1950-....). Auteur du texte' -> ('Marion, Alain', 'Auteur du texte')."""
    s = re.sub(r"\s*\((?:\d{3,4}|\.{2,4}|ca\.?)[^)]*\)", "", s).strip()
    role = ""
    m = re.match(r"^(.*?)\.\s+([A-ZÉ][^.]*)$", s)
    if m:
        s, role = m.group(1).strip(), m.group(2).strip()
    return s, role


def name_last_first(name):
    """'Alain Marion' -> 'Marion, Alain' (les noms déjà au format 'Nom, Prénom' sont gardés)."""
    n = re.sub(r"\s*\([^)]*\)?\.?\)?", "", name or "").strip(" .)")
    if not n:
        return ""
    if "," in n:
        return re.sub(r"\s+", " ", n)
    parts = n.split()
    if len(parts) == 1:
        return n
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in _PARTICLES:
        i -= 1
    return f"{' '.join(parts[i:])}, {' '.join(parts[:i])}"


_LOWER_FIRST = {"le", "la", "les", "l'", "un", "une", "des", "de", "du", "pour", "vers", "comment", "tout", "toute", "tous",
                "cours", "manuel", "guide", "concepts", "méthodes", "licence", "master", "exercices", "essai"}


def lower_first(sub):
    """Sous-titre : « La référence… » -> « la référence… » (style des notices), sans toucher aux sigles ni aux noms propres."""
    sub = (sub or "").strip()
    first = re.split(r"[\s’']", sub, 1)[0].lower().rstrip(",")
    if sub[:1].isupper() and (sub[1:2].islower() or sub[1:2] in "'’") and (first in _LOWER_FIRST or first + "'" in _LOWER_FIRST):
        return sub[0].lower() + sub[1:]
    return sub


def clean_resume(text, max_chars=420):
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(R[ée]sum[ée]|Pr[ée]sentation)\s*:\s*", "", t, flags=re.I)
    t = t.strip('"').strip()
    if max_chars and len(t) > max_chars:
        cut = t[:max_chars]
        ends = [m.end() for m in re.finditer(r"[.!?…](?=\s|$)", cut)]
        if ends and ends[-1] >= max_chars * 0.55:
            t = cut[:ends[-1]].strip()
        else:
            t = cut.rsplit(" ", 1)[0].rstrip(" ,;:—-") + "…"
    return t


def fmt_date(s):
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", (s or "").strip())
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{d}/{mo}/{y}" if d and mo else f"{mo}/{y}" if mo else y


def clean_publisher(s):
    s = re.sub(r"\s*\([^)]*\)", "", s or "").strip()
    return re.sub(r"\s+", " ", s)


_EDITION = re.compile(r"\s*\((?:\[?(?:Nouvelle\s+)?[ÉE]d(?:ition|\.)?\]?|\d+\s*(?:e|re|ème)\s*[ée]d)[^)]*\)", re.I)


def clean_bnf_title(t):
    t = (t or "").split(" / ")[0]
    m = _EDITION.search(t)
    if m:
        t = t[:m.start()]
    t = re.sub(r"\s*\[[^\]]*\]", "", t)
    return re.sub(r"\s+", " ", t).strip(" :;,")


def parse_bnf_format(fmt):
    """'1 vol. (XII-369 p.) : ill. en coul. ; 24 x 17 cm' -> (pages, illustrations, dimensions)."""
    f = fmt or ""
    pages = ""
    m = re.search(r"\(([^()]*?)\s*p\.\)", f)
    if m:
        pages = m.group(1).strip()
    ill = ""
    m = re.search(r":\s*(ill\.[^;]*?)(?=\s*;|$)", f)
    if m:
        s = m.group(1)
        if re.search(r"coul", s):
            ill = "illustrations en noir et en couleur" if re.search(r"noir", s) else "illustrations en couleur"
        else:
            ill = "illustrations en noir et blanc"
    dim = ""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:x\s*(\d+(?:[.,]\d+)?)\s*)?cm", f)
    if m:
        dim = f"{m.group(1)} x {m.group(2)} cm" if m.group(2) else f"{m.group(1)} cm"
    return pages, ill, dim


def looks_like_cover(img):
    """Écarte les vignettes « image non disponible » (presque unies) et les images minuscules."""
    if img.width < 90 or img.height < 120:
        return False
    g = img.convert("L").resize((48, 64))
    px = list(g.getdata())
    mean = sum(px) / len(px)
    var = sum((p - mean) ** 2 for p in px) / len(px)
    return var > 90


# ---------------------------------------------------------------- fusion
def merge(isbn, raw, resume_max=420, extra_publishers=None):
    """Fiche livre à partir des réponses brutes. Retourne un dict de champs (valeurs vides si inconnues)."""
    g = ((raw or {}).get("google") or {}).get("volumeInfo") or {}
    b = (raw or {}).get("bnf") or {}
    out = {"titre": "", "auteurs": [], "resume": "", "date": "", "collection": "", "editeur": "",
           "pages": "", "illustrations": "", "dimensions": "", "sujets": []}

    gt = " : ".join(x for x in [g.get("title"), lower_first(g.get("subtitle"))] if x)
    out["titre"] = gt or clean_bnf_title(" ".join(b.get("title", [])[:1]))

    bn = []
    for s in b.get("creator", []) + b.get("contributor", []):
        name, role = parse_bnf_author(s)
        if name and not any(x in role.lower() for x in _EXCLUDED_ROLES):
            bn.append(name)
    out["auteurs"] = list(dict.fromkeys(bn)) or list(dict.fromkeys(
        a for a in (name_last_first(x) for x in g.get("authors", [])) if a))

    out["resume"] = clean_resume(g.get("description", ""), resume_max)
    out["date"] = fmt_date(g.get("publishedDate", "")) or fmt_date(" ".join(b.get("date", [])))

    desc = " ".join(b.get("description", []))
    m = re.search(r"Collection\s*:\s*(.*?)(?:\s*Code à barres commercial.*)?$", desc)
    if m:
        out["collection"] = m.group(1).strip()
    pub = clean_publisher(b["publisher"][0]) if b.get("publisher") else clean_publisher(g.get("publisher", ""))
    out["editeur"] = pub or isbnlib.publisher_for(isbn, extra_publishers)

    fmt = " ; ".join(b.get("format", []))
    pages, ill, dim = parse_bnf_format(fmt)
    out["pages"] = pages or (str(g["pageCount"]) if g.get("pageCount") else "")
    out["illustrations"], out["dimensions"] = ill, dim
    out["sujets"] = b.get("subject", [])
    return out


# ---------------------------------------------------------------- couvertures
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def find_cover_file(isbn, covers_dir):
    """Image nommée d'après l'ISBN dans le dossier de couvertures (tirets et espaces acceptés)."""
    try:
        for f in os.listdir(covers_dir or ""):
            stem, ext = os.path.splitext(f)
            if ext.lower() in IMG_EXT and isbnlib.to13(stem) == isbn:
                return os.path.join(covers_dir, f)
    except OSError:
        pass
    return ""


def save_cover_bytes(data, dest_dir, isbn, ext=None):
    """Enregistre une image (octets) en <isbn>.jpg / .png ; retourne le chemin."""
    im = Image.open(io.BytesIO(data))
    im.load()
    os.makedirs(dest_dir, exist_ok=True)
    for old in os.listdir(dest_dir):
        if os.path.splitext(old)[1].lower() in IMG_EXT and isbnlib.to13(os.path.splitext(old)[0]) == isbn:
            try:
                os.remove(os.path.join(dest_dir, old))
            except OSError:
                pass
    if im.mode in ("RGBA", "LA", "P"):
        path = os.path.join(dest_dir, isbn + ".png")
        im.convert("RGBA").save(path, "PNG")
    else:
        path = os.path.join(dest_dir, isbn + ".jpg")
        if max(im.size) > 1600:
            k = 1600 / max(im.size)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im.convert("RGB").save(path, "JPEG", quality=92)
    return path


def _bnf_ark(raw):
    for ident in ((raw or {}).get("bnf") or {}).get("identifier", []):
        m = re.search(r"ark:/12148/[A-Za-z0-9]+", ident)
        if m:
            return m.group()
    return ""


def cover_candidates(isbn, raw):
    """[(nom, adresse, vérifier)] par ordre de préférence."""
    g = ((raw or {}).get("google") or {}).get("volumeInfo") or {}
    links = g.get("imageLinks") or {}
    c = []
    for k in ("extraLarge", "large", "medium", "thumbnail", "smallThumbnail"):
        if links.get(k):
            c.append(("Google", links[k].replace("http://", "https://").replace("&edge=curl", ""), False))
            break
    ark = _bnf_ark(raw)
    if ark:
        c.append(("BnF", "https://catalogue.bnf.fr/couverture?&appName=NE&idArk=%s&couverture=1" % ark, True))
    c.append(("Google (devinée)", "https://books.google.com/books/content?vid=ISBN%s&printsec=frontcover&img=1&zoom=1&source=gbs_api" % isbn, True))
    c.append(("AbeBooks", "https://pictures.abebooks.com/isbn/%s-fr.jpg" % isbn, True))
    i10 = isbnlib.to10(isbn)
    if i10:
        c.append(("Amazon", "https://images-na.ssl-images-amazon.com/images/P/%s.01.LZZZZZZZ.jpg" % i10, True))
    c.append(("Open Library", "https://covers.openlibrary.org/b/isbn/%s-L.jpg?default=false" % isbn, True))
    return c


def _try_cover(url):
    try:
        data = http_get(url, timeout=10)
        im = Image.open(io.BytesIO(data))
        im.load()
        return (data, "") if looks_like_cover(im) else (None, "image vide ou trop petite")
    except urllib.error.HTTPError as e:
        return None, f"erreur {e.code}"
    except Exception as e:
        return None, "pas de réponse" if "timed out" in str(e) or isinstance(e, OSError) else "image illisible"


def download_cover(isbn, raw):
    """Teste toutes les sources en parallèle. Retourne (chemin, origine, journal) ; origine finissant par « ? » = à vérifier."""
    from concurrent.futures import ThreadPoolExecutor
    cands = cover_candidates(isbn, raw)
    with ThreadPoolExecutor(max_workers=len(cands) or 1) as ex:
        res = list(ex.map(lambda c: _try_cover(c[1]), cands))
    log, chosen = [], None
    for (name, url, verif), (data, why) in zip(cands, res):
        log.append(f"{name} : {'✓' if data else why}")
        if data and chosen is None:
            chosen = (data, name, verif)
    if not chosen:
        return "", "", log
    data, name, verif = chosen
    path = save_cover_bytes(data, store.cover_cache_dir(), isbn)
    origin = ("google" if name == "Google" else name.split(" (")[0].lower().replace(" ", "")) + ("?" if verif else "")
    return path, origin, log
