"""Pages fixes du catalogue : page de garde, conditions de vente, demande de facture proforma, 4e de couverture.

Mise en page reprise du catalogue papier du CMPL (octobre 2024). Tout est en millimètres."""
import os

from PIL import Image

from . import textfit
from .model import Page, Pic, Rect, TextBox
from .textfit import MM_PER_PT, Para, Run

W, H = 210.0, 297.0
BLUE, LIGHT, MID, NAVY, INK = "#5DADE1", "#AED6F0", "#85C1E8", "#1F435C", "#22313F"
ASSETS = os.path.join(os.path.dirname(__file__), "assets")

ACCROCHES = ["Dernières éditions", "Moins chères qu'en librairie française", "Prix & demandes de devis à la fin des sélections"]

CONDITIONS = """-1- Préambule
Toute commande d'ouvrages implique l'acceptation par l'acheteur des Conditions de Vente énoncées ci-dessous. Ces conditions concernent uniquement la vente des ouvrages référencés par la librairie CMPL.
-2- Facturation (Pro Forma)
Dès réception de la consultation de prix, le CMPL expédie à l'acheteur (par e-mail, fax ou poste selon demande) la Facture Pro Forma correspondante aux ouvrages demandés. Ceux-ci peuvent être disponibles en stock ou à commander.
Les ouvrages disponibles en stock sont réservés 10 (dix) jours à compter de la date d'envoi de la Facture Pro Forma avant d'être remis en vente, au cas où le destinataire n'aurait donné suite. La livraison est gratuite sur la ville d'Antananarivo intra-muros. Des frais forfaitaires de livraison peuvent être ajoutés sur la Facture Pro Forma dans le cas d'une livraison en périphérie d'Antananarivo intra-muros. Pour une livraison en province, les frais de port seront ajoutés sur la Facture Pro Forma au total du prix des ouvrages suivant les tarifs du messager Colis Express (tarifs disponibles sur demande).
Les ouvrages non-disponibles (à paraître ou en rupture de stock) font l'objet d'une autre facture Pro Forma et de conditions de vente particulières du fait de leur acheminement vers les villes de Madagascar.
Les prix du catalogue et des autres supports de communication du CMPL sont donnés à titre indicatif et peuvent être soumis à modification. Les prix & quantités mentionnés sur la Facture Pro Forma sont garantis 10 (dix) jours.
-3- Paiement
Le paiement à distance (province) se fait par mandat postal ou par mobile (Telma Mvola et Orange Money), à l'ordre et à l'adresse du CMPL. L'acheteur mentionnera sur le mandat, à la suite de son nom le numéro de la Facture Pro Forma. Le CMPL n'accepte aucun autre mode de paiement à distance depuis les provinces. Les ouvrages livrés sur la ville d'Antananarivo intra-muros peuvent être payés à la livraison, par le coursier-encaisseur du CMPL, après confirmation par téléphone des disponibilités, durant les jours ouvrables. Les ouvrages peuvent aussi être payés au comptant et enlevés au magasin CMPL.
-4- Livraison & Facturation (Définitive)
Dans le cas d'une livraison en province, dès encaissement du mandat postal, le CMPL expédie dans un délai de 3 (trois) jours ouvrables les ouvrages et la Facture Définitive correspondant à la Facture Pro Forma CMPL et au Bon de Commande Client.
Dans le cas d'une livraison dans la ville d'Antananarivo intra-muros, le client peut choisir une livraison-paiement à domicile ou un enlèvement-paiement depuis les locaux du CMPL à Isoraka.
-5- Litiges & Juridiction
En cas de vice constatés sur un ou plusieurs ouvrages, l'acheteur le ou les retournera au CMPL qui procèdera à la constatation et le cas échéant, à l'échange (ou au remboursement en cas de rupture de stock) et au remboursement des frais de port correspondant à l'échange.
En l'absence de règlement à l'amiable, la juridiction malgache est seule compétente pour les résolutions des litiges."""

