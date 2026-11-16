"""Lecture du fichier d'ISBN (Excel, CSV ou texte) et modèle Excel."""
import csv
import io
import re
import unicodedata

from . import isbn as isbnlib

# colonnes reconnues : clé interne -> noms possibles (sans accents, minuscules)
ALIASES = {
    "isbn": ["isbn", "isbn13", "isbn 13", "ean", "code isbn"],
    "prix": ["prix", "prix public", "prix france", "prix public eur", "prix france euros", "prix euro", "prix eur", "prix (eur)"],
    "collection": ["collection"],
    "titre": ["titre"],
    "auteurs": ["auteur", "auteurs"],
    "resume": ["resume", "description", "texte"],
    "date": ["date", "date de parution", "parution"],
    "editeur": ["editeur", "maison d'edition"],
    "pages": ["pages", "pagination", "nombre de pages"],
    "distributeur": ["distributeur"],
    "dispo": ["dispo", "disponibilite"],
}
LABELS = {"isbn": "ISBN", "prix": "Prix public (€)", "collection": "Collection", "titre": "Titre", "auteurs": "Auteurs",
          "resume": "Résumé", "date": "Date de parution", "editeur": "Éditeur", "pages": "Pages"}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"\s+", " ", s).strip(" :*")


def parse_price(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "").replace("\xa0", "")
    s = s.replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return round(float(m.group()), 2) if m else None


# ------------------------------------------------------------------ détection des colonnes
KEYS = ("isbn", "prix", "titre", "auteurs", "editeur", "collection", "date", "pages", "resume", "distributeur", "dispo")
KEY_LABELS = {"isbn": "ISBN", "prix": "Prix public (€)", "titre": "Titre", "auteurs": "Auteurs", "editeur": "Éditeur", "collection": "Collection",
              "date": "Date de parution", "pages": "Pages", "resume": "Résumé", "distributeur": "Distributeur", "dispo": "Disponibilité"}

# Mots d'en-tête reconnus (le texte est mis en minuscules, sans accents, ponctuation remplacée par des espaces).
_PAT = {
    "isbn": re.compile(r"\b(isbn(?: ?1[03])?|ean(?: ?13)?|gencod|gtin|code ?isbn|code ?barres?|codebarres?|ref isbn)\b"),
    "titre": re.compile(r"\b(titres?|designation|libelle|intitule|title|ouvrage)\b"),
    "auteurs": re.compile(r"\b(auteurs?|authors?|ecrivains?|contributeurs?)\b"),
    "editeur": re.compile(r"\b(editeurs?|maison d ?edition|publisher|maison)\b"),
    "collection": re.compile(r"\b(collections?|series?)\b"),
    "date": re.compile(r"\b(date ?(?:de )?(?:parution|publication)|parution|publication)\b"),
    "pages": re.compile(r"\b(nb ?pages?|nombre ?(?:de )?pages?|pages?|pagination)\b"),
    "resume": re.compile(r"\b(resume|description|presentation|quatrieme|4eme)\b"),
    "distributeur": re.compile(r"\b(distributeur|diffuseur)\b"),
    "dispo": re.compile(r"\b(dispo|disponibilite|etat commercial)\b"),
}
_EXACT = {  # en-têtes exacts (ancienne liste) : toujours reconnus
    "isbn": ["isbn", "isbn13", "isbn 13", "ean", "code isbn"], "date": ["date"], "texte": [], "resume": ["texte"],
}
_PRICE_WORD = re.compile(r"\b(prix|pvp|p ?v ?p|tarif|pu|p ?u|price)\b")
_PRICE_MOD = [(r"\bpublic\b", 3), (r"\bttc\b", 3), (r"\bpvp\b|\bp ?v ?p\b", 3), (r"\bfrance\b|\bfr\b", 1), (r"\beuros?\b|\beur\b", 1), (r"\bvente\b", 1),
              (r"\bht\b", -3), (r"\bnet\b", -2), (r"\bremise\b|\brabais\b", -5), (r"\bachat\b|\brevient\b|\bgros\b|\bfournisseur\b", -4), (r"\bariary\b|\bmga\b|\bar\b", -6)]


