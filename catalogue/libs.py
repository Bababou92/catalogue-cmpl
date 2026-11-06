"""Bibliothèque de catalogues enregistrés et sauvegardes automatiques datées."""
import hashlib
import json
import os
import re
import time
import uuid

from . import store

KEEP_BACKUPS = 10


def _dir(name):
    d = os.path.join(store.data_dir(), name)
    os.makedirs(d, exist_ok=True)
    return d


def _jwrite(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _jread(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _safe_id(i):
    if not re.fullmatch(r"[0-9a-f]{12}", str(i or "")):
        raise ValueError("catalogue introuvable")
    return i


# ---------------------------------------------------------------- catalogues enregistrés
def list_catalogues():
    out = []
    d = _dir("catalogues")
    for f in os.listdir(d):
        if not f.endswith(".json"):
            continue
        try:
            c = _jread(os.path.join(d, f))
            out.append({"id": c["id"], "nom": c.get("nom", ""), "updated": c.get("updated", 0), "n": len(c.get("books", []))})
        except Exception:
            continue
    return sorted(out, key=lambda x: -x["updated"])


def save_catalogue(cat, nom, cid=None):
    """Enregistre (ou met à jour) le catalogue. Retourne son identifiant."""
    cid = _safe_id(cid) if cid else uuid.uuid4().hex[:12]
    meta = dict(cat.get("meta", {}), lib_id=cid)
    _jwrite(os.path.join(_dir("catalogues"), cid + ".json"),
            {"id": cid, "nom": (nom or meta.get("titre") or "Catalogue").strip() or "Catalogue", "updated": time.time(), "meta": meta, "books": cat.get("books", [])})
    return cid


def load_catalogue(cid):
    p = os.path.join(_dir("catalogues"), _safe_id(cid) + ".json")
    if not os.path.isfile(p):
        raise ValueError("catalogue introuvable")
    return _jread(p)


def delete_catalogue(cid):
    p = os.path.join(_dir("catalogues"), _safe_id(cid) + ".json")
    if os.path.isfile(p):
        os.remove(p)


def rename_catalogue(cid, nom):
    c = load_catalogue(cid)
    c["nom"] = (nom or "").strip() or c["nom"]
    _jwrite(os.path.join(_dir("catalogues"), cid + ".json"), c)


def duplicate_catalogue(cid, nom=None):
    """Copie pour le catalogue suivant : on garde les livres, on remet à zéro le mois affiché."""
    c = load_catalogue(cid)
    meta = dict(c.get("meta", {}))
    for k in ("indicatif", "garde_date"):
        meta.pop(k, None)
    return save_catalogue({"meta": meta, "books": c.get("books", [])}, nom or (c["nom"] + " (copie)"))


# ---------------------------------------------------------------- sauvegardes automatiques
def _digest(cat):
    return hashlib.sha1(json.dumps(cat, ensure_ascii=False, sort_keys=True).encode("utf8")).hexdigest()


def backup(cat, reason="auto"):
    """Copie datée du catalogue en cours ; ignorée si identique à la dernière ; ne garde que les dernières."""
    if not cat.get("books"):
        return None
    d = _dir("sauvegardes")
    cur = _digest(cat)
    existing = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    if existing:
        try:
            if _digest(_jread(os.path.join(d, existing[-1]))["cat"]) == cur:
                return None
        except Exception:
            pass
    reason = re.sub(r"[^a-z0-9\-]", "", reason.lower())[:20] or "auto"
    name = time.strftime("%Y-%m-%d_%Hh%Mm%S") + "_" + reason + ".json"
    _jwrite(os.path.join(d, name), {"t": time.time(), "reason": reason, "n": len(cat["books"]), "titre": cat.get("meta", {}).get("titre", ""), "cat": cat})
    for old in sorted(f for f in os.listdir(d) if f.endswith(".json"))[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    return name


def list_backups():
    out = []
    d = _dir("sauvegardes")
    for f in sorted((f for f in os.listdir(d) if f.endswith(".json")), reverse=True):
        try:
            j = _jread(os.path.join(d, f))
            out.append({"name": f, "t": j.get("t", 0), "reason": j.get("reason", ""), "n": j.get("n", 0), "titre": j.get("titre", "")})
        except Exception:
            continue
    return out


def load_backup(name):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}h[0-9]{2}m[0-9]{2}_[a-z0-9\-]*\.json", name or ""):
        raise ValueError("sauvegarde introuvable")
    p = os.path.join(_dir("sauvegardes"), name)
    if not os.path.isfile(p):
        raise ValueError("sauvegarde introuvable")
    return _jread(p)["cat"]
