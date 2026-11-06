"""ISBN : lecture tolérante, conversion ISBN-10 -> ISBN-13, contrôle de la clé, éditeur d'après le préfixe."""
import re

# Éditeurs courants d'après le début de l'ISBN-13 (les plus longs préfixes gagnent). Modifiable dans editeurs.json.
PREFIXES = {
    "978201": "Hachette", "978202": "Seuil", "978203": "Larousse", "978207": "Gallimard", "978208": "Flammarion",
    "978209": "Nathan", "978210": "Dunod", "978213": "PUF", "9782200": "Armand Colin", "9782212": "Eyrolles",
    "9782226": "Albin Michel", "9782275": "LGDJ", "9782311": "Vuibert", "9782707": "La Découverte",
}


def clean(s):
    s = str(s or "").strip().upper()
    s = re.sub(r"^ISBN(?:-?1[03])?\s*:?\s*", "", s)
    return re.sub(r"[^0-9X]", "", s)


def check13(d):
    if not re.fullmatch(r"\d{13}", d):
        return False
    t = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12]))
    return (10 - t % 10) % 10 == int(d[12])


def check10(d):
    if not re.fullmatch(r"\d{9}[\dX]", d):
        return False
    t = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d))
    return t % 11 == 0


def to13(s):
    """Renvoie l'ISBN-13 (chiffres) ou '' si la saisie n'est pas un ISBN valide."""
    d = clean(s)
    if len(d) == 13 and check13(d):
        return d
    if len(d) == 10 and check10(d):
        core = "978" + d[:9]
        return core + str((10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core)) % 10) % 10)
    return ""


def looks_like_isbn(s):
    return len(clean(s)) in (10, 13)


def from_cell(v):
    """Valeur de cellule Excel -> texte (gère les nombres 9.78210086151e12)."""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v if v is not None else "").strip()


def pretty(d):
    return f"{d[:3]}-{d[3]}-{d[4:7]}-{d[7:12]}-{d[12]}" if len(d) == 13 else d


def publisher_for(d, extra=None):
    table = dict(PREFIXES)
    table.update({str(k): v for k, v in (extra or {}).items()})
    for n in range(len(d), 5, -1):
        if d[:n] in table:
            return table[d[:n]]
    return ""


def to10(d13):
    """ISBN-13 en 978… -> ISBN-10 (pour certains services de couvertures) ; '' sinon."""
    d = clean(d13)
    if len(d) != 13 or not d.startswith("978"):
        return ""
    core = d[3:12]
    tot = sum((10 - i) * int(c) for i, c in enumerate(core))
    chk = (11 - tot % 11) % 11
    return core + ("X" if chk == 10 else str(chk))