def _hn(s):
    """En-tête normalisé : minuscules, sans accents, sans ponctuation."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[._/\\\-:*#€$]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def price_score(h):
    h = _hn(h)
    if not _PRICE_WORD.search(h):
        return 0
    sc = 1
    for pat, w in _PRICE_MOD:
        if re.search(pat, h):
            sc += w
    return sc


def col_letter(j):
    s = ""
    j += 1
    while j:
        j, r = divmod(j - 1, 26)
        s = chr(65 + r) + s
    return s


def _filled(v):
    return v is not None and str(v).strip() != ""


def _is_isbn(v):
    raw = isbnlib.from_cell(v)
    return bool(raw and isbnlib.to13(raw))


def _num(v):
    """Nombre lu dans une cellule (prix, pages…) ou None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v or "").replace("\xa0", "").replace(" ", "").replace("€", "").replace("EUR", "").replace("eur", "").replace(",", ".")
    return float(t) if re.fullmatch(r"\d+(?:\.\d+)?", t) else None


def _header_hits(row):
    """{clé: colonne} d'après les en-têtes d'une ligne."""
    found, pscore = {}, {}
    for j, c in enumerate(row):
        if not _filled(c):
            continue
        n, h = _norm(c), _hn(c)
        ps = price_score(c)
        if ps > 0:
            pscore[j] = ps
        for key in ("isbn", "titre", "auteurs", "editeur", "collection", "date", "pages", "resume", "distributeur", "dispo"):
            if key in found:
                continue
            if n in _EXACT.get(key, ()) or _PAT[key].search(h):
                found[key] = j
    if pscore:
        found["prix"] = max(pscore, key=lambda j: (pscore[j], -j))
        found["_prix_tie"] = sum(1 for v in pscore.values() if v == max(pscore.values())) > 1
    return found


