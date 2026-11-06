"""Tableau des prix (pages A4 portrait) : mêmes colonnes que le catalogue papier du CMPL.

Titre | Auteurs | Édition | Date de parution | ISBN | Éditeur | Prix France (Euros) pour info | Prix CMPL (Ariary)
"""
import os
import re
from datetime import date

from PIL import Image

from . import textfit
from .model import Page, Pic, Rect, TextBox
from .textfit import MM_PER_PT, Para, Run

PAGE_W, PAGE_H = 210.0, 297.0
MARGIN = 10.0
HEAD_FILL, HEAD_INK, GRID, INK, GREY = "#8C8C8C", "#FFFFFF", "#8A8A8A", "#000000", "#444444"
ROW_PT, HEAD_PT, PAD = 7.0, 7.5, 1.0

ADRESSE = ["9, rue Docteur Villette - Isoraka", "BP 3312 - Antananarivo", "cmpl @ moov.mg", "T. + 261 38 08 825 67"]
RC = "RC 6612 - INSRE 94819"
SITE = "www.librairie-cmpl.com"
NOTE = ("Seuls les prix mentionnés sur un devis ou une facture sont valables.\n"
        "Formulaire de demande de prix disponible à la fin de la sélection.")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_ABR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
EDITEURS_COURTS = {"ARMAND COLIN": "A.COLIN"}

FIELDS = ["titre_tableau", "auteurs", "edition", "date", "fiche", "editeur", "prix", "prix_ar"]     # champ modifié par chaque colonne

# (titre de colonne, largeur relative, alignement)
COLS = [("Titre", 46, "l"), ("Auteurs", 40, "l"), ("Edition", 12, "c"), ("Date de parution", 16, "c"), ("ISBN", 25, "c"),
        ("Editeur", 20, "c"), ("Prix France (Euros) pour info", 14, "r"), ("Prix Cmpl (Ariary)", 17, "r")]


def mois_annee(d=None):
    d = d or date.today()
    return f"{MOIS[d.month - 1].capitalize()} {d.year}"


# ---------------------------------------------------------------- calculs
def ariary(prix, taux, arrondi=1):
    """Prix en Ariary : euros x taux, arrondi à l'unité (ou à 10, 100, 500 Ar…). None si pas de prix."""
    try:
        v = float(prix) * float(taux)
    except (TypeError, ValueError):
        return None
    a = max(1, int(arrondi or 1))
    return int(v / a + 0.5) * a


def fmt_int(n):
    return f"{n:,}".replace(",", " ") if n is not None else ""


def fmt_eur(p):
    try:
        return f"{float(p):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def fmt_date(s):
    """'03/06/2024' -> '3-juin-24' ; 'MM/AAAA' -> 'juin-24' ; 'AAAA' -> '2024'."""
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return f"{d}-{MOIS_ABR[mo - 1]}-{str(y)[2:]}" if 1 <= mo <= 12 else s
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        mo, y = map(int, m.groups())
        return f"{MOIS_ABR[mo - 1]}-{str(y)[2:]}" if 1 <= mo <= 12 else s
    return s


def fmt_isbn(i):
    d = re.sub(r"\D", "", i or "")
    return f"{d[0]} {d[1:4]} {d[4:7]} {d[7:10]} {d[10:13]}" if len(d) == 13 else (i or "")


def short_title(book):
    t = (book.get("titre_tableau") or "").strip()
    if t:
        return t
    return re.split(r"\s+:\s+", (book.get("titre") or "").strip(), maxsplit=1)[0] or (book.get("titre") or "")


def authors_cell(book):
    out = []
    for a in book.get("auteurs") or []:
        a = re.sub(r"\s*\([^)]*\)", "", a)                  # « (06 ; 2020 ; Anglet) » et autres précisions
        out.append(a.split(",")[0].strip().upper())
    out = [a for a in out if a]
    if len(out) > 3:
        return "/".join(out[:3]) + " ET AL"
    return "/".join(out)


def publisher_cell(book):
    e = (book.get("editeur") or "").strip()
    e = re.sub(r"^(les\s+)?[ée]ditions?\s+(de\s+la\s+|du\s+|de\s+l['’]|de\s+|d['’])?", "", e, flags=re.I).replace('"', "").replace("«", "").replace("»", "").strip()
    e = e.upper()
    e = EDITEURS_COURTS.get(e, e)
    if len(e) > 28:                                           # nom très long : coupé au mot (modifiable dans la fiche)
        e = e[:28].rsplit(" ", 1)[0].rstrip(" ,;-") + "…"
    return e


def _taux_of(book, taux):
    t = book.get("taux")
    try:
        t = float(str(t).replace(",", ".")) if t not in (None, "") else None
    except ValueError:
        t = None
    return t or taux


def _edit_value(book, field):
    """Valeur proposée dans le mini-éditeur du tableau."""
    if field == "titre_tableau":
        return short_title(book)
    if field == "auteurs":
        return "\n".join(book.get("auteurs") or [])
    if field == "prix":
        return "" if book.get("prix") in (None, "") else str(book["prix"]).replace(".", ",")
    if field == "prix_ar":
        return "" if book.get("prix_ar") in (None, "") else str(book["prix_ar"])
    return str(book.get(field) or "")


def row_values(book, taux, arrondi=1):
    t = book.get("taux")
    try:
        t = float(str(t).replace(",", ".")) if t not in (None, "") else None
    except ValueError:
        t = None
    pr = book.get("prix")
    ar = ariary(pr, t or taux, arrondi) if pr not in (None, "") else None
    forced = book.get("prix_ar")
    if forced not in (None, ""):
        try:
            ar = int(float(str(forced).replace(",", ".").replace(" ", "")))
        except ValueError:
            pass
    return [short_title(book), authors_cell(book), str(book.get("edition") or ""), fmt_date(book.get("date")),
            fmt_isbn(book.get("isbn")), publisher_cell(book), fmt_eur(pr) if pr not in (None, "") else "", fmt_int(ar)]