PIED_CONDITIONS = ["RC 6612 – INSRE 94819", "BFV SG 0200100109-4 (MGF)", "BFV SG 001 96032 00105 7 (Euro)"]


def _run(t, size, bold=False, italic=False, color=INK, smallcaps=False):
    return Run(t, family="arial", size=size, bold=bold, italic=italic, color=color, smallcaps=smallcaps)


def _height(paras, width_mm):
    return textfit.layout(paras, width_mm / MM_PER_PT)[1] * MM_PER_PT if paras else 0.0


def _logo(path="logo_librairie.png"):
    try:
        im = Image.open(os.path.join(ASSETS, path))
        im.load()
        return im.convert("RGB")
    except Exception:
        return None


def _pic_logo(x, y, w, name="Logo CMPL"):
    im = _logo()
    return Pic(x, y, w, w * im.height / im.width, image=im, fmt="AUTO", name=name) if im is not None else None


def default_image():
    im = Image.open(os.path.join(ASSETS, "garde_defaut.jpg"))
    im.load()
    return im.convert("RGB")


def _fit(im, ratio):
    """Recadre l'image au centre pour remplir un cadre de proportions largeur/hauteur = ratio."""
    w, h = im.size
    if w / h > ratio:
        nw = int(h * ratio)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / ratio)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    if max(im.size) > 1600:
        im.thumbnail((1600, 1600))
    return im


def _contact_block(pg, x, y, w, color=INK, align="c"):
    lines = [("cmpl@moov.mg", False), ("+261 38 08 825 67", False), ("www.librairie-cmpl.com", True)]
    paras = [Para([_run(t, 10.5, bold=b, color=color, smallcaps=True)], align=align, space_before_pt=0 if i == 0 else 5.0) for i, (t, b) in enumerate(lines)]
    pg.elements.append(TextBox(x, y, w, 25.0, paras, name="Contacts"))
    fy = y + 25.0
    pg.elements.append(Rect(x + w / 2 - 17, fy + 0.6, 4.6, 4.6, fill=NAVY, name="Icône Facebook"))
    pg.elements.append(TextBox(x + w / 2 - 17, fy + 0.6, 4.6, 4.6, [Para([_run("f", 9.0, bold=True, color="#FFFFFF")], align="c")], anchor="m", name="f"))
    pg.elements.append(TextBox(x + w / 2 - 11, fy, 40.0, 6.0, [Para([_run("/Librairie-cmpl", 10.5, color=color, smallcaps=True)], align="l")], anchor="m", name="Facebook"))
    pg.elements.append(TextBox(x, fy + 8.0, w, 7.0, [Para([_run("Madagascar", 11.0, bold=True, color=NAVY, smallcaps=True)], align="c")], anchor="m", name="Pays"))


# ---------------------------------------------------------------- page de garde
def cover_values(meta):
    """Textes de la page de garde, avec les valeurs par défaut."""
    meta = meta or {}
    acc = (meta.get("garde_acc") or "").strip("\n")
    return {
        "titre": (meta.get("garde_titre") or meta.get("titre") or "Catalogue CMPL").strip(),
        "date": (meta.get("garde_date") or meta.get("indicatif") or "").strip(),
        "acc": acc if acc.strip() else "\n".join(ACCROCHES),
    }


