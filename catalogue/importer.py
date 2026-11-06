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


def _rows_from_table(table):
    """table : liste de listes de cellules. Retourne (rows, problems)."""
    table = [[c for c in r] for r in table if any(str(c or "").strip() for c in r)]
    if not table:
        return [], ["Le fichier est vide."]
    cols, start = {}, 0
    for i, r in enumerate(table[:15]):
        found = {}
        for j, c in enumerate(r):
            n = _norm(c)
            for key, names in ALIASES.items():
                if n in names and key not in found:
                    found[key] = j
        if "isbn" in found:
            cols, start = found, i + 1
            break
    if not cols:                                  # pas d'en-tête : colonne 1 = ISBN, colonne 2 = prix
        cols = {"isbn": 0, "prix": 1}
    rows, problems, seen = [], [], set()
    for n, r in enumerate(table[start:], start + 1):
        def cell(k):
            j = cols.get(k)
            return r[j] if j is not None and j < len(r) else None
        raw = isbnlib.from_cell(cell("isbn"))
        if not raw:
            continue
        d = isbnlib.to13(raw)
        if not d:
            problems.append(f"Ligne {n} : « {raw} » n'est pas un ISBN valide (clé de contrôle incorrecte ?).")
            continue
        if d in seen:
            problems.append(f"Ligne {n} : ISBN {d} en double (ignoré).")
            continue
        seen.add(d)
        row = {"isbn": d}
        p = parse_price(cell("prix"))
        if p is not None:
            row["prix"] = p
        for k in ("collection", "titre", "resume", "date", "editeur", "pages"):
            v = cell(k)
            if v not in (None, ""):
                row[k] = isbnlib.from_cell(v) if k != "date" else (v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v).strip())
        a = cell("auteurs")
        if a not in (None, ""):
            row["auteurs"] = [x.strip() for x in re.split(r"[\n|;]", str(a)) if x.strip()]
        rows.append(row)
    return rows, problems


def read_rows(data: bytes, filename="isbn.xlsx"):
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        return _rows_from_table([list(r) for r in ws.iter_rows(values_only=True)])
    text = data.decode("utf-8-sig", "replace") if data[:3] != b"\xff\xfe" else data.decode("utf-16", "replace")
    if "�" in text:
        text = data.decode("cp1252", "replace")
    sample = text[:2000]
    if name.endswith(".csv") or sample.count(";") + sample.count("\t") + sample.count(",") > 2:
        delim = max(";\t,", key=sample.count)
        return _rows_from_table(list(csv.reader(io.StringIO(text), delimiter=delim)))
    return _rows_from_table([re.split(r"[\s;]+", ln.strip(), maxsplit=1) for ln in text.splitlines() if ln.strip()])


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