# ---------------------------------------------------------------- mise en page
def _run(text, size, bold=False, italic=False, color=INK):
    return Run(text, family="arial", size=size, bold=bold, italic=italic, color=color)


def _h(paras, width_mm):
    return textfit.layout(paras, width_mm / MM_PER_PT)[1] * MM_PER_PT if paras else 0.0


def _logo():
    p = os.path.join(os.path.dirname(__file__), "assets", "logo_librairie.png")
    try:
        im = Image.open(p)
        im.load()
        return im.convert("RGB")
    except Exception:
        return None


def _widths():
    usable = PAGE_W - 2 * MARGIN
    tot = sum(c[1] for c in COLS)
    return [usable * c[1] / tot for c in COLS]


def _header(pg, titre, indicatif, n, total):
    """Logo, coordonnées, titre de la sélection, note, pied de page."""
    im = _logo()
    x = MARGIN
    if im is not None:
        h = 14.0
        w = h * im.width / im.height
        pg.elements.append(Pic(x, 8.0, w, h, image=im, fmt="AUTO", name="Logo CMPL"))
        x += w + 4
    lines = [Para([_run(l, 7.0)], align="l") for l in ADRESSE] + [Para([_run(RC, 6.0, color=GREY)], align="l", space_before_pt=1.0)]
    pg.elements.append(TextBox(x, 7.5, 46.0, 20.0, lines, name="Coordonnées"))
    bx = x + 48
    bw = PAGE_W - MARGIN - bx
    paras = [Para([_run(f"Sélection {titre}", 10.5, bold=True)], align="c"),
             Para([_run(f"Prix indicatifs {indicatif}", 8.5, bold=True)], align="c", space_before_pt=2.0)]
    for i, l in enumerate(NOTE.split("\n")):
        paras.append(Para([_run(l, 6.5, italic=True)], align="c", space_before_pt=3.0 if i == 0 else 0.0))
    pg.elements.append(TextBox(bx, 7.5, bw, 24.0, paras, name="Titre de la sélection"))
    pg.elements.append(TextBox(PAGE_W / 2 - 40, PAGE_H - 11.0, 80.0, 6.0, [Para([_run(SITE, 9.0, bold=True)], align="c")],
                               anchor="m", name="Site"))
    pg.elements.append(TextBox(PAGE_W - MARGIN - 20, PAGE_H - 11.0, 20.0, 6.0, [Para([_run(f"{n}/{total}", 8.0)], align="r")],
                               anchor="m", name="Numéro de page"))


def _table_head(pg, y, widths, head_h):
    x = MARGIN
    for (label, _, _), w in zip(COLS, widths):
        pg.elements.append(Rect(x, y, w, head_h, fill=HEAD_FILL, name="En-tête"))
        pg.elements.append(TextBox(x, y, w, head_h, [Para([_run(label, HEAD_PT, bold=True, color=HEAD_INK)], align="c")],
                                   anchor="m", inset=PAD, name="En-tête : " + label))
        x += w
    return y + head_h


def build_pages(books, titre="Catalogue", indicatif=None, taux=3366, arrondi=1):
    """Pages A4 paysage du tableau des prix. Retourne une liste de Page (avec .hot vide)."""
    indicatif = (indicatif or "").strip() or mois_annee()
    widths = _widths()
    xs = [MARGIN + sum(widths[:i]) for i in range(len(widths))]
    top, head_h, limit = 34.0, 14.0, PAGE_H - 15.0
    line = 0.25
    rows = []
    for b in books:
        vals = row_values(b, taux, arrondi)
        cells, hmax = [], 0.0
        for (label, _, al), w, v in zip(COLS, widths, vals):
            paras = [Para([_run(v, ROW_PT)], align=al)] if v else []
            hh = _h(paras, w - 2 * PAD)
            cells.append(paras)
            hmax = max(hmax, hh)
        rows.append((cells, max(5.0, hmax + 2 * PAD + 0.4), b))
    # répartition sur les pages
    groups, cur, used = [], [], top + head_h
    for r in rows:
        if cur and used + r[1] > limit:
            groups.append(cur)
            cur, used = [], top + head_h
        cur.append(r)
        used += r[1]
    if cur or not groups:
        groups.append(cur)
    pages = []
    for n, grp in enumerate(groups, 1):
        pg = Page(f"Tableau des prix — page {n}", PAGE_W, PAGE_H)
        pg.hot = []
        _header(pg, titre, indicatif, n, len(groups))
        y = _table_head(pg, top, widths, head_h)
        for cells, rh, b in grp:
            auto = ariary(b.get("prix"), _taux_of(b, taux), arrondi) if b.get("prix") not in (None, "") else None
            for x, w, paras, field in zip(xs, widths, cells, FIELDS):
                if paras:
                    pg.elements.append(TextBox(x, y, w, rh, paras, anchor="m", inset=PAD, name="Cellule"))
                pg.hot.append({"isbn": b.get("isbn"), "field": field, "x": x, "y": y, "w": w, "h": rh,
                               "v": _edit_value(b, field), "auto": fmt_int(auto) if field == "prix_ar" else ""})
            pg.elements.append(Rect(MARGIN, y + rh - line, sum(widths), line, fill=GRID, name="Filet"))
            y += rh
        bottom = y
        for x in xs + [MARGIN + sum(widths)]:
            pg.elements.append(Rect(x - line / 2, top + head_h, line, bottom - top - head_h, fill=GRID, name="Filet vertical"))
        pages.append(pg)
    return pages
