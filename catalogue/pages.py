"""Mise en page des pages de livres (A4, deux colonnes, comme le flyer du CMPL)."""
import dataclasses
import os
import re
from collections import OrderedDict
from functools import lru_cache

from PIL import Image

from . import textfit
from .model import Page, Pic, Rect, TextBox
from .textfit import MM_PER_PT, Para, Run

PAGE_W, PAGE_H = 210.0, 297.0
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 14.0, 16.0, 14.0
GUTTER = 8.0
COL_W = (PAGE_W - 2 * MARGIN_X - GUTTER) / 2
COVER_W, COVER_MAX_H, COVER_GAP = 21.5, 34.0, 3.5
LINE_COLOR = "#9A9A9A"
BLACK, GREY = "#000000", "#555555"

TITLE_PT, AUTHOR_PT, TEXT_PT, META_PT, EDIT_PT = 11.5, 8.0, 8.0, 7.5, 9.0


def _run(text, size, bold=False, italic=False, color=BLACK):
    return Run(text, family="arial", size=size, bold=bold, italic=italic, color=color)


def _paras_height(paras, width_mm):
    return textfit.layout(paras, width_mm / MM_PER_PT)[1] * MM_PER_PT if paras else 0.0


@lru_cache(maxsize=256)
def _load_image(path, mtime):
    im = Image.open(path)
    im.load()
    if max(im.size) > 900:
        k = 900 / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    return im.convert("RGB") if im.mode not in ("RGBA", "LA", "P") else im.convert("RGBA")


def cover_image(book):
    p = book.get("cover_path") or ""
    if p and os.path.isfile(p):
        try:
            return _load_image(p, os.path.getmtime(p))
        except Exception:
            return None
    return None


def format_line(book):
    if not book.get("pages"):
        return ""
    parts = [f"1 vol. ({book['pages']} p.)"]
    if book.get("illustrations"):
        parts.append(book["illustrations"])
    if book.get("dimensions"):
        parts.append(book["dimensions"])
    return " ; ".join(parts)


def _split_first_lines(text, width_pt, n_lines, run):
    """Coupe un texte après n lignes (mesurées à width_pt). Retourne (début, reste)."""
    if n_lines <= 0:
        return "", text
    lines = textfit._wrap(Para([run]), width_pt)
    if len(lines) <= n_lines:
        return text, ""
    first = "".join(p.text for ln in lines[:n_lines] for p in ln).strip()
    # on repart des mots du texte d'origine pour garder exactement la même ponctuation
    words = text.split()
    k = len(first.split())
    return " ".join(words[:k]), " ".join(words[k:])