def analyze_table(table):
    """Analyse un tableau (liste de listes) : en-tête, colonnes et leur sens, avec ce qui reste à confirmer."""
    lines = [(i + 1, list(r)) for i, r in enumerate(table) if any(_filled(c) for c in r)]
    out = {"cols": {}, "from": {}, "start": 0, "header": None, "lines": lines, "reasons": [], "review": False, "n_isbn": 0, "ncols": 0, "signature": ""}
    if not lines:
        return out
    out["ncols"] = max(len(r) for _, r in lines)
    # 1. ligne d'en-tête : celle qui reconnaît le plus de colonnes dans les 30 premières lignes
    best, hdr = None, -1
    for i, (_, r) in enumerate(lines[:30]):
        h = _header_hits(r)
        score = len([k for k in h if not k.startswith("_")])
        if (h.get("isbn") is not None or score >= 2) and (best is None or score > best[0]):
            best, hdr = (score, h), i
    cols, src = {}, {}
    if best:
        cols = {k: v for k, v in best[1].items() if not k.startswith("_")}
        src = {k: "en-tête" for k in cols}
        out["header"], out["start"] = hdr, hdr + 1
        out["signature"] = "|".join(_hn(c) for c in lines[hdr][1] if _filled(c))
        tie = best[1].get("_prix_tie")
    else:
        tie = False
    body = [r for _, r in lines[out["start"]:]][:600]
    nc = out["ncols"]

    def column(j):
        return [r[j] if j < len(r) else None for r in body]

    # 2. colonne des ISBN : celle de l'en-tête si elle contient bien des ISBN, sinon la colonne qui en contient le plus
    def isbn_ratio(j):
        vals = [v for v in column(j) if _filled(v)]
        return (sum(1 for v in vals if _is_isbn(v)) / len(vals)) if vals else 0.0, len(vals)
    h = cols.get("isbn")
    if h is None or isbn_ratio(h)[0] < 0.3:
        cand = sorted(((isbn_ratio(j), j) for j in range(nc)), key=lambda t: (-t[0][0], -t[0][1], t[1]))
        if cand and cand[0][0][0] >= 0.5:
            j = cand[0][1]
            if h is not None and j != h:
                out["reasons"].append(f"La colonne « ISBN » de l'en-tête ne contient pas d'ISBN : la colonne {col_letter(j)} a été utilisée à la place.")
            cols["isbn"], src["isbn"] = j, "contenu"
        elif h is None:
            loose = sorted(((sum(1 for v in column(j) if _filled(v) and isbnlib.looks_like_isbn(v)), j) for j in range(nc)), reverse=True)
            if loose and loose[0][0] > 0:                         # des « presque ISBN » : on les signalera ligne par ligne
                cols["isbn"], src["isbn"] = loose[0][1], "contenu"
    if "isbn" in cols and out["header"] is None and lines:
        first = lines[0][1]                       # en-tête inconnu : la 1re ligne sans ISBN est quand même l'en-tête (on la saute, elle sert d'empreinte du format)
        j = cols["isbn"]
        if not (j < len(first) and _is_isbn(first[j])) and sum(1 for c in first if _filled(c)) >= 2:
            out["header"], out["start"] = 0, 1
            out["signature"] = "|".join(_hn(c) for c in first if _filled(c))
            body = [r for _, r in lines[1:]][:600]
    if "isbn" in cols:
        out["n_isbn"] = sum(1 for v in column(cols["isbn"]) if _is_isbn(v))
        if src["isbn"] == "contenu" and nc > 1 and out["header"] is None:
            out["reasons"].append("Pas d'en-tête reconnu : la colonne des ISBN a été repérée d'après son contenu.")
            out["review"] = True
    # 3. colonne des prix : en-tête (score) sinon contenu
    if "prix" in cols:
        vals = [v for v in column(cols["prix"]) if _filled(v)]
        if not vals or sum(1 for v in vals if _num(v) is not None) / len(vals) < 0.5:
            cols.pop("prix"); src.pop("prix", None)               # l'en-tête dit « prix » mais la colonne n'est pas numérique
        elif tie:
            out["reasons"].append("Plusieurs colonnes ressemblent à un prix : vérifie laquelle est le prix public TTC.")
            out["review"] = True
    if "prix" not in cols and "isbn" in cols:
        used = set(cols.values())
        cands = []
        for j in range(nc):
            if j in used:
                continue
            vals = [v for v in column(j) if _filled(v)]
            nums = [_num(v) for v in vals]
            ok = [x for x in nums if x is not None]
            if len(vals) < max(2, 0.4 * len(body)) or len(ok) / len(vals) < 0.8:
                continue
            if not all(0.5 <= x <= 2000 for x in ok):
                continue
            frac = sum(1 for x in ok if abs(x - round(x)) > 1e-9) / len(ok)
            if frac < 0.3:                                           # entiers seuls : pages, quantités, années… pas des prix
                continue
            cands.append((frac, len(ok), -j, j))
        if cands:
            cands.sort(reverse=True)
            cols["prix"], src["prix"] = cands[0][3], "contenu"
            out["reasons"].append(f"Le prix a été repéré d'après le contenu de la colonne {col_letter(cols['prix'])} : vérifie-le.")
            out["review"] = True
            if len(cands) > 1:
                out["reasons"].append("Plusieurs colonnes de nombres à virgule : vérifie que c'est la bonne.")
        elif out["header"] is not None or nc > 1:
            out["reasons"].append("Aucune colonne de prix reconnue : les prix seront à saisir.")
    out["cols"], out["from"] = cols, src
    return out


