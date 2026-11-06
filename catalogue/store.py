"""Dossiers de données, réglages, cache des sources et catalogue en cours."""
import json
import os
import sys
import threading
import time

_lock = threading.Lock()

SETTING_KEYS = ("google_key", "out_dir", "covers_dir", "resume_max", "taux", "theme", "update_popup")


def data_dir():
    d = os.environ.get("CMPL_CAT_DATA_DIR")
    if not d:
        base = os.environ.get("APPDATA") if sys.platform.startswith("win") else os.path.expanduser("~/.local/share")
        d = os.path.join(base or os.path.expanduser("~"), "CMPL-Catalogue")
    os.makedirs(d, exist_ok=True)
    return d


def docs_dir():
    p = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(p if os.path.isdir(p) else os.path.expanduser("~"), "CMPL-Catalogues")


def _path(name):
    return os.path.join(data_dir(), name)


def _read(name, default):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write(name, obj):
    tmp = _path(name) + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        os.replace(tmp, _path(name))


# ---------------------------------------------------------------- réglages
def load_settings():
    s = {"google_key": "", "out_dir": docs_dir(), "covers_dir": os.path.join(docs_dir(), "Couvertures"),
         "resume_max": 420, "taux": 3366, "theme": "light", "update_popup": True}
    s.update({k: v for k, v in _read("reglages.json", {}).items() if k in SETTING_KEYS})
    return s


def save_settings(s):
    _write("reglages.json", {k: s.get(k) for k in SETTING_KEYS})


def update_settings(patch):
    s = load_settings()
    for k, v in patch.items():
        if k in SETTING_KEYS:
            s[k] = v
    save_settings(s)
    return s


# ---------------------------------------------------------------- éditeurs perso
def editeurs():
    return _read("editeurs.json", {})


# ---------------------------------------------------------------- cache des sources (30 jours)
def cache_get(isbn, max_age_days=30):
    c = _read("cache.json", {}).get(isbn)
    if c and time.time() - c.get("t", 0) < max_age_days * 86400:
        return c.get("raw")
    return None


def cache_put(isbn, raw):
    with _lock:
        pass
    allc = _read("cache.json", {})
    allc[isbn] = {"t": time.time(), "raw": raw}
    _write("cache.json", allc)


def cover_cache_dir():
    d = os.path.join(data_dir(), "couvertures_cache")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- catalogue en cours
def load_catalogue():
    return _read("catalogue.json", {"meta": {"titre": "", "date": ""}, "books": []})


def save_catalogue(cat):
    _write("catalogue.json", cat)
