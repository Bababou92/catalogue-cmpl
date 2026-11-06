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
def fake_post(key, model, prompt, max_tokens=1500):
    sent.append((key, model, prompt))
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "\"Un ouvrage de référence pour comprendre les bases. " + "Texte utile. " * 50 + "\""}]}
ai._post = fake_post
b = catalog.new_book("9782100000001", titre="Droit fiscal", auteurs=["Nom, Prénom"], editeur="Dunod", sujets=["Fiscalité"])
txt = ai.describe(b, "sk-ant-x", 300); assert 150 < len(txt) <= 301 and not txt.startswith('"') and "Fiscalité" in sent[-1][2]
try: ai.describe(b, "", 300); assert 0
except ai.AIError as e: assert "clé" in str(e)
def err(code, msg):
    def f(key, model, prompt, max_tokens=1500): raise urllib.error.HTTPError("u", code, "x", {}, _io.BytesIO(('{"error":{"message":"%s"}}' % msg).encode()))
    return f
ai._post = err(401, "invalid x-api-key")
try: ai.describe(b, "k", 300); assert 0
except ai.AIError as e: assert "refusée" in str(e)
ai._post = err(400, "Your credit balance is too low")
try: ai.describe(b, "k", 300); assert 0
except ai.AIError as e: assert "crédit" in str(e)
ai._post = lambda key, model, prompt, max_tokens=1500: {"stop_reason": "max_tokens", "content": [{"type": "text", "text": "Ouvrage de référence en anatomie humaine, il associe la description"}]}
try: ai.describe(b, "k", 300); assert 0
except ai.AIError as e: assert "coupée" in str(e), e
ai._post = lambda key, model, prompt, max_tokens=1500: {"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "Ouvrage de référence en anatomie humaine, il associe la description des structures à leur fonction et à la clinique."}]}
assert ai.describe(b, "k", 300).endswith("clinique.")
assert ai.MODELS[0] == "claude-haiku-5-5" and "Cyberattaques" in ai.SYSTEM
ai._post = fake_post
job = catalog.FetchJob(["9782100000001"], dict(ST, claude_key="k")); job.kind = "ai"
store_b = {"9782100000001": b}
catalog.run_ai(job, lambda i: store_b.get(i), lambda nb, ia=False: None)
assert b["resume_ia"] and b["resume"] and "à relire" in catalog.status(dict(b, fetched=True, cover_path=""))[1]

# ---- format BnF variante, infos douces (non bloquantes), statuts
assert sources.parse_bnf_format("1 volume 223 p ; 27 cm")[0] == "223" and sources.parse_bnf_format("1 volume 223 p ; 27 cm")[2] == "27 cm"
assert sources.parse_bnf_format("1 vol. (XII-369 p.) : ill. ; 24 cm")[:1] == ("XII-369",)
assert sources.parse_bnf_format("1 vol. (non paginé) ; 24 cm")[0] == ""
assert sources.parse_bnf_format("1 vol. (310 p.) : ill. en coul. ; 24 cm")[1] == "illustrations en couleur"
bk = catalog.new_book("9782100000002", titre="T", auteurs=["A, B"], resume="R", date="2024", editeur="E", prix=10, fetched=True)
cv = os.path.join(COV, "x.jpg"); Image.new("RGB", (300, 420), (10, 10, 200)).save(cv); bk["cover_path"] = cv
assert catalog.status(bk) == ("vert", "complet"), catalog.status(bk)          # pages/collection/illustrations absents : jamais bloquant
assert catalog.public(bk)["infos"] == ["nombre de pages non trouvé", "pas de collection", "illustrations non précisées"]
bk["date"] = ""; assert "date de parution" in catalog.status(bk)[1]
# ---- vider les caches
store.cache_put("9782100000002", {"google": None}); assert store.cache_get("9782100000002") is not None
open(os.path.join(store.cover_cache_dir(), "x.jpg"), "wb").write(b"x"); store.clear_cache()
assert store.cache_get("9782100000002") is None and not os.listdir(store.cover_cache_dir())
d_ = tempfile.mkdtemp(); Image.new("RGB", (200, 300)).save(os.path.join(d_, "9782100870165.jpg")); Image.new("RGB", (200, 300)).save(os.path.join(d_, "logo.png"))
assert sources.delete_cover_files(d_) == 1 and os.listdir(d_) == ["logo.png"]

# ---- tableau des prix
from catalogue import prix
assert prix.ariary(23, 3366) == 77418 and prix.ariary(19.9, 3366) == 66983 and prix.ariary(19.9, 3366, 100) == 67000 and prix.ariary(None, 3366) is None
assert prix.fmt_date("03/06/2024") == "3-juin-24" and prix.fmt_date("06/2024") == "juin-24" and prix.fmt_date("2024") == "2024"
assert prix.fmt_isbn("9782100851638") == "9 782 100 851 638" and prix.fmt_eur(16.5) == "16,50"
assert sources.parse_edition("Strategor : la référence (9e éd.) J. Albino") == "9" and sources.parse_edition("Atlas ([Nouvelle édition]) P. B.") == ""
tb = catalog.new_book("9782100851638", titre="Cas de compta : 10 récits pour enrichir sa pratique", auteurs=["Ragaigne, Alexandre", "Gond, Jean-Pascal", "Lachuer, X", "Autre, Y"],
                      editeur="Éditions \"Le Moniteur\"", date="03/06/2024", prix=23, edition="1")
rv = prix.row_values(tb, 3366)
assert rv == ["Cas de compta", "RAGAIGNE/GOND/LACHUER ET AL", "1", "3-juin-24", "9 782 100 851 638", "LE MONITEUR", "23,00", prix.fmt_int(77418)], rv
tb["taux"] = "4488"; assert prix.row_values(tb, 3366)[7] == prix.fmt_int(103224)
pp = prix.build_pages([dict(tb, isbn="97821008516%02d" % i) for i in range(60)], "Test", "Octobre 2024", 3366)
assert len(pp) >= 2 and all(p.w < p.h for p in pp) and any("2/%d" % len(pp) in "".join(r.text for e in p.elements if hasattr(e, "paras") for pa in e.paras for r in pa.runs) for p in pp)
op = os.path.join(tempfile.mkdtemp(), "mix.pdf"); render_pdf.build_pdf(pages.build_pages(books[:2] if "books" in dir() else [tb]) + pp, op)
import pypdf as _pp; _r = _pp.PdfReader(op); assert abs(float(_r.pages[0].mediabox.width) - float(_r.pages[-1].mediabox.width)) < 1 and "Prix indicatifs Octobre 2024" in _r.pages[-1].extract_text()
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

# pages fixes + multiple de 4 (impression en folio)
from catalogue import server as _srv, store as _st
_srv.CAT["books"] = [dict(tb, isbn="97821008516%02d" % i) for i in range(7)]
for opts in ({}, {"p_garde": False}, {"p_dos": False, "p_cond": False}, {"p_multi4": False}):
    _st.update_settings(dict({"p_garde": True, "p_cond": True, "p_proforma": True, "p_dos": True, "p_multi4": True, "inclure_prix": True}, **opts))
    fr, bp, pp, post = _srv.build_all()
    allp = fr + bp + pp + post
    assert all(p.w < p.h for p in allp), "toutes les pages doivent etre verticales"
    if opts.get("p_multi4", True):
        assert len(allp) % 4 == 0, (opts, len(allp))
        if _st.load_settings().get("p_dos"):
            assert allp[-1].name == "4e de couverture"
    else:
        assert not any(p.name == "Page blanche" for p in allp)
print("OK pages fixes")

# annuler / bibliotheque / sauvegardes / prix modifies / excel
import copy as _copy, time as _time
from catalogue import libs as _libs
_srv.load()
_b = catalog.new_book("9782100870165"); _b.update(titre="Analyse", auteurs=["A, B"], resume="x" * 50, date="03/06/2024", editeur="Dunod", prix=24.0, fetched=True)
_srv.CAT["books"] = [_b]; _srv.save(); _time.sleep(1.3)
_srv.CAT["books"][0]["titre"] = "Modifie"; _srv.save()
_srv.undo_redo(-1); assert _srv.CAT["books"][0]["titre"] == "Analyse"
_srv.undo_redo(1); assert _srv.CAT["books"][0]["titre"] == "Modifie"
_cid = _libs.save_catalogue(_srv.CAT, "Nov"); _d = _libs.duplicate_catalogue(_cid)
assert {c["nom"] for c in _libs.list_catalogues()} == {"Nov", "Nov (copie)"}
assert "indicatif" not in _libs.load_catalogue(_d)["meta"]
assert _libs.backup(_srv.CAT, "test") and _libs.backup(_srv.CAT, "test") is None
_added, _chg = _srv.add_rows([{"isbn": "9782100870165", "prix": 26.0}]); assert _added == 0 and _chg[0]["ancien"] == 24.0
_o = tempfile.mkdtemp(); _r = _srv.generate(_o, "T", True, True, True); assert len(_r["files"]) == 3
import openpyxl as _ox; _ws = _ox.load_workbook(_r["files"][2]).active; assert _ws.cell(6, 7).value == 26.0
_st.update_settings({"p_garde": True, "p_cond": True, "p_proforma": True, "p_dos": True, "p_multi4": True, "inclure_prix": True})
assert _srv.check()["pages"] % 4 == 0
print("OK annuler/bibliotheque")

# rubriques, tri, couleur de garde
_bs = []
for _i, (_r, _t) in enumerate([("Droit", "Zebre"), ("Droit", "Abeille"), ("Economie", "Le chat"), ("", "Orphelin"), ("Economie", "Banque")]):
    _x = catalog.new_book("97821008701%02d" % _i); _x.update(titre=_t, auteurs=["A, B"], resume="Texte " * 30, rubrique=_r, date="03/06/2024", editeur="Dunod", prix=24.0, fetched=True); _bs.append(_x)
_srv.CAT["books"] = _bs; _srv.CAT["meta"]["garde_couleur"] = "orange"; _srv.save()
_srv.sort_books("rubrique"); assert [b["rubrique"] for b in _srv.CAT["books"]] == ["Droit", "Droit", "Economie", "Economie", ""]
_srv.sort_books("titre"); assert [b["titre"] for b in _srv.CAT["books"]][:2] == ["Abeille", "Banque"]
_srv.sort_books("rubrique")
_pg = pages.build_pages(_srv.CAT["books"], "T", "#F0A04B")
_heads = [e.name for p in _pg for e in p.elements if getattr(e, "name", "").startswith("Rubrique :")]
assert _heads == ["Rubrique : Droit", "Rubrique : Economie", "Rubrique : Autres titres"], _heads
assert not any(getattr(e, "name", "").startswith("Rubrique") for p in pages.build_pages([catalog.new_book("9782100870165")], "T") for e in p.elements)
_st.update_settings({"p_garde": True, "p_cond": True, "p_proforma": True, "p_dos": True, "p_multi4": True, "inclure_prix": True})
_pv = _srv.preview(0); assert len(_pv["pages"]) == _pv["count"] and _pv["pages"][0]["kind"] == "garde" and _pv["pages"][-1]["kind"] == "dos"
assert any(e.fill == "#F0A04B" for e in _srv.build_all()[0][0].elements if hasattr(e, "fill"))
print("OK rubriques")

# tableaux tournés sur page verticale + citation de la 4e de couverture
from catalogue import citations as _ci, fixed as _fx, prix as _px, model as _md, ai as _ai
import json as _json
_bk = [catalog.new_book("97821008701%02d" % i) for i in range(40)]
for _i, _x in enumerate(_bk):
    _x.update(titre="Livre %d" % _i, auteurs=["A, B"], editeur="Dunod", prix=24.0, date="03/06/2024", fetched=True)
_pp = _px.build_pages(_bk, "T", "", 3366)
assert all((p.w, p.h) == (210.0, 297.0) for p in _pp) and len(_pp) >= 1
assert all(isinstance(e, _md.TextBox) and e.rot == 270 for e in _pp[0].elements if isinstance(e, _md.TextBox))
_hz = _pp[0].hot[0]; assert _hz["h"] > _hz["w"] * 3 and _hz["field"] == "titre_tableau"       # une cellule devient haute et étroite
_pf = _fx.proforma_page(); assert (_pf.w, _pf.h) == (210.0, 297.0) and any(isinstance(e, _md.TextBox) and e.rot == 270 for e in _pf.elements)
_o = tempfile.mkdtemp(); render_pdf.build_pdf(_pp + [_pf], os.path.join(_o, "t.pdf")); assert os.path.getsize(os.path.join(_o, "t.pdf")) > 3000
from pypdf import PdfReader as _PR
_rd = _PR(os.path.join(_o, "t.pdf")); assert all(round(float(p.mediabox.width)) == 595 and round(float(p.mediabox.height)) == 842 for p in _rd.pages)
assert "Livre 0" in _rd.pages[0].extract_text() and "PROFORMA" in "".join(p.extract_text() for p in _rd.pages)
_srv.CAT["books"] = _bk; _srv.CAT["meta"].pop("citation", None); _srv.save()
_fr, _bp, _pr, _post = _srv.build_all()
assert all((p.w, p.h) == (210.0, 297.0) for p in _fr + _bp + _pr + _post)
# citations : tirage sans répétition, précédente, texte libre, absence
assert 40 <= len(_ci.QUOTES) and all(12 <= len(t) <= _ci.MAX_LEN and a for t, a in _ci.QUOTES) and len({t for t, _ in _ci.QUOTES}) == len(_ci.QUOTES)
_m = {}; _seen = []
for _i in range(len(_ci.QUOTES)):
    _s = _ci.next_quote(_m); _seen.append(_s["texte"])
assert len(set(_seen)) == len(_ci.QUOTES) - (1 if _ci.QUOTES[0][0] not in _seen else 0) or len(set(_seen)) >= len(_ci.QUOTES) - 1
assert _s["tour_fait"] and _s["peut_prev"] and all(_seen[i] != _seen[i + 1] for i in range(len(_seen) - 1))
_c1 = _ci.current(_m)[0]; _ci.prev_quote(_m); assert _ci.current(_m)[0] == _seen[-2] and _c1 == _seen[-1]
_ci.set_custom(_m, "Ma citation", "Moi"); assert _ci.current(_m)[:2] == ("Ma citation", "Moi")
_ci.set_off(_m, True); assert _ci.current(_m) is None; assert not any(e.name == "Citation" for e in _fx.back_page("#5DADE1", _ci.current(_m)).elements)
_ci.set_off(_m, False)
# bouton IA : bloqué tant que le tour n'est pas fait, puis 12 citations, délai, limite par jour, aucun doublon
_ci.AI_COOLDOWN = 0.2
_m2 = {}; _ok, _why = _ci.ia_available(_m2); assert not _ok and "tour" in _why
_calls = []
def _fake_post(key, model, prompt):
    _calls.append(prompt)
    return {"content": [{"type": "text", "text": _json.dumps([{"t": "Citation IA numéro %d, pour tester l'ajout" % i, "a": "Auteur %d" % i} for i in range(12)] + [{"t": _ci.QUOTES[0][0], "a": "Doublon"}])}]}
_ci.ai_post = _fake_post
_m2["citation_tour"] = "1"
assert _ci.fetch_ai(_m2, "K") == 12 and len(_calls) == 1 and len(_ci.pool()) == len(_ci.QUOTES) + 12
_ok, _why = _ci.ia_available(_m2); assert not _ok and ("tour" in _why or "Patiente" in _why)
_m2["citation_tour"] = "1"; _ok, _why = _ci.ia_available(_m2); assert not _ok and "Patiente" in _why
import time as _t; _t.sleep(0.3)
_n = 0
for _k in range(10):
    _m2["citation_tour"] = "1"; _t.sleep(0.25)
    try: _ci.fetch_ai(_m2, "K"); _n += 1
    except _ai.AIError: break
assert _n == _ci.AI_PER_DAY - 1 and len(_calls) == _ci.AI_PER_DAY, (_n, len(_calls))
try: _ci.fetch_ai({"citation_tour": "1"}, ""); assert False
except _ai.AIError: pass
print("OK tableaux tournes / citations")