def entry_layout(book, x, y, col_w=COL_W):
    """Éléments d'une notice de livre placée en (x, y). Retourne (éléments, hauteur_mm)."""
    els = []
    pad_top, pad_bottom = 3.2, 3.6
    els.append(Rect(x, y, col_w, 0.35, fill=LINE_COLOR, name="Filet"))
    top = y + pad_top

    im = cover_image(book)
    if im is not None:
        ch = min(COVER_MAX_H, COVER_W * im.height / im.width)
        cw = ch * im.width / im.height if ch < COVER_W * im.height / im.width else COVER_W
        els.append(Pic(x, top, cw, ch, image=im, fmt="AUTO", name="Couverture"))
        cover_w, cover_h = cw, ch
    else:
        cover_w, cover_h = COVER_W, 31.0
        els.append(Rect(x, top, cover_w, cover_h, fill="#E3E6EB", name="Couverture manquante"))
        els.append(TextBox(x, top, cover_w, cover_h, [Para([_run("Couverture à ajouter", 6, color="#7A8394")], align="c")],
                           anchor="m", inset=1.0, name="Couverture manquante (texte)"))

    text_x = x + cover_w + COVER_GAP
    text_w = col_w - cover_w - COVER_GAP

    # --- à droite de la couverture : titre, auteurs, début du résumé
    title = (book.get("titre") or "").strip() or f"(titre à saisir) {book.get('isbn', '')}"
    head = [Para([_run(title, TITLE_PT, bold=True, color=BLACK if book.get("titre") else "#B3261E")], align="l")]
    for i, a in enumerate(book.get("auteurs") or []):
        head.append(Para([_run(a, AUTHOR_PT + 0.5, italic=True, color=GREY)], align="l", space_before_pt=3.0 if i == 0 else 0.0))
    head_h = _paras_height(head, text_w)

    resume = (book.get("resume") or "").strip()
    first_txt, rest_txt = "", resume
    if resume:
        run = _run(resume, TEXT_PT)
        lh = textfit.line_height_pt(run) * MM_PER_PT
        room = cover_h - head_h - 1.2
        n = int(room // lh) if room > 0 else 0
        first_txt, rest_txt = _split_first_lines(resume, text_w / MM_PER_PT, n, run)
    beside = list(head)
    if first_txt:
        beside.append(Para([_run(first_txt, TEXT_PT)], align="l", space_before_pt=2.5))
    beside_h = _paras_height(beside, text_w)
    els.append(TextBox(text_x, top, text_w, beside_h + 0.6, beside, name="Titre et auteurs"))

    # --- sous la couverture : suite du résumé + références
    below = []
    if rest_txt:
        below.append(Para([_run(rest_txt, TEXT_PT)], align="l"))
    if book.get("date"):
        below.append(Para([_run(book["date"], META_PT)], align="l", space_before_pt=1.5 if below else 0.0))
    if book.get("collection"):
        below.append(Para([_run("Collection : " + book["collection"], META_PT + 0.5, italic=True)], align="l"))
    if book.get("editeur"):
        below.append(Para([_run("Éditeur : " + book["editeur"], EDIT_PT, bold=True, italic=True)], align="l", space_before_pt=1.0))
    fl = format_line(book)
    if fl:
        below.append(Para([_run(fl, META_PT)], align="l"))
    block_h = max(cover_h, beside_h)
    below_y = top + block_h + 1.2
    below_h = _paras_height(below, col_w)
    if below:
        els.append(TextBox(x, below_y, col_w, below_h + 0.6, below, name="Résumé (suite) et références"))
    total = (below_y + below_h if below else top + block_h) - y + pad_bottom
    return els, total


_ENTRY_CACHE = OrderedDict()
_KEYS = ("isbn", "titre", "auteurs", "resume", "date", "collection", "editeur", "pages", "illustrations", "dimensions")


def _shift(els, dx, dy):
    return [dataclasses.replace(e, x=e.x + dx, y=e.y + dy) for e in els]


def entry_cached(book):
    """Mise en page d'une notice en (0, 0), gardée en mémoire tant que le livre ne change pas."""
    p = book.get("cover_path") or ""
    try:
        sig = (p, os.path.getmtime(p)) if p and os.path.isfile(p) else ("", 0)
    except OSError:
        sig = ("", 0)
    key = (sig,) + tuple(repr(book.get(k)) for k in _KEYS)
    hit = _ENTRY_CACHE.get(key)
    if hit is None:
        hit = entry_layout(book, 0.0, 0.0)
        _ENTRY_CACHE[key] = hit
        while len(_ENTRY_CACHE) > 600:
            _ENTRY_CACHE.popitem(last=False)
    else:
        _ENTRY_CACHE.move_to_end(key)
    return hit


HEAD_H, HEAD_GAP = 8.0, 2.0


def _heading(x, y, title, color):
    w = PAGE_W - 2 * MARGIN_X
    return [Rect(x, y, w, HEAD_H, fill=color, name="Rubrique"),
            TextBox(x, y, w, HEAD_H, [Para([_run(title, 11.5, bold=True, color="#FFFFFF")], align="l")], anchor="m", inset=3.0, name="Rubrique : " + title)]


def build_pages(books, name="Catalogue", color="#5DADE1"):
    """Répartit les livres sur des pages A4. Retourne une liste de Page (avec .hot = zones cliquables).
    Un livre dont la rubrique change démarre une nouvelle ligne précédée d'un bandeau de titre."""
    pages = []
    cur = None
    y = MARGIN_TOP

    def new_page():
        pg = Page(f"{name} — page {len(pages) + 1}", PAGE_W, PAGE_H)
        pg.hot = []
        pages.append(pg)
        return pg

    named = any((b.get("rubrique") or "").strip() for b in books)
    rub = lambda b: (b.get("rubrique") or "").strip() or ("Autres titres" if named else "")
    limit = PAGE_H - MARGIN_BOTTOM
    i, prev = 0, ""
    while i < len(books):
        row = [books[i]]
        if i + 1 < len(books) and rub(books[i + 1]) == rub(books[i]):
            row.append(books[i + 1])
        title = rub(books[i]) if rub(books[i]) != prev and rub(books[i]) else ""
        prev = rub(books[i])
        laid = []
        for c, b in enumerate(row):
            x = MARGIN_X + c * (COL_W + GUTTER)
            laid.append((b, x) + entry_cached(b))
        h = max(l[3] for l in laid)
        need = h + ((HEAD_H + HEAD_GAP) if title else 0)
        if cur is None or (y + need > limit and y > MARGIN_TOP + 1):
            cur, y = new_page(), MARGIN_TOP
        if title:
            cur.elements.extend(_heading(MARGIN_X, y, title, color))
            y += HEAD_H + HEAD_GAP
        for b, x, els, eh in laid:
            cur.elements.extend(_shift(els, x, y))
            cur.hot.append({"isbn": b["isbn"], "x": x, "y": y, "w": COL_W, "h": h})
        y += h
        i += len(row)
    if not pages:
        new_page()
    return pages
