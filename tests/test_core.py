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

# ---- export Dilicom (.slk) : prix, secours titre/auteur/éditeur, disponibilité
SLK = ("ID;PWXL;N;E\nC;Y1;X1;K\"Date :\"\nC;X2;K\"06/11/2026\"\nF;P0;Y3;X1\nC;K\"EAN\"\nF;X2\nC;K\"TITRE\"\nF;X3\nC;K\"AUTEUR\"\nF;X4\nC;K\"EDITEUR\"\n"
       "F;X5\nC;K\"DISTRIBUTEUR\"\nF;X6\nC;K\"PRIX\"\nF;X7\nC;K\"DISPO\"\nF;X9\nC;K\"QTE\"\n"
       "F;Y4;X1\nC;K\"9782212139273\"\nF;X2\nC;K\"LE COLOMBAGE, MODE D'EMPLOI\"\nF;X3\nC;K\"VALENTIN JEAN-LOUIS\"\nF;X4\nC;K\"EYROLLES\"\nF;X6\nC;K39.5\nF;X7\nC;K\"EN RUPTURE DE STOCK\"\nF;X9\nC;K1\n"
       "F;Y5;X1\nC;K\"9782100870165\"\nF;X2\nC;K\"ANALYSE FINANCIERE\"\nF;X6\nC;K24\nF;X7\nC;K\"DISPONIBLE\"\n"
       "F;Y6;X9\nC;K2\nF;X10\nC;K\"63,5\"\nE\n").encode("cp1252")
rows, pb = importer.read_rows(SLK, "panier.slk")
assert [r["isbn"] for r in rows] == ["9782212139273", "9782100870165"] and not pb, (rows, pb)
assert rows[0]["prix"] == 39.5 and rows[0]["dispo"] == "EN RUPTURE DE STOCK" and rows[1]["prix"] == 24.0
assert rows[0]["dilicom"]["titre"] == "Le colombage, mode d'emploi" and rows[0]["dilicom"]["editeur"] == "Eyrolles"
assert rows[0]["dilicom"]["auteurs"] == ["Valentin Jean-Louis"] and "titre" not in rows[0]
bk = catalog.from_import_row(rows[0]); assert bk["edited"] == [] and bk["prix"] == 39.5
assert catalog.public(bk)["alerte"] == "en rupture de stock"
catalog.apply_fetch(bk, {"errors": []}, ST, COV)          # rien trouvé sur internet -> repli Dilicom
assert bk["titre"] == "Le colombage, mode d'emploi" and bk["editeur"] == "Eyrolles" and bk["auteurs"]
assert "titre à vérifier" in catalog.status(bk)[1]
bk["edited"].append("titre"); assert "titre à vérifier" not in catalog.status(bk)[1]
# ---- descriptions IA (réseau simulé)
from catalogue import ai
import urllib.error, io as _io
sent = []
def fake_post(key, model, prompt, max_tokens=400):
    sent.append((key, model, prompt))
    return {"content": [{"type": "text", "text": "\"Un ouvrage de référence pour comprendre les bases. " + "Texte utile. " * 50 + "\""}]}
ai._post = fake_post
b = catalog.new_book("9782100000001", titre="Droit fiscal", auteurs=["Nom, Prénom"], editeur="Dunod", sujets=["Fiscalité"])
txt = ai.describe(b, "sk-ant-x", 300); assert 150 < len(txt) <= 301 and not txt.startswith('"') and "Fiscalité" in sent[-1][2]
try: ai.describe(b, "", 300); assert 0
except ai.AIError as e: assert "clé" in str(e)
def err(code, msg):
    def f(key, model, prompt, max_tokens=400): raise urllib.error.HTTPError("u", code, "x", {}, _io.BytesIO(('{"error":{"message":"%s"}}' % msg).encode()))
    return f
ai._post = err(401, "invalid x-api-key")
try: ai.describe(b, "k", 300); assert 0
except ai.AIError as e: assert "refusée" in str(e)
ai._post = err(400, "Your credit balance is too low")
try: ai.describe(b, "k", 300); assert 0
except ai.AIError as e: assert "crédit" in str(e)
ai._post = fake_post
job = catalog.FetchJob(["9782100000001"], dict(ST, claude_key="k")); job.kind = "ai"
store_b = {"9782100000001": b}
catalog.run_ai(job, lambda i: store_b.get(i), lambda nb, ia=False: None)
assert b["resume_ia"] and b["resume"] and "à relire" in catalog.status(dict(b, fetched=True, cover_path=""))[1]
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
