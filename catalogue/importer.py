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
        dil = "dispo" in cols or "distributeur" in cols      # export Dilicom : titre/auteur/éditeur = secours seulement
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


def read_rows(data: bytes, filename="isbn.xlsx"):
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        return _rows_from_table([list(r) for r in ws.iter_rows(values_only=True)])
    if name.endswith(".slk") or data[:3] == b"ID;":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252", "replace")
        return _rows_from_table(_sylk_table(text))
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