def cover_page(meta, image=None, mois=""):
    v = cover_values(meta)
    date = v["date"] or mois
    pg = Page("Page de garde", W, H)
    pg.hot = []
    pg.elements.append(Rect(0, 0, W, 183.0, fill=BLUE, name="Fond bleu"))
    pg.elements.append(Rect(14.0, 10.0, 100.0, 21.5, fill="#FFFFFF", name="Bandeau"))
    pg.elements.append(Rect(21.0, 14.7, 10.0, 10.0, fill=NAVY, name="Pictogramme"))
    pg.elements.append(Rect(24.0, 17.7, 4.5, 4.5, fill="#FFFFFF", name="Pictogramme"))
    pg.elements.append(TextBox(34.0, 10.0, 78.0, 21.5, [Para([_run(f"Les sélections CMPL – {date}", 8.5, color=INK, smallcaps=True)], align="l")], anchor="m", name="Bandeau texte"))
    pg.hot.append({"meta": True, "field": "garde_date", "x": 14.0, "y": 10.0, "w": 100.0, "h": 21.5, "v": date, "auto": ""})
    pg.elements.append(Rect(124.5, 39.5, 44.5, 43.0, fill=LIGHT, name="Carré clair"))
    pg.elements.append(Rect(145.0, 68.5, 57.0, 52.0, fill="#FFFFFF", name="Cadre photo"))
    im = image if image is not None else default_image()
    pg.elements.append(Pic(146.5, 70.0, 54.0, 49.0, image=_fit(im, 54.0 / 49.0), fmt="AUTO", name="Image de la page de garde"))
    pg.hot.append({"meta": True, "field": "garde_image", "x": 145.0, "y": 68.5, "w": 57.0, "h": 52.0, "v": "", "auto": ""})
    # titre : la taille diminue si le titre est long
    box_w, box_h = 100.0, 56.0
    parts = [p for p in v["titre"].split("\n") if p.strip()] or [""]
    size = 38.0
    while size > 20.0:
        paras = [Para([_run(p, size, color="#FFFFFF")], align="l") for p in parts]
        if _height(paras, box_w) <= box_h:
            break
        size -= 2.0
    pg.elements.append(TextBox(19.0, 44.0, box_w, box_h, paras, anchor="b", name="Titre"))
    pg.hot.append({"meta": True, "field": "garde_titre", "x": 19.0, "y": 44.0, "w": box_w, "h": box_h, "v": v["titre"], "auto": ""})
    pg.elements.append(Rect(19.3, 104.2, 17.5, 2.2, fill="#FFFFFF", name="Barre"))
    pg.elements.append(Rect(19.3, 107.2, 90.5, 0.5, fill="#FFFFFF", name="Trait"))
    acc = [Para([_run(l, 10.0, color="#FFFFFF", smallcaps=True)], align="l", space_before_pt=0 if i == 0 else 10.0)
           for i, l in enumerate([l for l in v["acc"].split("\n") if l.strip()])]
    pg.elements.append(TextBox(19.3, 118.0, 150.0, 36.0, acc, name="Accroches"))
    pg.hot.append({"meta": True, "field": "garde_acc", "x": 19.3, "y": 118.0, "w": 150.0, "h": 36.0, "v": v["acc"], "auto": ""})
    logo = _pic_logo(96.0, 193.0, 106.0)
    if logo is not None:
        pg.elements.append(logo)
    _contact_block(pg, 96.0, 238.0, 106.0)
    return pg


# ---------------------------------------------------------------- conditions de vente
def _logo_header(pg, x0=20.0, y0=12.0, lines=None):
    logo = _pic_logo(x0, y0, 17.0 * 558 / 192)
    x = x0
    if logo is not None:
        pg.elements.append(logo)
        x = x0 + logo.w + 6
    return x


