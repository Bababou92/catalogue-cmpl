"""Test de connexion internet : le navigateur se croit « en ligne » dès qu'il est relié à un wifi, même sans internet.
On tente donc une vraie connexion TCP (sans envoyer de données) vers quelques serveurs connus."""
import socket
import threading
import time

TARGETS = [("1.1.1.1", 443), ("8.8.8.8", 443), ("github.com", 443), ("www.google.com", 443)]
TIMEOUT = 2.5
CACHE_S = 4.0
_cache = {"t": 0.0, "ok": True}
_lock = threading.Lock()


def _try(host, port, hit):
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            hit.set()
    except OSError:
        pass


def online(force=False):
    """True si au moins un des serveurs répond (les essais se font en parallèle : 2,5 s au plus)."""
    now = time.time()
    with _lock:
        if not force and now - _cache["t"] < CACHE_S:
            return _cache["ok"]
    hit = threading.Event()
    ths = [threading.Thread(target=_try, args=(h, p, hit), daemon=True) for h, p in TARGETS]
    for t in ths:
        t.start()
    deadline = time.time() + TIMEOUT + 0.3
    while time.time() < deadline and not hit.is_set() and any(t.is_alive() for t in ths):
        hit.wait(0.05)
    ok = hit.is_set()
    with _lock:
        _cache.update(t=time.time(), ok=ok)
    return ok