def rows_from_analysis(an, cols=None, start=None):
    """Livres lus d'après une analyse (ou un cadrage choisi à la main). Retourne (rows, problems, stats)."""
    strict = cols is not None or an["from"].get("isbn") == "en-tête"      # colonne choisie ou annoncée : toute valeur non valide est signalée
    cols = an["cols"] if cols is None else cols
    start = an["start"] if start is None else start
    lines = an["lines"][start:]
    rows, problems, seen = [], [], set()
    stats = {"sans_prix": 0, "lignes": len(lines)}
    if "isbn" not in cols:
        return rows, ["Aucune colonne d'ISBN reconnue dans ce fichier."], stats
    dil = "dispo" in cols or "distributeur" in cols      # export Dilicom : titre/auteur/éditeur = secours seulement
    for n, r in lines:
        def cell(k):
            j = cols.get(k)
            return r[j] if j is not None and j < len(r) else None
        raw = isbnlib.from_cell(cell("isbn"))
        if not raw:
            continue
        d = isbnlib.to13(raw)
        if not d:
            if isbnlib.looks_like_isbn(raw):
                problems.append(f"Ligne {n} : « {raw} » n'est pas un ISBN valide (clé de contrôle incorrecte ?).")
            elif len(re.sub(r"\D", "", raw)) >= (3 if strict else 8):
                problems.append(f"Ligne {n} : « {raw} » n'est pas un ISBN valide.")
            continue
        if d in seen:
            problems.append(f"Ligne {n} : ISBN {d} en double (ignoré).")
            continue
        seen.add(d)
        row = {"isbn": d}
        p = parse_price(cell("prix"))
        if p is not None:
            row["prix"] = p
        else:
            stats["sans_prix"] += 1
        if dil:
            fb = {}
            if cell("titre"):
                fb["titre"] = dilicom_title(cell("titre"))
            if cell("auteurs"):
                fb["auteurs"] = dilicom_authors(cell("auteurs"))
            if cell("editeur"):
                fb["editeur"] = dilicom_publisher(cell("editeur"))
            if fb:
                row["dilicom"] = fb
            if cell("dispo"):
                row["dispo"] = str(cell("dispo")).strip()
        for k in ("collection", "resume", "date", "pages") if dil else ("collection", "titre", "resume", "date", "editeur", "pages"):
            v = cell(k)
            if v not in (None, ""):
                row[k] = isbnlib.from_cell(v) if k != "date" else (v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v).strip())
        a = None if dil else cell("auteurs")
        if a not in (None, ""):
            row["auteurs"] = [x.strip() for x in re.split(r"[\n|;]", str(a)) if x.strip()]
        rows.append(row)
    return rows, problems, stats


def _rows_from_table(table):
    """table : liste de listes de cellules. Retourne (rows, problems)."""
    if not any(any(_filled(c) for c in r) for r in table):
        return [], ["Le fichier est vide."]
    rows, problems, _ = rows_from_analysis(analyze_table(table))
    return rows, problems


# ------------------------------------------------------------------ export Dilicom (.slk = SYLK)
def _sylk_table(text):
    """Lit un fichier SYLK (ancien format Excel) et retourne une liste de lignes."""
    cells, y, x = {}, 0, 0
    for line in text.splitlines():
        if not line[:2] in ("C;", "F;"):
            continue
        k = line.find(";K") if line[0] == "C" else -1
        head = line if k < 0 else line[:k]
        for part in head.split(";")[1:]:
            if part[:1] == "Y" and part[1:].isdigit():
                y = int(part[1:])
            elif part[:1] == "X" and part[1:].isdigit():
                x = int(part[1:])
        if k >= 0:
            v = line[k + 2:]
            if v.startswith('"'):
                v = v[1:-1].replace('""', '"').replace(";;", ";")
            elif v in ("TRUE", "FALSE", "#N/A"):
                pass
            else:
                try:
                    v = float(v)
                except ValueError:
                    pass
            cells[(y, x)] = v
    if not cells:
        return []
    ymax, xmax = max(c[0] for c in cells), max(c[1] for c in cells)
    return [[cells.get((r, c)) for c in range(1, xmax + 1)] for r in range(1, ymax + 1)]


_SMALL = {"de", "du", "des", "la", "le", "les", "et", "en", "au", "aux", "un", "une", "pour", "par", "sur", "dans", "a", "l", "d"}