def conditions_page(texte=""):
    pg = Page("Conditions de vente", W, H)
    pg.hot = []
    x = _logo_header(pg, 20.0, 12.0)
    coord = [Para([_run("Centre Malgache de Promotion du Livre", 9.0, bold=True)], align="l"),
             Para([_run("9, rue Docteur Villette – Isoraka – BP 3312 – Antananarivo – MADAGASCAR", 8.0)], align="l"),
             Para([_run("Tél. (00 261 20) 22 244 62 – cmpl@moov.mg", 8.0)], align="l")]
    pg.elements.append(TextBox(x, 12.0, W - 20.0 - x, 17.0, coord, anchor="m", name="Coordonnées"))
    body_w, top, bottom = W - 40.0, 52.0, H - 30.0
    lines = [l.strip() for l in (texte or CONDITIONS).replace("\r", "").split("\n") if l.strip()]
    size = 9.5
    while True:
        paras = [Para([_run("CONDITIONS DE VENTE", size + 2.5, bold=True)], align="l")]
        for l in lines:
            head = l.startswith("-") and len(l) < 70 and l[1:2].isdigit()
            paras.append(Para([_run(l, size, bold=head)], align="l" if head else "j", space_before_pt=size * (0.9 if head else 0.4) if len(paras) > 1 else size * 0.8))
        if _height(paras, body_w) <= bottom - top or size <= 6.5:
            break
        size -= 0.25
    pg.elements.append(TextBox(20.0, top, body_w, bottom - top, paras, name="Conditions de vente"))
    pg.hot.append({"meta": True, "field": "conditions", "x": 20.0, "y": top, "w": body_w, "h": bottom - top, "v": "", "auto": ""})
    pied = [Para([_run(l, 8.0, color="#444444")], align="l") for l in PIED_CONDITIONS]
    pg.elements.append(TextBox(20.0, H - 26.0, 100.0, 14.0, pied, anchor="b", name="Pied de page"))
    return pg


# ---------------------------------------------------------------- demande de facture proforma
def blank_page():
    pg = Page("Page blanche", W, H)
    pg.hot = []
    return pg


