"""Lance le serveur avec de fausses réponses Google/BnF (pour les tests d'interface)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("CMPL_CAT_DATA_DIR", tempfile.mkdtemp())
import fakenet
from catalogue import ai, catalog, citations, net, sources, server
_flag = os.environ.get("CMPL_FAKE_OFFLINE_FILE")


def _http(url, timeout=25):
    import time, urllib.error
    time.sleep(0.4)                                    # assez lent pour pouvoir couper « internet » pendant la recherche
    if _flag and os.path.exists(_flag):
        raise urllib.error.URLError("hors ligne")
    return fakenet.http_get(url, timeout)


sources.http_get = _http
sources.RETRY_DELAYS = (0.2, 0.2)
catalog.NET_POLL = 1.0


def fake_claude(key, model, prompt, max_tokens=400):
    import time; time.sleep(0.2)
    t = prompt.split("\n")[0].replace("Titre : ", "")
    return {"content": [{"type": "text", "text": "Description simulée de « %s » : un ouvrage de référence qui présente clairement les notions essentielles, avec des exemples et des exercices pour s'entraîner. " % t * 2}], "usage": {"input_tokens": 1100, "output_tokens": 170}}


ai._post = fake_claude


def fake_quotes(key, model, prompt):
    import json, time; time.sleep(0.3)
    n = len(citations._load_ia().get("quotes", []))
    return {"content": [{"type": "text", "text": json.dumps([{"t": "Citation simulée numéro %d pour les essais." % (n + i), "a": "Auteur %d" % (n + i)} for i in range(12)])}], "usage": {"input_tokens": 650, "output_tokens": 700}}


citations.ai_post = fake_quotes
citations.AI_COOLDOWN = 3.0
if _flag:                                              # essais : le fichier existe = pas d'internet
    net.online = lambda force=False: not os.path.exists(_flag)
server.main(open_browser=False)
