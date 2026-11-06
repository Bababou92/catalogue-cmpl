"""Mise à jour automatique du .exe depuis les « Releases » GitHub.

Principe : un petit fichier latest.json (version, lien, empreinte SHA-256) est publié avec chaque version.
Au lancement, on le lit en arrière-plan. Si une version plus récente existe, l'interface propose de
l'installer ; rien n'est jamais fait sans le clic de l'utilisateur. Le téléchargement est vérifié (SHA-256),
puis l'ancien .exe est renommé en « .old » (Windows interdit d'écraser un .exe en cours mais autorise
à le renommer), le nouveau prend sa place et le programme se relance.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

from . import version

TIMEOUT = 8
CHUNK = 64 * 1024
STATE = {"state": "idle", "latest": None, "notes": "", "progress": 0.0, "error": "", "size": 0}
_lock = threading.Lock()
_cancel = threading.Event()


# ---------------------------------------------------------------- utilitaires

def parse_version(v):
    out = []
    for part in str(v).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def feed_url():
    return os.environ.get("CMPL_UPDATE_URL") or f"https://github.com/{version.REPO}/releases/latest/download/latest.json"


def exe_path():
    """Chemin de l'exécutable à remplacer (None si on tourne depuis les sources)."""
    forced = os.environ.get("CMPL_UPDATE_TARGET")
    if forced:
        return os.path.abspath(forced)
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return None


def url_allowed(url):
    if os.environ.get("CMPL_UPDATE_URL"):          # essais locaux
        return True
    return url.startswith(f"https://github.com/{version.REPO}/releases/download/")


def _set(**kw):
    with _lock:
        STATE.update(kw)


def status():
    with _lock:
        out = dict(STATE)
    out["version"] = version.VERSION
    out["can_apply"] = exe_path() is not None
    return out


def cleanup_old():
    """Supprime l'ancien exe (.old) laissé par la mise à jour précédente."""
    p = exe_path()
    if not p:
        return
    for suffix in (".old", ".new"):
        try:
            os.remove(p + suffix)
        except OSError:
            pass


# ---------------------------------------------------------------- vérification

def _fetch_feed():
    req = urllib.request.Request(feed_url(), headers={"User-Agent": "CMPL-Catalogue/" + version.VERSION})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read(200_000).decode("utf-8-sig"))
    if not isinstance(data, dict) or not data.get("version"):
        raise ValueError("fichier de version invalide")
    return data


def check(silent_errors=True):
    """Lit latest.json ; met à jour STATE (none / available / error)."""
    if STATE["state"] in ("downloading", "ready"):
        return
    _set(state="checking", error="")
    try:
        feed = _fetch_feed()
        url = str(feed.get("url", ""))
        sha = str(feed.get("sha256", "")).lower()
        if is_newer(feed["version"], version.VERSION):
            if not url_allowed(url) or len(sha) != 64:
                raise ValueError("fichier de version incomplet ou adresse non autorisée")
            _set(state="available", latest={"version": str(feed["version"]), "url": url, "sha256": sha},
                 notes=str(feed.get("notes", ""))[:1200], size=int(feed.get("size") or 0))
        else:
            _set(state="none", latest=None, notes="")
    except Exception as e:                      # pas d'internet, GitHub indisponible…
        _set(state="error", latest=None, error="" if silent_errors else "Impossible de vérifier les mises à jour (pas de connexion internet ?).")


def start_check(delay=0.0, silent=True):
    def run():
        if delay:
            time.sleep(delay)
        check(silent)
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- téléchargement

def _download(latest, target):
    new = target + ".new"
    try:
        _cancel.clear()
        _set(state="downloading", progress=0.0, error="")
        req = urllib.request.Request(latest["url"], headers={"User-Agent": "CMPL-Catalogue/" + version.VERSION})
        h = hashlib.sha256()
        done = 0
        with urllib.request.urlopen(req, timeout=20) as r, open(new, "wb") as out:
            total = int(r.headers.get("Content-Length") or STATE.get("size") or 0)
            while True:
                if _cancel.is_set():
                    raise InterruptedError("annulé")
                buf = r.read(CHUNK)
                if not buf:
                    break
                out.write(buf)
                h.update(buf)
                done += len(buf)
                if total:
                    _set(progress=min(0.99, done / total))
        if h.hexdigest().lower() != latest["sha256"]:
            raise ValueError("le fichier téléchargé est corrompu (empreinte différente), réessaie")
        if sys.platform == "win32" and not os.environ.get("CMPL_UPDATE_TARGET"):
            with open(new, "rb") as fh:
                if fh.read(2) != b"MZ":
                    raise ValueError("le fichier téléchargé n'est pas un programme Windows")
        _set(state="ready", progress=1.0)
    except InterruptedError:
        _remove(new)
        _set(state="available", progress=0.0, error="")
    except PermissionError:
        _remove(new)
        _set(state="error", error="Dossier protégé en écriture : déplace le programme sur le Bureau ou dans Documents, puis réessaie.")
    except Exception as e:
        _remove(new)
        _set(state="error", error=f"Téléchargement impossible : {e}")


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def start_download():
    target = exe_path()
    if not target:
        _set(state="error", error="La mise à jour automatique ne marche que dans le programme .exe.")
        return False
    with _lock:
        latest = STATE.get("latest")
        if STATE["state"] == "downloading" or not latest:
            return False
    threading.Thread(target=_download, args=(latest, target), daemon=True).start()
    return True


def cancel():
    _cancel.set()


# ---------------------------------------------------------------- installation

def apply():
    """Remplace l'exe par le nouveau et le relance. L'appelant doit ensuite quitter le processus."""
    target = exe_path()
    new, old = target + ".new", target + ".old"
    if STATE["state"] != "ready" or not os.path.isfile(new):
        raise RuntimeError("aucune mise à jour téléchargée")
    _remove(old)
    os.replace(target, old)                       # renommer un .exe en cours d'exécution est permis
    try:
        os.replace(new, target)
    except Exception:
        os.replace(old, target)                   # retour arrière : on garde l'ancienne version
        raise
    if not os.environ.get("CMPL_UPDATE_NOSPAWN"):
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        flags = 0
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([target, "--relance"], env=env, close_fds=True, creationflags=flags,
                         cwd=os.path.dirname(target))
    _set(state="restarting")