def dilicom_title(s):
    """TITRE EN MAJUSCULES SANS ACCENTS -> « Titre en majuscules sans accents » (approximatif, à vérifier)."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if not s or s != s.upper():
        return s
    s = s.lower()
    s = re.sub(r"\s*/\s*", " : ", s, count=1)
    return s[:1].upper() + s[1:]


def dilicom_authors(s):
    out = []
    for a in re.split(r"\s*/\s*", str(s or "")):
        a = a.strip()
        if a:
            out.append(" ".join(w.capitalize() if "-" not in w else "-".join(x.capitalize() for x in w.split("-")) for w in a.lower().split()))
    return out


def dilicom_publisher(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s.title() if s == s.upper() else s


def read_tables(data: bytes, filename="isbn.xlsx"):
    """Lit un fichier : liste de (nom de feuille, tableau). Excel : toutes les feuilles visibles."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or (data[:2] == b"PK" and not name.endswith((".csv", ".txt", ".tsv", ".slk"))):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        out = []
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            try:
                ws.reset_dimensions()          # certains fichiers annoncent une taille fausse
            except Exception:
                pass
            out.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
        return out
    if name.endswith(".xls") or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        try:
            import xlrd
        except ImportError:
            raise ValueError("Ce format ancien (.xls) n'est pas lu ici : ouvre le fichier dans Excel et enregistre-le en .xlsx.")
        wb = xlrd.open_workbook(file_contents=data)
        out = []
        for sh in wb.sheets():
            if sh.visibility != 0:
                continue
            rows = []
            for r in range(sh.nrows):
                row = []
                for c in range(sh.ncols):
                    cell = sh.cell(r, c)
                    v = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            v = xlrd.xldate_as_datetime(v, wb.datemode)
                        except Exception:
                            pass
                    elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        v = None
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        v = bool(v)
                    row.append(v)
                rows.append(row)
            out.append((sh.name, rows))
        return out
    if name.endswith(".slk") or data[:3] == b"ID;":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252", "replace")
        return [("", _sylk_table(text))]
    text = data.decode("utf-8-sig", "replace") if data[:3] != b"\xff\xfe" else data.decode("utf-16", "replace")
    if "�" in text:
        text = data.decode("cp1252", "replace")
    sample = text[:2000]
    if name.endswith(".csv") or sample.count(";") + sample.count("\t") + sample.count(",") > 2:
        delim = max(";\t,", key=sample.count)
        return [("", list(csv.reader(io.StringIO(text), delimiter=delim)))]
    return [("", [re.split(r"[\s;]+", ln.strip(), maxsplit=1) for ln in text.splitlines() if ln.strip()])]


def analyze_file(data: bytes, filename="isbn.xlsx", remembered=None):
    """Analyse chaque feuille : colonnes reconnues, ce qui reste à confirmer. Retourne une liste de dicts (voir sheet_view pour l'affichage)."""
    sheets = []
    for name, table in read_tables(data, filename):
        an = analyze_table(table)
        an["sheet"], an["remembered"] = name, False
        sig = an["signature"]
        mem = (remembered or {}).get(sig) if sig else None
        if mem and isinstance(mem.get("cols"), dict) and "isbn" in mem["cols"] and all(isinstance(v, int) and v < max(an["ncols"], 1) for v in mem["cols"].values()):
            an["cols"], an["from"] = dict(mem["cols"]), {k: "mémorisé" for k in mem["cols"]}
            an["reasons"], an["review"], an["remembered"] = ["Colonnes reprises d'un import précédent de ce même format de fichier."], False, True
            an["n_isbn"] = sum(1 for _, r in an["lines"][an["start"]:] if an["cols"]["isbn"] < len(r) and _is_isbn(r[an["cols"]["isbn"]]))
        sheets.append(an)
    return sheets


