"""Réponses simulées de Google Books / BnF (d'après de vrais résultats) + couvertures factices, pour les tests hors ligne."""
import io
import json
import re
import urllib.parse
import urllib.error
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw

BNF = {
    "9782200611545": dict(title=["Atlas du monde global : 100 cartes pour comprendre un monde chaotique ([Nouvelle édition]) Pascal Boniface, Hubert Védrine ; cartographie, Jean-Pierre Magnier"],
        creator=["Boniface, Pascal (1956-....). Auteur du texte", "Védrine, Hubert (1947-....). Auteur du texte"], contributor=["Magnier, Jean-Pierre. Cartographe"],
        publisher=["Armand Colin (Paris)", "Fayard (Paris)"], date=["2015"], format=["1 vol. (152 p.) ; 20 x 26 cm"],
        description=["Code à barres commercial : EAN 9782200611545"], subject=["Géopolitique", "Relations internationales"]),
    "9782100861514": dict(title=["Management des systèmes d'informations : tout pour s'entraîner ([Éd.] 2024-2025) Valérie Vo Ha,..."],
        creator=["Vo Ha, Valérie (1965-....). Auteur du texte"], contributor=[], publisher=["Dunod (Malakoff)", "Éditions Francis Lefebvre (Paris-La Défense)"],
        date=["2024"], format=["1 vol. (IX-319 p.) : ill. ; 24 cm"], description=["Collection : Expert Code à barres commercial : EAN 9782100861514"],
        subject=["Systèmes d'information -- Gestion"]),
    "9782100865420": dict(title=["Strategor : la référence en stratégie, de la start-up à la multinationale (9e éd.) J. Albino-Pimentel, R. Durand, P. Dussauge... [et al.]"],
        creator=[], contributor=[], publisher=["Dunod (Malakoff)"], date=["2024"], format=["1 vol. (IX-665 p.) : ill. en coul. ; 24 cm"],
        description=["Code à barres commercial : EAN 9782100865420"], subject=["Gestion concurrentielle", "Planification stratégique"]),
    "9782100824243": dict(title=["Strategor : all you need to know about strategy, from start-ups to multinationals / J. Albino-Pimentel, R. Durand, P. Dussauge... [et al.] ; [translation, Louise Bongiovanni]"],
        creator=[], contributor=["Bongiovanni, Louise. Traducteur"], publisher=["Dunod (Malakoff)"], date=["2024"],
        format=["1 vol. (VII-620 p.) : ill. en coul. ; 24 cm"], description=["Code à barres commercial : EAN 9782100824243"], subject=["Gestion concurrentielle"]),
    "9782100870165": dict(title=["Analyse financière : concepts et méthodes (7e éd., à jour des derniers changements du règlement de l'ANC) Alain Marion, Ludivine Chalençon, François Lantin"],
        creator=["Marion, Alain (1950-....). Auteur du texte", "Chalençon, Ludivine. Auteur du texte", "Lantin, François. Auteur du texte"], contributor=[],
        publisher=["Dunod (Malakoff)"], date=["2024"], format=["1 vol. (XII-369 p.) : ill. ; 24 cm"],
        description=["Collection : Les fondamentaux business Code à barres commercial : EAN 9782100870165"], subject=["Analyse financière"]),
}
GOOGLE = {
    "9782200623296": dict(title="Images économiques du monde", subtitle="Géopolitique-géoéconomie", authors=[], publishedDate="2018-09-05", pageCount=368,
        description="Lors de sa visite en Chine en janvier dernier, le président Emmanuel Macron avait comme principale mission d'exprimer la position de la France envers l'initiative chinoise des Routes de la soie, lancée au cours des années 2013-2014. Son discours de Xi'an qui focalisa principalement sur cette question témoigne non seulement de la prudence dont la France a jusqu'alors fait preuve vis-à-vis de cette initiative mais aussi des représentations ambivalentes que celle-ci suscite à travers le monde. D'une manière générale, on assiste à un tiraillement plus ou moins fort en fonction des pays et des régions entre un désir d'accéder à de nouvelles opportunités économiques et la crainte de voir s'installer une nouvelle hégémonie."),
    "9782200620035": dict(title="Images économiques du monde", subtitle="Géopolitique-Géoéconomie", authors=["François Bost", "Laurent Carroué", "Sébastien Colin", "Anne-Lise Humain-Lamoure"],
        publishedDate="2017-09-20", pageCount=361, description="Les Images économiques du monde dressent le bilan à la fois géoéconomique et géopolitique de l'année 2017. Le dossier \"France : la grande fracture\" vient analyser les multiples fractures (politique, sociale, territoriale) qui traversent le pays, et qui ont été exacerbées au cours de cette année électorale. La cartographie en couleurs est disponible sur la cartothèque en ligne du site armand-colin."),
    "9782200611545": dict(title="Atlas du monde global", subtitle="100 cartes pour comprendre un monde chaotique", authors=["Pascal Boniface", "Hubert Védrine"], publishedDate="2015-09-16", pageCount=160,
        description="Le monde global, si complexe, est fait de risques mais aussi d opportunites. Il est traverse par des courants contraires qui favorisent l emergence d une - communaute internationale - ou attisent les antagonismes averes ou potentiels."),
    "9782100861514": dict(title="Management des systèmes d'information DSCG 5", authors=["Valérie Vo Ha"], publishedDate="2024-09-11", pageCount=0),
    "9782100865420": dict(title="Strategor", subtitle="La référence en stratégie, de la start-up à la multinationale", authors=["João Albino-Pimentel", "Rodolphe Durand", "Pierre Dussauge", "Laurence Lehmann-Ortega"], publishedDate="2024-09-11"),
    "9782100824243": dict(title="Strategor", subtitle="All you need to know about strategy, from start-ups to multinationals", authors=["João Albino-Pimentel", "Rodolphe Durand"], publishedDate="2024-09-18"),
    "9782100870165": dict(title="Analyse financière", subtitle="Concepts et méthodes", authors=["Alain Marion (économiste).)", "Ludivine Chalençon", "François Lantin"], publishedDate="2024-08-28",
        description="Véritable guide de lecture et d'analyse, cet ouvrage propose une méthodologie rigoureuse et présente toutes les étapes de l'analyse financière : • analyse de l'activité et des indicateurs de performance ; • appréciation de la structure financière ; • interprétation des tableaux de flux ; • éclairage du niveau de rentabilité ; • maîtrise des principaux risques ESG (nouveauté). Cette 7e édition, entièrement mise à jour, propose une actualisation des données de référence."),
}
COVER_ISBN = {"9782100870165": (210, 60, 60), "9782200611545": (30, 90, 160)}   # ceux pour lesquels l'adresse « devinée » fonctionne
calls = []