def proforma_page():
    pg = Page("Demande de facture proforma", W, H)
    pg.hot = []
    M = 10.0
    logo = _pic_logo(M, 8.0, 14.0 * 558 / 192)
    x = M
    if logo is not None:
        pg.elements.append(logo)
        x = M + logo.w + 4
    adr = ["9, rue Docteur Villette - Isoraka", "BP 3312 - Antananarivo", "cmpl @ moov.mg", "T. + 261 20 22 244 62"]
    paras = [Para([_run(l, 7.0)], align="l") for l in adr] + [Para([_run("RC 6612 - INSRE 94819", 6.0, color="#444444")], align="l", space_before_pt=1.0)]
    pg.elements.append(TextBox(x, 7.5, 46.0, 20.0, paras, name="Coordonnées"))
    tx = x + 50
    pg.elements.append(TextBox(tx, 8.0, W - M - tx, 18.0, [
        Para([_run("DEMANDE DE FACTURE PROFORMA", 12.0, bold=True)], align="c"),
        Para([_run("Seuls les prix mentionnés sur un devis ou une facture sont valables.", 7.0, italic=True)], align="c", space_before_pt=4.0)], name="Titre"))
    # formulaire (à gauche) et signature (à droite)
    fx, fw, y = M, 112.0, 36.0
    pg.elements.append(TextBox(fx, y, W - 2 * M, 6.0, [Para([_run("□ Je souhaite être informé des actualités de la Librairie CMPL", 8.5, bold=True)], align="l")], anchor="m", name="Actualités"))
    y += 9.0
    for lab, extra in (("EMAIL*", 0), ("NOM/PRÉNOM*", 0), ("ADRESSE*", 1), ("CODE POSTAL*", 0), ("VILLE*", 0), ("TÉL*", 0), ("SOCIÉTÉ", 0)):
        pg.elements.append(TextBox(fx, y, 30.0, 6.0, [Para([_run(lab + " :", 8.5)], align="l")], anchor="b", name=lab))
        pg.elements.append(Rect(fx + 30.0, y + 5.6, fw - 30.0, 0.25, fill="#777777", name="Ligne"))
        y += 8.2
        if extra:
            pg.elements.append(Rect(fx + 30.0, y + 5.6, fw - 30.0, 0.25, fill="#777777", name="Ligne"))
            y += 8.2
    pg.elements.append(TextBox(fx, y + 1.0, fw, 5.0, [Para([_run("* Champs obligatoires", 7.0, italic=True)], align="l")], name="Obligatoire"))
    sx = fx + fw + 8.0
    pg.elements.append(Rect(sx, 46.0, W - M - sx, 40.0, fill="#FFFFFF", line="#444444", line_pt=0.75, name="Cadre signature"))
    pg.elements.append(TextBox(sx, 46.0, W - M - sx, 40.0, [Para([_run("Signature obligatoire", 8.5, italic=True)], align="c")], anchor="m", name="Signature"))
    # tableau de saisie
    cols = [("Référence", 32.0), ("Titre", 80.0), ("Auteur", 52.0), ("Quantité", 26.0)]
    tx0, ty, head_h, row_h = M, y + 12.0, 8.0, 9.0
    cx = tx0
    for lab, w in cols:
        pg.elements.append(Rect(cx, ty, w, head_h, fill="#8C8C8C", name="En-tête"))
        pg.elements.append(TextBox(cx, ty, w, head_h, [Para([_run(lab, 8.5, bold=True, color="#FFFFFF")], align="c")], anchor="m", name="En-tête : " + lab))
        cx += w
    tw = sum(w for _, w in cols)
    nrows = int((H - 32.0 - ty - head_h) // row_h)
    ye = ty + head_h + nrows * row_h
    for i in range(nrows + 1):
        pg.elements.append(Rect(tx0, ty + head_h + i * row_h - 0.1, tw, 0.2, fill="#8A8A8A", name="Filet"))
    cx = tx0
    for _, w in cols + [("", 0)]:
        pg.elements.append(Rect(cx - 0.1, ty + head_h, 0.2, ye - ty - head_h, fill="#8A8A8A", name="Filet vertical"))
        cx += w
    notes = ["À retourner à la librairie.",
             "Vous pouvez nous adresser une demande de prix d'ouvrages issus d'autres éditions que celles présentes dans nos sélections.",
             "En cas de livraison en province, des frais de port seront inclus dans la facture proforma.",
             "Les demandes de facture proforma peuvent nous être adressées sur papier libre."]
    pg.elements.append(TextBox(M, H - 28.0, W - 2 * M, 18.0, [Para([_run(n, 7.0, italic=True)], align="l") for n in notes], anchor="b", name="Notes"))
    return pg


# ---------------------------------------------------------------- 4e de couverture
def back_page():
    pg = Page("4e de couverture", W, H)
    pg.hot = []
    pg.elements.append(Rect(56.0, 86.0, 48.7, 50.0, fill=LIGHT, name="Carré clair"))
    pg.elements.append(Rect(14.0, 113.0, 74.4, 69.0, fill=LIGHT, name="Carré clair"))
    pg.elements.append(Rect(56.0, 113.0, 32.4, 23.0, fill=MID, name="Recouvrement"))
    pg.elements.append(Rect(0, 259.0, W, 38.0, fill=BLUE, name="Bandeau bleu"))
    sc = lambda t, b=False: Para([_run(t, 10.0, bold=b, color=INK, smallcaps=True)], align="l")
    gap = lambda: Para([_run(" ", 6.0)], align="l")
    paras = [sc("Librairie", True), sc("9, rue Dr Villette – Isoraka"), sc("BP 3312 Antananarivo"), gap(),
             sc("Relais", True), sc("Bibliothèque Universitaire"), sc("Campus d'Ambohitsaina"), gap(),
             sc("cmpl@moov.mg"), sc("t. +261 38 08 825 67"), sc("t. +261 20 22 244 62"), gap(), sc("www.librairie-cmpl.com", True)]
    pg.elements.append(TextBox(117.0, 99.0, 85.0, 80.0, paras, name="Coordonnées"))
    pg.elements.append(Rect(117.0, 183.0, 4.6, 4.6, fill=NAVY, name="Icône Facebook"))
    pg.elements.append(TextBox(117.0, 183.0, 4.6, 4.6, [Para([_run("f", 9.0, bold=True, color="#FFFFFF")], align="c")], anchor="m", name="f"))
    pg.elements.append(TextBox(123.0, 182.4, 60.0, 6.0, [sc("/Librairie-cmpl")], anchor="m", name="Facebook"))
    logo = _pic_logo(109.0, 213.0, 88.0)
    if logo is not None:
        pg.elements.append(logo)
    return pg
