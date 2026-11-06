"""Tests hors ligne : python tests/test_core.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ["CMPL_CAT_DATA_DIR"] = tempfile.mkdtemp()
import fakenet
from catalogue import catalog, isbn, importer, pages, render_pdf, sources, store

sources.http_get = fakenet.http_get
ST = store.load_settings()
COV = tempfile.mkdtemp()


def fetch(i, key="K", force=True):
    b = catalog.new_book(i)
    raw = sources.fetch_raw(i, key, use_cache=not force)
    catalog.apply_fetch(b, raw, ST, COV)
    catalog.resolve_cover(b, raw, COV)
    return b, raw


# fiche complète (BnF + Google)
b, _ = fetch("9782100870165")
assert b["titre"] == "Analyse financière : concepts et méthodes", b["titre"]
assert b["auteurs"] == ["Marion, Alain", "Chalençon, Ludivine", "Lantin, François"], b["auteurs"]
assert (b["date"], b["editeur"], b["collection"], b["pages"]) == ("28/08/2024", "Dunod", "Les fondamentaux business", "XII-369")
assert b["illustrations"] == "illustrations en noir et blanc" and b["dimensions"] == "24 cm"
assert b["resume"].endswith(".") and len(b["resume"]) <= 420 and b["cover_origin"] == "google?"
# traducteur / cartographe exclus ; éditeur sans la ville
b, _ = fetch("9782200611545"); assert b["auteurs"] == ["Boniface, Pascal", "Védrine, Hubert"] and b["editeur"] == "Armand Colin"
# livre collectif : auteurs depuis Google, mis au format « Nom, Prénom »
b, _ = fetch("9782100865420"); assert b["auteurs"][0] == "Albino-Pimentel, João" and b["pages"] == "IX-665" and b["illustrations"].endswith("couleur")
# éditeur déduit du préfixe quand la BnF ne connaît pas le livre
b, _ = fetch("9782200623296"); assert b["editeur"] == "Armand Colin" and b["date"] == "05/09/2018"
# ISBN inconnu partout
b, _ = fetch("9782100000000"); assert catalog.status(b)[0] == "orange" or catalog.status(b)[0] == "rouge"
# clé refusée / quota : message clair, rien en cache
raw = sources.fetch_raw("9782100870165", "BAD", use_cache=False); assert "clé refusée" in raw["errors"][0] and raw["bnf"]
raw = sources.fetch_raw("9782100870165", "QUOTA", use_cache=False); assert "quota" in raw["errors"][0]
raw = sources.fetch_raw("9782100870165", "", use_cache=False); assert "pas de clé" in raw["errors"][0]
# cache : pas de nouvel appel réseau
sources.fetch_raw("9782100861514", "K", use_cache=False); n = len(fakenet.calls)
sources.fetch_raw("9782100861514", "K", use_cache=True); assert len(fakenet.calls) == n
# ce que l'utilisateur a saisi n'est pas écrasé par une nouvelle recherche
b, raw = fetch("9782100870165"); b["titre"] = "Mon titre"; b["edited"].append("titre")
catalog.apply_fetch(b, raw, ST, COV); assert b["titre"] == "Mon titre"
# import
rows, pb = importer.read_rows("ISBN;Prix;Titre\n978-2-10-087016-5;24,90 €;Un titre\n123;1\n".encode(), "x.csv")
assert rows == [{"isbn": "9782100870165", "prix": 24.9, "titre": "Un titre"}] and len(pb) == 1
assert isbn.to13("2-10-086151-2") in ("", isbn.to13("2100861512"))
# dossier de couvertures : nom avec tirets accepté, prioritaire sur Google
from PIL import Image
Image.new("RGB", (300, 420), (10, 120, 10)).save(os.path.join(COV, "978-2-10-087016-5.jpg"))
b, _ = fetch("9782100870165"); assert b["cover_origin"] == "dossier", b["cover_origin"]
# mise en page : plusieurs pages, PDF avec texte sélectionnable
books = []
for k in range(23):
    x = catalog.new_book("97821008%05d" % k); x.update(titre=f"Livre numéro {k}", auteurs=["Nom, Prénom"], resume="Texte. " * 60, date="2024", editeur="Dunod", pages="200", fetched=True)
    books.append(x)
pg = pages.build_pages(books); assert len(pg) >= 3 and all(p.hot for p in pg)
assert sum(len(p.hot) for p in pg) == 23
out = os.path.join(tempfile.mkdtemp(), "t.pdf"); render_pdf.build_pdf(pg, out)
import pypdf
r = pypdf.PdfReader(out); assert len(r.pages) == len(pg) and "Livre numéro 0" in r.pages[0].extract_text()
print("OK tests")