def cover_png(color, w=300, h=420, text="COUVERTURE"):
    im = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, w - 20, 120], fill=(255, 255, 255))
    d.text((40, 60), text, fill=color)
    for i in range(8):
        d.rectangle([30, 160 + i * 28, w - 30 - (i * 13) % 60, 172 + i * 28], fill=(255, 255, 255))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def blank_png():
    b = io.BytesIO()
    Image.new("RGB", (128, 190), (250, 250, 250)).save(b, "PNG")
    return b.getvalue()


def http_get(url, timeout=25):
    calls.append(url)
    if "googleapis.com/books" in url:
        if "key=BAD" in url:
            raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)
        if "key=QUOTA" in url:
            raise urllib.error.HTTPError(url, 429, "quota", {}, None)
        isbn = re.search(r"isbn:(\d+)", url).group(1)
        g = GOOGLE.get(isbn)
        items = [{"id": "x" + isbn, "volumeInfo": dict(g, industryIdentifiers=[{"identifier": isbn}]), "saleInfo": {}}] if g else []
        return json.dumps({"totalItems": len(items), "items": items} if items else {"totalItems": 0}).encode()
    if "catalogue.bnf.fr" in url:
        isbn = re.search(r"%22(\d+)%22", url).group(1)
        r = BNF.get(isbn)
        if not r:
            return b'<?xml version="1.0"?><srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/"><srw:numberOfRecords>0</srw:numberOfRecords></srw:searchRetrieveResponse>'
        inner = "".join(f"<dc:{k}>{escape(v)}</dc:{k}>" for k, vals in r.items() for v in vals)
        return ('<?xml version="1.0"?><srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/"><srw:records><srw:record><srw:recordData>'
                '<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                + inner + '</oai_dc:dc></srw:recordData></srw:record></srw:records></srw:searchRetrieveResponse>').encode()
    if "books.google.com/books/content" in url:
        isbn = re.search(r"ISBN(\d+)", url).group(1)
        return cover_png(COVER_ISBN[isbn]) if isbn in COVER_ISBN else blank_png()
    raise urllib.error.URLError("hors ligne (test)")