def sheet_view(an):
    """Version simple (pour l'écran de vérification) d'une analyse de feuille."""
    lines = an["lines"]
    head = lines[an["header"]][1] if an["header"] is not None else []
    body = [r for _, r in lines[an["start"]:]]
    cols = []
    for j in range(an["ncols"]):
        samples = [str(r[j]).strip()[:40] for r in body if j < len(r) and _filled(r[j])][:3]
        key = next((k for k, v in an["cols"].items() if v == j), "")
        cols.append({"idx": j, "letter": col_letter(j), "header": str(head[j]).strip()[:40] if j < len(head) and _filled(head[j]) else "", "samples": samples, "key": key,
                     "from": an["from"].get(key, "") if key else ""})
    return {"name": an["sheet"], "n_lines": len(body), "n_isbn": an["n_isbn"], "header_line": lines[an["header"]][0] if an["header"] is not None else None,
            "signature": an["signature"], "start": an["start"], "cols": cols, "reasons": an["reasons"], "review": an["review"], "remembered": an["remembered"], "has_isbn": "isbn" in an["cols"]}


def import_data(data: bytes, filename="isbn.xlsx", mapping=None, remembered=None):
    """Lit les livres du fichier. mapping = {feuille: {"cols": {clé: colonne}, "start": n}} (choisi à la main) ; sinon détection automatique.
    Retourne (rows, problems, recap)."""
    sheets = analyze_file(data, filename, remembered)
    if not any(an["lines"] for an in sheets):
        return [], ["Le fichier est vide."], {"sheets": [], "sans_prix": 0}
    rows, problems, seen, recap = [], [], set(), {"sheets": [], "sans_prix": 0}
    used = [an for an in sheets if an["lines"] and ("isbn" in an["cols"] or (mapping or {}).get(an["sheet"]))]
    for an in used:
        m = (mapping or {}).get(an["sheet"])
        if m:
            cols = {k: int(v) for k, v in (m.get("cols") or {}).items() if k in KEYS and str(v).lstrip("-").isdigit() and int(v) >= 0}
            r, pb, st = rows_from_analysis(an, cols, int(m.get("start", an["start"])))
        else:
            cols = an["cols"]
            r, pb, st = rows_from_analysis(an)
        pre = f"Feuille « {an['sheet']} » — " if len(used) > 1 and an["sheet"] else ""
        problems += [pre + x for x in pb]
        for row in r:
            if row["isbn"] in seen:
                problems.append(f"{pre}ISBN {row['isbn']} déjà lu sur une autre feuille (ignoré).")
                continue
            seen.add(row["isbn"])
            rows.append(row)
        head = an["lines"][an["header"]][1] if an["header"] is not None else []
        recap["sheets"].append({"name": an["sheet"], "n": len(r), "cols": [{"label": KEY_LABELS[k], "col": col_letter(j), "header": (str(head[j]).strip() if j < len(head) and _filled(head[j]) else "")}
                                                                       for k, j in cols.items()], "signature": an["signature"], "cols_map": cols})
        recap["sans_prix"] += st["sans_prix"]
    if not used:
        problems.append("Aucune colonne d'ISBN reconnue dans ce fichier.")
    return rows, problems, recap


def read_rows(data: bytes, filename="isbn.xlsx"):
    rows, problems, _ = import_data(data, filename)
    return rows, problems


def make_template(path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Livres"
    heads = ["ISBN", "Prix public (€)", "Collection"]
    ws.append(heads)
    ws.append(["9782100870165", 24.9, ""])
    ws.append(["9782100861514", 24.9, "Expert"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="294364")
        c.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 28
    for r in range(2, 400):
        ws.cell(r, 1).number_format = "@"
    ws2 = wb.create_sheet("Mode d'emploi")
    for line in ["Un livre par ligne : l'ISBN (avec ou sans tirets) et le prix public en euros.",
                 "La collection est facultative : le programme essaie de la trouver tout seul.",
                 "Colonnes facultatives (même en-tête) : Titre, Auteurs, Résumé, Date de parution, Éditeur, Pages.",
                 "Ce que tu remplis ici remplace ce que le programme trouve sur internet."]:
        ws2.append([line])
    ws2.column_dimensions["A"].width = 110
    wb.save(path)
